# The Salix API.
#
# Nothing here is exposed to the internet directly: only Next talks to this
# container, because Next is what holds the shared key. See docker-compose.yml.

FROM python:3.12-slim

# curl for the container healthcheck; nothing else is needed at runtime, and
# the layer is dropped from the image size that matters by being early and
# stable.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first, so a code change does not reinstall the world.
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    # Postgres and OSS are optional at the code level and required for any
    # deployment with more than one process or real audio. Installed here so
    # switching to them is a change of environment variable, not of image.
    && pip install --no-cache-dir asyncpg oss2

COPY api/ ./
# The seed corpus builds the demo database; it imports salix, so it lives
# beside it rather than inside it.
COPY seed/ /app/seed/

# Recordings and the SQLite file. Mounted as a volume in compose -- without
# that, every redeploy would start with an empty database.
RUN mkdir -p /data/audio
ENV SALIX_STORAGE_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/ready || exit 1

# One worker by default. The workload is I/O-bound on model calls, and the
# in-process rate limiter counts per worker -- raise this and the limits
# multiply by the same number.
CMD ["uvicorn", "salix.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
