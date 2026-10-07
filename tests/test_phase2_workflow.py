"""The spec section 34 engineering workflow, executed exactly, end to end through the API.

Needs RUN_INTEGRATION=1 (database); object storage is the in-memory fake.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from documents_support import client, code, docs_url, documents_of, make_revision, upload
from file_factory import PDF
from powerforge_api.storage import InMemoryObjectStorage

SLD_A = "SLD_RevA.pdf"
SLD_B = "SLD_RevB.pdf"
T1 = "T1_Shop_Drawing.pdf"
FAULT = "Utility_Fault_Data.pdf"


def pdf_for(name: str) -> bytes:
    """A valid PDF whose bytes differ per file, so no duplicate warnings muddy the scenario."""
    return PDF + f"% {name}\n".encode()


def revision_url(project_id: str, revision_id: str) -> str:
    return f"/api/projects/{project_id}/revisions/{revision_id}"


def rows(project_id: str, revision_id: str) -> dict[str, dict[str, Any]]:
    response = client.get(docs_url(project_id, revision_id), params={"status": "ALL"})
    assert response.status_code == 200, response.text
    return {item["document"]["original_filename"]: item for item in response.json()["items"]}


def states(project_id: str, revision_id: str) -> dict[str, tuple[str, str]]:
    return {
        name: (item["origin"], item["status"])
        for name, item in rows(project_id, revision_id).items()
    }


def test_the_section_34_workflow(
    require_db: None, use_storage: Callable[[InMemoryObjectStorage], InMemoryObjectStorage]
) -> None:
    storage = use_storage(InMemoryObjectStorage())

    # 1. User creates Project P-100 (the number is suffixed so reruns do not collide).
    created = client.post(
        "/api/projects",
        json={"project_number": f"P-100-{uuid.uuid4().hex[:8]}", "project_name": "Workflow"},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    # 2. Revision 0: no ACTIVE revision exists, so no base; it starts empty.
    rev0_response = make_revision(pid, "0")
    assert rev0_response.status_code == 201, rev0_response.text
    rev0 = rev0_response.json()
    assert rev0["based_on_revision_id"] is None
    assert rev0["inherited_document_count"] == 0
    assert rows(pid, rev0["id"]) == {}

    # 3. Three uploads: three Documents, three UPLOADED/INCLUDED associations.
    for name in (SLD_A, T1, FAULT):
        uploaded = upload(pid, rev0["id"], pdf_for(name), name)
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["duplicate_detected"] is False
    assert len(documents_of(pid)) == 3
    assert len(storage.objects) == 3
    assert states(pid, rev0["id"]) == {
        SLD_A: ("UPLOADED", "INCLUDED"),
        T1: ("UPLOADED", "INCLUDED"),
        FAULT: ("UPLOADED", "INCLUDED"),
    }
    rev0_rows = rows(pid, rev0["id"])
    document_ids = {name: item["document"]["id"] for name, item in rev0_rows.items()}

    # 4. Revision 0 becomes ACTIVE.
    activated = client.post(f"{revision_url(pid, rev0['id'])}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    rev0_package = client.get(docs_url(pid, rev0["id"]), params={"status": "ALL"}).json()

    # 5. Revision 1 with defaults: based on Revision 0, carry-forward on.
    rev1_response = make_revision(pid, "1")
    assert rev1_response.status_code == 201, rev1_response.text
    rev1 = rev1_response.json()
    assert rev1["based_on_revision_id"] == rev0["id"]
    assert rev1["inherited_document_count"] == 3
    inherited = rows(pid, rev1["id"])
    assert set(inherited) == {SLD_A, T1, FAULT}
    for name, item in inherited.items():
        assert item["origin"] == "INHERITED"
        assert item["status"] == "INCLUDED"
        assert item["inherited_from_revision_id"] == rev0["id"]
        assert item["inherited_from_revision_identifier"] == "0"
        assert item["document"]["id"] == document_ids[name]
        assert item["id"] != rev0_rows[name]["id"]
    assert len(documents_of(pid)) == 3
    assert len(storage.objects) == 3
    assert len(storage.calls_for("put")) == 3

    # 6. SLD_RevB.pdf into Revision 1: a new Document, UPLOADED/INCLUDED.
    uploaded_b = upload(pid, rev1["id"], pdf_for(SLD_B), SLD_B)
    assert uploaded_b.status_code == 201, uploaded_b.text
    assert uploaded_b.json()["origin"] == "UPLOADED"
    assert uploaded_b.json()["status"] == "INCLUDED"
    assert uploaded_b.json()["document"]["id"] not in document_ids.values()
    assert len(documents_of(pid)) == 4
    assert len(storage.objects) == 4

    # 7. Remove the inherited SLD_RevA.pdf from Revision 1.
    removed = client.post(f"{docs_url(pid, rev1['id'])}/{inherited[SLD_A]['id']}/remove")
    assert removed.status_code == 200, removed.text
    assert states(pid, rev1["id"]) == {
        SLD_A: ("INHERITED", "REMOVED"),
        SLD_B: ("UPLOADED", "INCLUDED"),
        T1: ("INHERITED", "INCLUDED"),
        FAULT: ("INHERITED", "INCLUDED"),
    }
    assert states(pid, rev0["id"]) == {
        SLD_A: ("UPLOADED", "INCLUDED"),
        T1: ("UPLOADED", "INCLUDED"),
        FAULT: ("UPLOADED", "INCLUDED"),
    }
    assert len(storage.objects) == 4
    assert storage.calls_for("delete") == []

    # 8. Revision 1 is activated; Revision 0 is superseded and its package is read-only.
    activated_1 = client.post(f"{revision_url(pid, rev1['id'])}/activate")
    assert activated_1.status_code == 200, activated_1.text
    assert activated_1.json()["status"] == "ACTIVE"
    superseded = client.get(revision_url(pid, rev0["id"])).json()
    assert superseded["status"] == "SUPERSEDED"

    r0_item = rev0_rows[SLD_A]["id"]
    r0_docs = docs_url(pid, rev0["id"])
    attempts = {
        "upload": upload(pid, rev0["id"], pdf_for("late.pdf"), "late.pdf"),
        "edit": client.patch(f"{r0_docs}/{r0_item}", json={"notes": "late"}),
        "remove": client.post(f"{r0_docs}/{r0_item}/remove"),
        "restore": client.post(f"{r0_docs}/{r0_item}/restore"),
        "reuse": client.post(
            f"{r0_docs}/reuse",
            json={"source_revision_document_id": uploaded_b.json()["id"]},
        ),
    }
    for name, response in attempts.items():
        assert (response.status_code, code(response)) == (409, "revision_read_only"), name

    assert client.get(docs_url(pid, rev0["id"])).status_code == 200
    assert client.get(f"{r0_docs}/{r0_item}").status_code == 200
    from_rev0 = client.get(f"{r0_docs}/{r0_item}/download-url")
    assert from_rev0.status_code == 200, from_rev0.text
    # The same physical object serves Revision 0's and Revision 1's (removed) SLD_RevA.
    from_rev1 = client.get(f"{docs_url(pid, rev1['id'])}/{inherited[SLD_A]['id']}/download-url")
    assert from_rev1.status_code == 200, from_rev1.text
    assert (
        storage.calls_for("create_download_url")[0] == storage.calls_for("create_download_url")[1]
    )

    # Revision 0's package is unchanged by everything that happened after its activation.
    assert client.get(docs_url(pid, rev0["id"]), params={"status": "ALL"}).json() == rev0_package
    assert client.get(revision_url(pid, rev0["id"])).json() == superseded
    assert states(pid, rev0["id"]) == {
        SLD_A: ("UPLOADED", "INCLUDED"),
        T1: ("UPLOADED", "INCLUDED"),
        FAULT: ("UPLOADED", "INCLUDED"),
    }

    # Revision 1 still shows its own package.
    assert states(pid, rev1["id"]) == {
        SLD_A: ("INHERITED", "REMOVED"),
        SLD_B: ("UPLOADED", "INCLUDED"),
        T1: ("INHERITED", "INCLUDED"),
        FAULT: ("INHERITED", "INCLUDED"),
    }

    # 9. No file was ever copied or deleted: four Documents, four objects, four puts.
    assert len(documents_of(pid)) == 4
    assert len(storage.objects) == 4
    assert len(storage.calls_for("put")) == 4
    assert storage.calls_for("delete") == []
