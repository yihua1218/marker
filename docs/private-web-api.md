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

## Supported Inputs

Supported upload extensions:

- `.pdf`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`
- `.pptx`
- `.docx`
- `.xlsx`
- `.html`, `.htm`
- `.epub`

## Supported Marker Output Formats

Use the `output_format` form field with one of:

- `markdown`
- `json`
- `html`
- `chunks`

The archive itself can be downloaded as:

- `zip`
- `tar.gz`

## Endpoints

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
  -F 'output_format=markdown' \
  http://127.0.0.1:8765/jobs
```

Response:

```json
{
  "id": "job-id",
  "original_filename": "document.pdf",
  "document_stem": "document",
  "output_format": "markdown",
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

A future MCP server can wrap this API with small tools:

- `marker_web_auth_status`
  - Input: none or `base_url`.
  - Output: authentication state.
- `marker_web_create_job`
  - Input: `base_url`, local file path, `output_format`.
  - Output: job object.
- `marker_web_get_job`
  - Input: `base_url`, `job_id`.
  - Output: job object.
- `marker_web_list_jobs`
  - Input: `base_url`.
  - Output: retained jobs.
- `marker_web_download_job`
  - Input: `base_url`, `job_id`, archive `format`, destination path.
  - Output: saved archive path.
- `marker_web_delete_job`
  - Input: `base_url`, `job_id`.
  - Output: deletion result.

The MCP server should read the token from an environment variable such as `MARKER_WEB_TOKEN` and send it as a Bearer token.

## Skill Plan

A Codex skill can provide a higher-level workflow:

1. Confirm the private Marker server base URL.
2. Confirm the source file path.
3. Choose `output_format`: `markdown`, `json`, `html`, or `chunks`.
4. Upload the file through `POST /jobs`.
5. Poll `GET /jobs/{job_id}` until completion.
6. Download the selected archive format.
7. Optionally delete the retained job if the user asks.

Suggested skill commands:

- "Convert this file with private Marker to Markdown."
- "Convert this PDF to JSON and download the zip."
- "List retained Marker conversion jobs."
- "Delete Marker job `<job_id>`."
