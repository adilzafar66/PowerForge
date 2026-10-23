"""Real Postgres lock ordering and stale-session behavior, using dedicated sessions."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from engineering_support import engineering_context as engineering_context
from powerforge_api.exceptions import ArchivedProject, CancelledProject, RevisionReadOnly
from powerforge_api.schemas.projects import RevisionCreate
from powerforge_api.services.engineering_model_service import EngineeringModelService
from powerforge_api.services.project_service import ProjectService
from powerforge_api.services.revision_service import RevisionService
from powerforge_api.services.revision_writes import lock_writable_revision
from powerforge_engineering_model import InformationState
from powerforge_persistence import Project, ProjectRevision
from powerforge_project import ProjectStatus, RevisionStatus

pytestmark = pytest.mark.integration


def wait_blocked(engine, pid: int) -> None:
    deadline = time.monotonic() + 5
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            if connection.execute(
                text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pid}
            ).scalar_one():
                return
            time.sleep(0.02)
    pytest.fail("Expected database lock contention did not occur")


@pytest.mark.parametrize(
    "operation", ["create", "update", "type_change", "attribute", "remove", "restore"]
)
def test_every_mutation_locks_project_then_revision(engineering_context, operation) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    eid = eq.id
    if operation == "restore":
        ctx.service.remove_equipment(*ctx.ids, eid)
    statements = []

    def capture(conn, cursor, statement, *rest):
        statements.append(statement)

    engine = ctx.session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        match operation:
            case "create":
                ctx.service.create_equipment(*ctx.ids, "CT")
            case "update":
                ctx.service.update_equipment(*ctx.ids, eid, name="Updated")
            case "type_change":
                ctx.service.update_equipment(*ctx.ids, eid, equipment_type="LV_BREAKER")
            case "attribute":
                ctx.service.set_attribute(
                    *ctx.ids, eid, "nominal_voltage", InformationState.PRESENT, value=1
                )
            case "remove":
                ctx.service.remove_equipment(*ctx.ids, eid)
            case "restore":
                ctx.service.restore_equipment(*ctx.ids, eid)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    project_lock = next(
        i for i, s in enumerate(statements) if "FROM projects" in s and "FOR SHARE" in s
    )
    revision_lock = next(
        i for i, s in enumerate(statements) if "FROM project_revisions" in s and "FOR UPDATE" in s
    )
    assert project_lock < revision_lock
    assert not any(s.lstrip().startswith("UPDATE projects") for s in statements)


@pytest.mark.parametrize(
    "transition,error",
    [("archive", ArchivedProject), ("cancel", CancelledProject), ("supersede", RevisionReadOnly)],
)
def test_waiting_write_refreshes_stale_status_after_transition(
    engineering_context, transition, error
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS", name="Original")
    eid, engine = eq.id, ctx.session.get_bind()
    ready, proceed = Event(), Event()
    backend = {}

    def writer():
        with Session(engine) as session:
            # Keep strong references to stale ORM rows while waiting for a concurrent transition.
            project = session.get(Project, ctx.project_id)
            revision = session.get(ProjectRevision, ctx.revision_id)
            backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            assert (
                project.status == ProjectStatus.ACTIVE and revision.status == RevisionStatus.DRAFT
            )
            ready.set()
            assert proceed.wait(5)
            with pytest.raises(error):
                EngineeringModelService(session).update_equipment(
                    *ctx.ids, eid, name="Must not save"
                )
            assert not session.in_transaction()

    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as holder:
        future = pool.submit(writer)
        try:
            assert ready.wait(5)
            project = holder.scalar(
                select(Project).where(Project.id == ctx.project_id).with_for_update()
            )
            if transition == "archive":
                project.status = ProjectStatus.ARCHIVED
            elif transition == "cancel":
                project.status = ProjectStatus.CANCELLED
            else:
                holder.get(ProjectRevision, ctx.revision_id).status = RevisionStatus.SUPERSEDED
            holder.flush()
            proceed.set()
            wait_blocked(engine, backend["pid"])
            holder.commit()
        finally:
            proceed.set()
            holder.rollback()
        future.result(timeout=10)
    assert ctx.service.get_equipment(*ctx.ids, eid).name == "Original"


def test_archive_waits_for_shared_engineering_write_guard(engineering_context) -> None:
    ctx = engineering_context
    engine = ctx.session.get_bind()
    started = Event()
    backend = {}

    def archive():
        with Session(engine) as session:
            backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            ProjectService(session).archive_project(ctx.project_id)

    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as holder:
        lock_writable_revision(holder, *ctx.ids)
        future = pool.submit(archive)
        try:
            assert started.wait(5)
            wait_blocked(engine, backend["pid"])
        finally:
            holder.commit()
        future.result(timeout=10)
    with pytest.raises(ArchivedProject):
        ctx.service.create_equipment(*ctx.ids, "BUS")


def test_revision_clone_serializes_with_base_model_mutation(
    engineering_context, monkeypatch
) -> None:
    """The clone sees a complete before-state; the blocked writer commits afterward."""
    from powerforge_api.services import revision_service
    from powerforge_persistence.engineering import Equipment

    ctx = engineering_context
    source = ctx.service.create_equipment(*ctx.ids, "BUS", name="Before")
    engine = ctx.session.get_bind()
    clone_ready, release_clone, writer_ready = Event(), Event(), Event()
    backend = {}
    copied = revision_service.copy_active_engineering_model

    def holding_copy(session, base, target):
        count = copied(session, base, target)
        clone_ready.set()
        assert release_clone.wait(5)
        return count

    monkeypatch.setattr(revision_service, "copy_active_engineering_model", holding_copy)

    def clone():
        with Session(engine) as session:
            result = RevisionService(session).create_revision(
                ctx.project_id,
                RevisionCreate(
                    identifier=f"clone-{source.id}",
                    based_on_revision_id=ctx.revision_id,
                    carry_forward_documents=False,
                ),
            )
            return result.revision.id

    def mutate():
        with Session(engine) as session:
            backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            writer_ready.set()
            EngineeringModelService(session).update_equipment(*ctx.ids, source.id, name="After")

    with ThreadPoolExecutor(max_workers=2) as pool:
        clone_future = pool.submit(clone)
        assert clone_ready.wait(5)
        mutation_future = pool.submit(mutate)
        assert writer_ready.wait(5)
        try:
            wait_blocked(engine, backend["pid"])
        finally:
            release_clone.set()
        child_id = clone_future.result(timeout=10)
        mutation_future.result(timeout=10)

    with Session(engine) as session:
        inherited = session.scalar(
            select(Equipment).where(
                Equipment.revision_id == child_id,
                Equipment.inherited_from_equipment_id == source.id,
            )
        )
        current_source = session.get(Equipment, source.id)
        assert inherited.name == "Before"
        assert current_source.name == "After"
