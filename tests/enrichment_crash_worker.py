"""Test-only pause after claim at real object-storage I/O; no producer output is faked."""

import time

from extraction_worker import extraction_tasks
from extraction_worker.celery_app import celery_app as celery_app
from powerforge_document_processing.storage.factory import build_s3_storage as real_storage


class SlowSource:
    def __init__(self, storage):
        self.storage = storage

    def get(self, key):
        time.sleep(60)
        return self.storage.get(key)

    def __getattr__(self, key):
        return getattr(self.storage, key)


extraction_tasks.build_s3_storage = lambda settings: SlowSource(real_storage(settings))
