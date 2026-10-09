"""The shared processing package stays free of the API, the worker, and renderers."""

from __future__ import annotations

import ast
from pathlib import Path

from powerforge_document_processing.models import Document

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "document-processing"
SRC_ROOT = PACKAGE_ROOT / "src" / "powerforge_document_processing"
API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "powerforge_api"
FORBIDDEN_IMPORTS = frozenset({"fastapi", "celery", "PIL", "fitz", "cv2"})


def test_document_is_mapped_once_in_the_shared_package() -> None:
    assert Document.__module__ == "powerforge_document_processing.models"
    assert not (API_ROOT / "models.py").exists()
    assert not (API_ROOT / "storage").exists()


def test_package_does_not_import_fastapi_celery_or_renderers() -> None:
    for path in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                root = module.split(".", 1)[0]
                assert root not in FORBIDDEN_IMPORTS, f"{path.name} imports {module}"
