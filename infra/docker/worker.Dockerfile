FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Worker shares the API's dependency set (SQLAlchemy models, AI gateway).
COPY apps/api/requirements.txt apps/api/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY apps/api /app/api_lib
COPY apps/worker /app/worker
ENV PYTHONPATH=/app/api_lib:/app/worker

CMD ["python", "-m", "worker.main"]
