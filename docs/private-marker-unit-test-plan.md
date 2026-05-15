# Private Marker Unit Test Validation Plan

This plan defines the first unit-test path for the private Marker web API, MCP server, and Skill package. The goal is to protect the private conversion workflow without requiring a full OCR/model conversion during every local test run.

## Scope

- API module: `marker/scripts/private_web.py`
- MCP module: `marker/scripts/private_mcp.py`
- Root MCP launcher: `private_marker_mcp.py`
- Public API documentation: `docs/private-web-api.md`
- MCP documentation: `docs/private-marker-mcp.md`
- Skill documentation and example: `docs/private-marker-skill.md`, `docs/skills/private-marker-web/SKILL.md`

## First MVP Test Path

- Validate Traditional Chinese and Windows-sensitive filename handling.
- Validate upload format checks for supported inputs and rejected inputs.
- Validate archive creation, including Unicode package roots and image paths.
- Validate job metadata persistence and migration for older `job.json` files.
- Validate MCP tool schema coverage for all API-facing tools.
- Validate MCP JSON-RPC initialization, tool listing, tool call serialization, and unknown-tool errors.
- Validate that API, MCP, and Skill documentation contains the required operational sections.

## Unit-Test Checklist

- [x] API filename helpers preserve display names and provide ASCII-safe fallbacks.
- [x] API download `Content-Disposition` supports UTF-8 filenames with RFC 5987 `filename*`.
- [x] API upload validation accepts declared supported formats.
- [x] API upload validation rejects unsupported extensions and invalid PDF headers.
- [x] API archive generation preserves Traditional Chinese names inside `.zip` packages.
- [x] API job store persists and reloads completed jobs.
- [x] API job store migrates older metadata by filling default output format and display name.
- [x] MCP tool schema includes auth, API info, list, get, create, download, and delete tools.
- [x] MCP server responds to `initialize`.
- [x] MCP server responds to `tools/list`.
- [x] MCP server serializes successful `tools/call` results.
- [x] MCP server returns a structured error for unknown tools.
- [x] Skill and API documentation include required workflow, privacy, format, and boundary notes.

## First Test Command

Run from the project root with the project virtual environment:

```bash
.venv/bin/python -m pytest tests/private_web --cov=marker.scripts.private_web --cov=marker.scripts.private_mcp --cov-report=term-missing --cov-report=json:/private/tmp/private_marker_coverage.json
```

## Current Deliberate Exclusions

- Full Marker OCR/model conversion is not run in unit tests because it is slow and hardware-dependent.
- Browser/UI flows are not covered yet; they should be added with Vitest or Playwright.
- Live MCP upload/download against a running API server is not part of the unit-test suite.
- Skill behavior is validated as documentation and workflow coverage, not as an installed runtime integration.

## Next Coverage Targets

- Add FastAPI `TestClient` endpoint tests with `run_conversion` monkeypatched.
- Add tests for `GET /jobs/{id}/download` selecting older completed jobs.
- Add frontend tests for retained job selection and output-format submission.
- Add MCP integration smoke tests behind an explicit opt-in marker.
- Add a coverage threshold after endpoint tests raise coverage above the initial baseline.
