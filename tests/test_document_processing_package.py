"""The shared processing package stays free of the API, the worker, and renderers."""

from __future__ import annotations

import ast
from pathlib import Path

from powerforge_document_processing.models import Document

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "document-processing"
SRC_ROOT = PACKAGE_ROOT / "src" / "powerforge_document_processing"
API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "powerforge_api"
FORBIDDEN_IMPORTS = frozenset(
    {"fastapi", "celery", "cv2", "pytesseract", "tesseract", "easyocr", "paddleocr"}
)
RENDERER_ONLY_IMPORTS = frozenset({"PIL", "fitz"})


def test_document_is_mapped_once_in_the_shared_package() -> None:
    assert Document.__module__ == "powerforge_document_processing.models"
    assert not (API_ROOT / "models.py").exists()
    assert not (API_ROOT / "storage").exists()


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return {module.split(".", 1)[0] for module in modules}


def test_package_does_not_import_fastapi_celery_or_ocr() -> None:
    for path in SRC_ROOT.rglob("*.py"):
        roots = _imported_roots(path)
        assert not (roots & FORBIDDEN_IMPORTS), f"{path.name} imports {roots & FORBIDDEN_IMPORTS}"
        if path.name != "rendering.py":
            assert not (roots & RENDERER_ONLY_IMPORTS), f"{path.name} imports a renderer"


def test_renderer_does_not_import_sqlalchemy() -> None:
    roots = _imported_roots(SRC_ROOT / "rendering.py")
    assert "sqlalchemy" not in roots
