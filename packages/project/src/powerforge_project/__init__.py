"""Project and revision domain vocabulary.

Enums and pure transition helpers only. Persistence lives in services/api.
"""

from powerforge_project.enums import ProjectStatus, RevisionStatus
from powerforge_project.transitions import assert_transition, can_transition

__all__ = [
    "ProjectStatus",
    "RevisionStatus",
    "assert_transition",
    "can_transition",
]
