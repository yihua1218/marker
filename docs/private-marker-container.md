# Private Marker Container Setup

This service can run with Docker Compose or with `nerdctl compose` through the repository `Dockerfile`, `docker-compose.yml`, `.env`, and `.env.example` files.

## Files

- `Dockerfile`: builds the React frontend and installs the private Marker web service into a Python runtime image.
- `docker-compose.yml`: starts the web service, maps the configured port, mounts persistent data, and adds a health check.
- `.env.example`: versioned example configuration.
- `.env`: local runtime configuration, ignored by git.
- `private-marker-data/`: ignored persistent data directory mounted into `/app/data`.

## Configuration

Copy the example file and change the token before exposing the service:

```bash
cp .env.example .env
```

Important values:

- `PORT`: host and container web port. Default: `8765`.
- `HOST`: container bind host. Use `0.0.0.0` inside containers.
- `MARKER_WEB_TOKEN`: private web/API/MCP token.
- `MARKER_WEB_JOB_DIR`: container job storage path. Default: `/app/data/jobs`.
- `MARKER_WEB_FRONTEND_DIST`: built frontend path inside the image.
- `MARKER_WEB_AUTO_RESUME_JOBS`: resubmit retained queued/running jobs on startup. Default: `1`.
- `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME`: mounted cache paths for model/runtime reuse.
- `IMAGE_NAME`, `IMAGE_TAG`: local image name used by compose.

## Build and Run

Use Docker Compose if you are running Docker Desktop or another Docker-compatible runtime:

```bash
docker compose up --build
```

Use `nerdctl compose` if you are running Rancher Desktop with containerd:

```bash
nerdctl compose up --build
```

Both commands build the image from `Dockerfile` when needed, create the `private-marker-web` service, mount `./private-marker-data` into `/app/data`, and start the web server on the configured `PORT`.

Open:

```text
http://localhost:8765
```

Sign in with the `MARKER_WEB_TOKEN` value from `.env`.

## Build Only

To build the image without starting the service:

```bash
docker build -t localhost/private-marker-web:latest .
```

With `nerdctl`:

```bash
nerdctl build -t localhost/private-marker-web:latest .
```

If you changed `IMAGE_NAME` or `IMAGE_TAG` in `.env`, use those values in the image tag.

## Health Check

```bash
curl -fsS http://localhost:8765/health
```

Expected response:

```json
{
  "ok": true,
  "private_mode": true
}
```

## API Smoke Test

```bash
curl \
  -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  http://localhost:8765/api/info
```

## Upload Smoke Test

```bash
curl \
  -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  -F "file=@/path/to/document.pdf" \
  -F "output_format=markdown" \
  http://localhost:8765/jobs
```

## Stop

With Docker Compose:

```bash
docker compose down
```

With `nerdctl compose`:

```bash
nerdctl compose down
```

The retained jobs and model caches stay in `private-marker-data/`.

## Notes

- MPS/M1 GPU acceleration is not available inside the Linux container runtime. The container should be treated as a portable CPU service unless a Linux GPU runtime is configured.
- Keep the service private. Do not expose it publicly unless licensing, authentication, storage cleanup, upload limits, and network controls have been reviewed.
