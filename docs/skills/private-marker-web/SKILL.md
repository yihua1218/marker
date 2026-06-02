# Private Marker Web

Use this skill when a user wants to convert local documents through their private Marker web service, inspect retained jobs, download conversion archives, or delete completed/failed jobs.

## Requirements

- The private Marker web server is running, usually at `http://127.0.0.1:8765`.
- `MARKER_WEB_TOKEN` is available to the agent environment or provided by the user.
- Prefer MCP tools when available:
  - `marker_web_auth_status`
  - `marker_web_api_info`
  - `marker_web_create_job`
  - `marker_web_get_job`
  - `marker_web_list_jobs`
  - `marker_web_download_job`
  - `marker_web_delete_job`

## Workflow

1. Check authentication with `marker_web_auth_status`.
2. Confirm the local source file path exists.
3. Ask for conversion engine only if the user did not specify one. Default to `marker`; use `docling` when requested, and `auto` when the user wants fallback routing.
4. Ask for output format only if the user did not specify one. Default to `markdown`.
5. Create a conversion job with `marker_web_create_job`, passing `conversion_engine`.
6. Poll with `marker_web_get_job` until `complete` or `failed`.
7. Download the archive with `marker_web_download_job` when complete.
8. Report the saved archive path and job id.
9. Delete a job only when the user explicitly asks.

## Conversion Engines

- `marker`
- `docling`
- `auto`

## Output Formats

- `markdown`
- `json`
- `html`
- `chunks`

Docling supports `markdown`, `json`, and `html`; it does not support `chunks`.
Auto supports `markdown` only and currently expects PDF input.

## Archive Formats

- `zip`
- `tar.gz`

## Fallback

If MCP tools are unavailable, use the private HTTP API documented in `docs/private-web-api.md`.

## Safety

This service is intended for private, personal, non-commercial use. Do not route documents to public endpoints, and do not expose `MARKER_WEB_TOKEN`.
