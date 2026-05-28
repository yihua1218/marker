# Private Marker MCP Server

The private Marker MCP server exposes the private web API as MCP tools over stdio. It is intended for local AI agents that need to submit files to the private Marker web service, poll jobs, download archives, and delete retained jobs.

## Start The Web Service

```bash
MARKER_WEB_TOKEN=your-private-token .venv/bin/marker_private_web --host 127.0.0.1 --port 8765
```

## Start The MCP Server

```bash
MARKER_WEB_BASE_URL=http://127.0.0.1:8765 \
MARKER_WEB_TOKEN=your-private-token \
.venv/bin/marker_private_mcp
```

You can also run it directly:

```bash
MARKER_WEB_BASE_URL=http://127.0.0.1:8765 \
MARKER_WEB_TOKEN=your-private-token \
.venv/bin/python private_marker_mcp.py
```

## MCP Tools

- `marker_web_auth_status`
  - Checks authentication state.
- `marker_web_api_info`
  - Returns supported file formats, output formats, archive formats, and endpoint metadata.
- `marker_web_list_jobs`
  - Lists retained conversion jobs.
- `marker_web_get_job`
  - Gets one job by `job_id`.
- `marker_web_create_job`
  - Uploads a local file and starts conversion.
  - Arguments:
    - `file_path`
    - `output_format`: `markdown`, `json`, `html`, or `chunks`
- `marker_web_download_job`
  - Downloads a completed archive.
  - Arguments:
    - `job_id`
    - `archive_format`: `zip` or `tar.gz`
    - `destination_path`
- `marker_web_retry_job`
  - Retries a completed or failed job using its retained input file.
  - Arguments:
    - `job_id`
- `marker_web_delete_job`
  - Deletes a completed or failed job.

## Minimal JSON-RPC Smoke Test

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
| MARKER_WEB_BASE_URL=http://127.0.0.1:8765 MARKER_WEB_TOKEN=your-private-token .venv/bin/marker_private_mcp
```

## Example Tool Call

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "marker_web_create_job",
    "arguments": {
      "file_path": "/path/to/document.pdf",
      "output_format": "markdown"
    }
  }
}
```

## Security Notes

- Keep `MARKER_WEB_TOKEN` out of source control.
- Keep the web service private and access-controlled.
- Do not expose this MCP server to untrusted clients.
- The MCP server can read local files passed through `file_path`; only connect it to trusted AI agents.
