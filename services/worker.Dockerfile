FROM python:3.12-slim

WORKDIR /app

ARG WORKER_PACKAGE=document-worker
ARG CELERY_APP=document_worker.celery_app
ARG CELERY_QUEUE=celery

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CELERY_APP=${CELERY_APP}
ENV CELERY_QUEUE=${CELERY_QUEUE}
ENV PYTHONPATH=/app/services/worker/src

COPY packages/shared /app/packages/shared
COPY packages/project /app/packages/project
COPY packages/persistence /app/packages/persistence
COPY packages/engineering-model /app/packages/engineering-model
COPY packages/document-model /app/packages/document-model
COPY packages/document-processing /app/packages/document-processing
COPY packages/ai /app/packages/ai
COPY packages/document-classification /app/packages/document-classification
COPY services/${WORKER_PACKAGE} /app/services/worker

RUN pip install --no-cache-dir --upgrade pip \
    && if [ "$WORKER_PACKAGE" = "document-worker" ]; then \
        pip install --no-cache-dir \
            -e /app/packages/shared \
            -e /app/packages/project \
            -e /app/packages/persistence \
            -e /app/packages/engineering-model \
            -e /app/packages/document-model \
            -e /app/packages/document-processing \
            -e /app/packages/ai \
            -e /app/packages/document-classification \
            -e /app/services/worker \
            "psycopg[binary]>=3.2"; \
    elif [ "$WORKER_PACKAGE" = "extraction-worker" ]; then \
        pip install --no-cache-dir \
            -e /app/packages/shared \
            -e /app/packages/project \
            -e /app/packages/persistence \
            -e /app/packages/engineering-model \
            -e /app/packages/document-model \
            -e /app/packages/document-processing \
            -e /app/packages/document-classification \
            -e /app/packages/ai \
            -e /app/services/worker \
            "openai>=2" \
            "psycopg[binary]>=3.2"; \
    else \
        pip install --no-cache-dir -e /app/packages/shared -e /app/services/worker; \
    fi

CMD celery -A ${CELERY_APP} worker --loglevel=INFO --concurrency=1 -Q ${CELERY_QUEUE}
