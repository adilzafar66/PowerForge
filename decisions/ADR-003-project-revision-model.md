# ADR-003: Project and revision model (Phase 1)

## Status

Accepted

## Date

2026-09-03

## Context

Phase 1 introduces projects and revisions. The product spec, Phase 0 architecture docs, and the first Phase 1 draft disagreed on several points: whether project revisions and engineering-model revisions were the same entity, whether authentication starts with projects, how identifiers appear in URLs, and how project lifecycle status changes.

Those decisions must be recorded before implementation so later phases attach documents and the engineering model to the correct row.

## Decisions

### One revision entity

`ProjectRevision` is the only revision. Future documents, extraction jobs, and the engineering model attach to `project_revisions.id`.

"Model revisions" in `ENGINEERING_MODEL.md` means the engineering-model snapshot stored **on** a project revision in a later phase. Phase 1 does not create a `model_revisions` table.

### Package boundary

- `packages/project` (`powerforge_project`): enums and domain schemas only.
- `services/api`: SQLAlchemy models, services, and FastAPI routes.

This matches existing domain packages (contracts, no SQLAlchemy, no FastAPI).

### Identity

- Primary keys are UUIDs via `gen_random_uuid()` (pgcrypto, Phase 0).
- API paths use those UUIDs.
- The human-readable revision code is `identifier`, unique per project. It is not named `revision_id`.
- `created_by` is a nullable UUID with no foreign key. A users table and authentication are **not** Phase 1. When they exist, `created_by` becomes a non-null FK.
- `engineer_names` is a list of free-text names on the project until users exist.

### Revision lifecycle

- Projects are created without a revision.
- New revisions are `DRAFT`.
- `activate_revision` is the only writer of `ACTIVE`, and it is atomic (partial unique index: one ACTIVE revision per project). The previous ACTIVE revision becomes `SUPERSEDED`.
- `SUPERSEDED` revisions cannot be re-activated. Only revisions created after the current ACTIVE revision (by `created_at`) may be activated.

### Project lifecycle

Status values: `ACTIVE`, `PAUSED`, `CANCELLED`, `ARCHIVED`.

Transitions:

- `ACTIVE` ↔ `PAUSED`
- `ACTIVE` / `PAUSED` → `CANCELLED`
- `ACTIVE` / `PAUSED` / `CANCELLED` → `ARCHIVED`
- `ARCHIVED` → the status recorded at archive time (`ACTIVE`, `PAUSED`, or `CANCELLED`)

Status is not changed via PATCH. Explicit actions: `/pause`, `/resume`, `/cancel`, `/archive`, `/unarchive`.

PATCH project updates metadata only (name, address, client, scope, engineer names, description). `project_number` is immutable.

PATCH revision may update `description` and `identifier`, not status.

Archived projects reject PATCH, new revisions, revision activation, pause, resume, and cancel. Unarchive is allowed and restores `status_before_archive`. Existing archived rows with no recorded history restore to `ACTIVE`.

Cancelled projects use the same write restrictions as archived projects (no PATCH, revisions, or activate). Archive from `CANCELLED` remains allowed. Unarchive of a cancelled-then-archived project returns it to `CANCELLED`, not `ACTIVE`. There is no `uncancel` action.

### UI routing and search

- `/` is the project list.
- `/status` is the Phase 0 stack health page.
- Opening a revision in Phase 1 is a placeholder.
- Project list search matches `project_number`, `project_name`, `client_name`, and `project_address`. Broader search (scope, engineers, revisions) is deferred.

## Consequences

**Positive**

- Later phases can attach equipment and documents with `revision_id` → `project_revisions.id` without a second revision hierarchy.
- Auth can be added without rewriting project tables (`created_by` stays nullable until then).
- Concurrent activate cannot create two ACTIVE revisions.

**Negative / follow-up**

- There is no `CANCELLED` → `ACTIVE` path. Archive is a filing action and does not uncancel.
- Engineer names will need a migration when users exist.
- Project-level access control is deferred with authentication; the Phase 0 note that it "begins when projects exist" is superseded.

## References

- `cursor/phase1_specs.txt`
- `cursor/specification.txt` §6, §21, §34
- `docs/ARCHITECTURE.md`
- `docs/ENGINEERING_MODEL.md`
- [ADR-004](ADR-004-document-storage-and-revision-inheritance.md) — extends this model with revision lineage and revision-scoped documents (Phase 2)
