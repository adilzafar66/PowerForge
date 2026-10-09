"""Shared storage, ORM models, and page rendering.

The processing service is not in this package yet. This package must not import
FastAPI or Celery. Only ``rendering.py`` may import Pillow or PyMuPDF.
"""
