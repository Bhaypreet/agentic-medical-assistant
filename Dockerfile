# "python:3.11-slim" is a moving tag, so an unrelated rebuild could
# silently change the base image underneath the service. Pinned to a
# patch version here; pin by digest for a fully reproducible build:
#   docker pull python:3.11.9-slim
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.11.9-slim
# then replace the tag below with the printed name@sha256:... value.
FROM python:3.11.9-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libgl1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies are copied and installed before the source, so a code
# change does not invalidate the (slow) dependency layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY pyproject.toml .

# Build the knowledge base at image build time so the running container
# does not need write access to do it, and startup is not delayed.
#
# Settings are validated at import and GROQ_API_KEY is required, but this
# step only runs the local embedding model - it never calls Groq. The
# placeholder is scoped to this one RUN so it is not baked into the image
# as an ENV layer; the real key is still required at runtime.
RUN GROQ_API_KEY=unused-at-build-time python -m app.rag.ingest

# The service ran as root. Give it an unprivileged user that owns only
# the directories it must write to.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/uploads /app/report_vectorstore /app/data_store \
    && chown -R appuser:appuser /app/uploads /app/report_vectorstore /app/data_store

# The service runs as appuser, but WORKDIR /app is root-owned, so the
# default DATABASE_URL of "sqlite:///./sessions.db" could not be created
# and the container died in init_db() at startup. Point it at the writable
# directory created above. Set DATABASE_URL to a Postgres URL to override.
ENV DATABASE_URL=sqlite:////app/data_store/sessions.db

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# gunicorn supervises uvicorn workers, so one crashed worker is replaced
# instead of taking the container down. --proxy-headers lets the app see
# the real client address behind a load balancer, which the rate limiter
# needs. WEB_CONCURRENCY tunes worker count per instance size.
CMD ["sh", "-c", "gunicorn app.api.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${WEB_CONCURRENCY:-2} \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile - \
    --forwarded-allow-ips '*'"]
