FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/services/api/src

COPY packages /app/packages
COPY services/api /app/services/api
COPY database /app/database

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        -e /app/packages/shared \
        -e /app/packages/engineering-model \
        -e /app/packages/document-model \
        -e /app/packages/extraction \
        -e /app/packages/topology \
        -e /app/packages/validation \
        -e /app/packages/provenance \
        -e /app/packages/ai \
        -e /app/services/api

EXPOSE 8000

CMD ["sh", "-c", "alembic -c /app/database/alembic.ini upgrade head && uvicorn powerforge_api.main:app --host 0.0.0.0 --port 8000"]
