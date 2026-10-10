"""Shared storage, ORM models, page rendering, and the processing service.

Upload calls ``ensure`` after the document commit. This package must not
import FastAPI. Only ``enqueue.py`` may import Celery. Only ``rendering.py``
may import Pillow or PyMuPDF.
"""
