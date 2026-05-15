# Private Marker Unit-Test Coverage Report

Generated after the first unit-test run for the API, MCP, and Skill documentation work.

## Test Run

- Date: 2026-05-15
- Environment: project `.venv`
- Command:

```bash
.venv/bin/python -m pytest tests/private_web --cov=marker.scripts.private_web --cov=marker.scripts.private_mcp --cov-report=term-missing --cov-report=json:/private/tmp/private_marker_coverage.json
```

## Result

- Test files: `tests/private_web/test_private_web_api.py`, `tests/private_web/test_private_mcp.py`, `tests/private_web/test_private_marker_docs.py`
- Test count: 11
- Passed: 11
- Failed: 0
- Runtime: 0.34 seconds
- Coverage JSON: `/private/tmp/private_marker_coverage.json`

## Coverage Summary

| Module | Statements | Missed | Coverage |
| --- | ---: | ---: | ---: |
| `marker/scripts/private_web.py` | 305 | 139 | 54% |
| `marker/scripts/private_mcp.py` | 104 | 50 | 52% |
| Total | 409 | 189 | 54% |

## Covered Behaviors

- Traditional Chinese filename display handling.
- Windows reserved-name and invalid-character handling.
- UTF-8 download filename support through `Content-Disposition`.
- Upload validation for supported formats and invalid inputs.
- Unicode archive root and image path preservation.
- Job metadata persistence and migration defaults.
- MCP tool registration for API-facing actions.
- MCP `initialize`, `tools/list`, successful `tools/call`, and unknown-tool error handling.
- API, MCP, and Skill documentation key-section checks.

## Known Gaps

- Full Marker conversion is not covered by unit tests.
- FastAPI route tests are still pending.
- Frontend job retention and download selection behavior are not covered by automated UI tests yet.
- MCP live API calls are not part of the unit-test suite.
- Skill coverage confirms documentation structure, not runtime execution by an agent.

## Recommended Next Step

Add endpoint-level tests with FastAPI `TestClient` and a monkeypatched conversion runner. That should raise confidence in `/jobs`, `/jobs/{id}`, `/jobs/{id}/download`, and delete behavior without invoking the heavy conversion pipeline.
