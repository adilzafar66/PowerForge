"""Shared storage, ORM models, page rendering, and the processing service.

Upload does not call the service. This package must not import FastAPI or
Celery. Only ``rendering.py`` may import Pillow or PyMuPDF.
"""
