FROM python:3.12-slim

WORKDIR /app

ARG WORKER_PACKAGE=document-worker
ARG CELERY_APP=document_worker.celery_app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CELERY_APP=${CELERY_APP}
ENV PYTHONPATH=/app/services/worker/src

COPY packages/shared /app/packages/shared
COPY services/${WORKER_PACKAGE} /app/services/worker

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e /app/packages/shared -e /app/services/worker

CMD celery -A ${CELERY_APP} worker --loglevel=INFO --concurrency=1
