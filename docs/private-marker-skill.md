# Private Marker Skill Guide

This document describes how an AI coding assistant skill should use the private Marker web API or MCP tools.

## When To Use

Use this skill when the user asks to:

- Convert a local PDF or supported document to Markdown, JSON, HTML, or chunks.
- List retained private Marker conversion jobs.
- Download a completed conversion archive.
- Delete a retained conversion job.
- Inspect supported private Marker API formats.

## Required Context

The skill needs:

- Private Marker web base URL, default `http://127.0.0.1:8765`.
- Private token from `MARKER_WEB_TOKEN`.
- Local source file path.
- Desired Marker output format: `markdown`, `json`, `html`, or `chunks`.
- Desired archive format: `zip` or `tar.gz`.

## Preferred MCP Flow

1. Call `marker_web_auth_status`.
2. If authentication fails, ask the user to start the private Marker web service or configure `MARKER_WEB_TOKEN`.
3. Call `marker_web_api_info` if supported formats are unclear.
4. Call `marker_web_create_job` with `file_path` and `output_format`.
5. Poll `marker_web_get_job` until `status` is `complete` or `failed`.
6. If complete, call `marker_web_download_job`.
7. If the user asks to clean up, call `marker_web_delete_job`.

## Fallback HTTP Flow

Use HTTP directly when MCP tools are unavailable:

```bash
curl \
  -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  -F "file=@/path/to/document.pdf" \
  -F "output_format=markdown" \
  http://127.0.0.1:8765/jobs
```

Poll:

```bash
curl -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  http://127.0.0.1:8765/jobs/<job-id>
```

Download:

```bash
curl -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  -o output.zip \
  "http://127.0.0.1:8765/jobs/<job-id>/download?format=zip"
```

## User-Facing Examples

- "Convert `/Users/me/report.pdf` to Markdown and download a zip."
- "Convert this DOCX to HTML with private Marker."
- "List my retained Marker jobs."
- "Download job `abc123` as tar.gz."
- "Delete failed Marker jobs."

## Boundaries

- Do not send files to any public service.
- Do not expose the private token.
- Do not delete jobs unless the user asks.
- Do not assume public or commercial deployment is licensed.
