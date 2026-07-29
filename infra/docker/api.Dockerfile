FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps/api/requirements.txt apps/api/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY apps/api /app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
