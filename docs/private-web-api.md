# Private Marker Web API

This document describes the private web API used by the Marker conversion UI.

The hosted service is intended for private, personal, non-commercial use. Do not expose these endpoints publicly without a separate license and security review.

## Authentication

Set `MARKER_WEB_TOKEN` before starting the server:

```bash
MARKER_WEB_TOKEN=your-private-token .venv/bin/marker_private_web --host 127.0.0.1 --port 8765
```

Clients can authenticate in either of two ways:

- Browser cookie: `POST /auth` with form field `token`.
- API token: `Authorization: Bearer <MARKER_WEB_TOKEN>`.

If `MARKER_WEB_TOKEN` is not set, the server only allows loopback access.

## Job Recovery and Logging

Job metadata and uploaded input files are retained under `MARKER_WEB_JOB_DIR`. On startup, jobs that were `queued` or `running` are moved back to `queued` and, by default, submitted to the worker pool again. Set `MARKER_WEB_AUTO_RESUME_JOBS=0` only if you want to inspect or retry those jobs manually.

The server logs job load, requeue, submit, conversion start, conversion finish, archive creation, missing input, retry, and failure events through the Marker logger. These logs include the job id and paths needed to debug stuck or failed work.

## Supported Inputs

Supported upload extensions:

- `.pdf`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`
- `.pptx`
- `.docx`
- `.xlsx`
- `.html`, `.htm`
- `.epub`

## Conversion Engines and Output Formats

Use the `conversion_engine` form field with one of:

- `marker`: the existing Marker pipeline.
- `docling`: IBM Docling `DocumentConverter`. This is an optional dependency; install `marker-pdf[docling]` or `marker-pdf[full]` before submitting Docling jobs.
- `auto`: PDF-to-Markdown routing pipeline. It runs Docling with OCR first, evaluates the Markdown quality, and falls back to Marker if the quality gate fails.

Docling's current official Python API converts with `DocumentConverter().convert(source).document` and exports through methods such as `export_to_markdown()`.

For Marker, use the `output_format` form field with one of:

- `markdown`
- `json`
- `html`
- `chunks`

For Docling, use one of:

- `markdown`
- `json`
- `html`

For Auto, use:

- `markdown`

The archive itself can be downloaded as:

- `zip`
- `tar.gz`

## Filename Handling

The service separates filenames into three forms:

- `original_filename`: the browser-provided filename, preserved for display.
- `display_stem`: a Unicode NFC-normalized, Windows-safe display name. Traditional Chinese filenames are preserved here.
- `document_stem`: an internal ASCII storage slug with the job id prefix appended to avoid collisions.

Downloads use an RFC 5987 `Content-Disposition` header with both `filename` and `filename*`, so modern browsers on Windows should receive Traditional Chinese filenames correctly.

Archive contents use `display_stem` as the package root and output filename. For example, uploading `測試文件.pdf` and choosing Markdown produces archive entries like:

```text
測試文件/
  測試文件.md
  metadata.json
  images/
```

Characters invalid on Windows (`<>:"/\\|?*` and control characters) are replaced with `-`, and reserved DOS device names fall back to `document`.

## Endpoints

### `GET /api/info`

Returns machine-readable API metadata, including supported input extensions, output formats, archive formats, and endpoint names.

### `GET /openapi.json`

Returns FastAPI's OpenAPI schema for the private web service.

### `GET /auth/status`

Returns the current authentication state.

```json
{
  "authenticated": true,
  "token_required": true,
  "loopback_only": false
}
```

### `POST /auth`

Signs in a browser session.

Request:

```bash
curl -c cookies.txt -F 'token=your-private-token' http://127.0.0.1:8765/auth
```

Response:

```json
{
  "authenticated": true
}
```

### `POST /auth/logout`

Clears the browser session cookie.

### `POST /jobs`

Uploads a file and starts a conversion job.

Request:

```bash
curl \
  -H 'Authorization: Bearer your-private-token' \
  -F 'file=@/path/to/document.pdf' \
  -F 'conversion_engine=auto' \
  -F 'output_format=markdown' \
  http://127.0.0.1:8765/jobs
```

Response:

```json
{
  "id": "job-id",
  "original_filename": "測試文件.pdf",
  "document_stem": "document-jobprefix",
  "display_stem": "測試文件",
  "output_format": "markdown",
  "conversion_engine": "auto",
  "status": "queued",
  "stage": "Queued",
  "progress": 0,
  "created_at": 1778790266.2,
  "updated_at": 1778790266.2,
  "output_dir": null,
  "zip_path": null,
  "targz_path": null,
  "error": null
}
```

### `GET /jobs`

Lists retained jobs.

```bash
curl -H 'Authorization: Bearer your-private-token' http://127.0.0.1:8765/jobs
```

### `GET /jobs/{job_id}`

Returns a single job status. Poll this endpoint until `status` is `complete` or `failed`.

### `POST /jobs/{job_id}/retry`

Requeues a completed or failed job using the retained input file. Jobs that are already `queued` or `running` return `409`.

### `GET /jobs/{job_id}/download?format=zip`

Downloads the generated archive.

Supported `format` values:

- `zip`
- `tar.gz`

Example:

```bash
curl \
  -H 'Authorization: Bearer your-private-token' \
  -o document.zip \
  'http://127.0.0.1:8765/jobs/job-id/download?format=zip'
```

### `DELETE /jobs/{job_id}`

Deletes a completed or failed job and removes its uploaded file, output files, and archives.

Running jobs cannot be deleted.

## MCP Tool Plan

The implemented stdio MCP server wraps this API with these tools:

- `marker_web_auth_status`
  - Input: none or `base_url`.
  - Output: authentication state.
- `marker_web_create_job`
  - Input: `base_url`, local file path, `output_format`, `conversion_engine`.
  - Output: job object.
- `marker_web_get_job`
  - Input: `base_url`, `job_id`.
  - Output: job object.
- `marker_web_list_jobs`
  - Input: `base_url`.
  - Output: retained jobs.
- `marker_web_retry_job`
  - Input: `base_url`, `job_id`.
  - Output: requeued job object.
- `marker_web_download_job`
  - Input: `base_url`, `job_id`, archive `format`, destination path.
  - Output: saved archive path.
- `marker_web_delete_job`
  - Input: `base_url`, `job_id`.
  - Output: deletion result.

The MCP server should read the token from an environment variable such as `MARKER_WEB_TOKEN` and send it as a Bearer token.

See [private-marker-mcp.md](./private-marker-mcp.md) for startup and JSON-RPC examples.

## Skill Plan

A Codex skill can provide a higher-level workflow:

1. Confirm the private Marker server base URL.
2. Confirm the source file path.
3. Choose `conversion_engine`: `marker`, `docling`, or `auto`.
4. Choose `output_format`: `markdown`, `json`, `html`, or `chunks`. Docling does not support `chunks`; Auto supports Markdown only.
5. Upload the file through `POST /jobs`.
6. Poll `GET /jobs/{job_id}` until completion.
7. Download the selected archive format.
8. Optionally delete the retained job if the user asks.

Suggested skill commands:

- "Convert this file with private Marker to Markdown."
- "Use Docling to convert this PDF to Markdown."
- "Use Auto mode to convert this PDF and fall back to Marker if Docling output looks broken."
- "Convert this PDF to JSON and download the zip."
- "List retained Marker conversion jobs."
- "Delete Marker job `<job_id>`."

See [private-marker-skill.md](./private-marker-skill.md) and [skills/private-marker-web/SKILL.md](./skills/private-marker-web/SKILL.md).
