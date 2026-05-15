FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8765 \
    HOST=0.0.0.0 \
    MARKER_WEB_JOB_DIR=/app/data/jobs \
    MARKER_WEB_FRONTEND_DIST=/app/frontend/dist \
    HF_HOME=/app/data/huggingface \
    TORCH_HOME=/app/data/torch \
    XDG_CACHE_HOME=/app/data/cache

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      libffi8 \
      libglib2.0-0 \
      libgomp1 \
      libharfbuzz-subset0 \
      libjpeg62-turbo \
      libopenjp2-7 \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY marker ./marker
COPY private_marker_web.py private_marker_mcp.py ./

RUN python -m pip install --upgrade pip && \
    python -m pip install ".[full]" fastapi uvicorn python-multipart requests

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    mkdir -p /app/data/jobs /app/data/huggingface /app/data/torch /app/data/cache

EXPOSE 8765

ENTRYPOINT ["/usr/bin/tini", "--", "docker-entrypoint.sh"]
CMD ["marker_private_web"]
