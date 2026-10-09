"""Shared storage and ORM models loaded by the API and, later, the document worker.

The processing service is not in this package yet. This package must not import
FastAPI, Celery, Pillow, or PyMuPDF.
"""
