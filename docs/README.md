# Private Marker Docs

Start here if you are working on the private Marker web service in this repository.

## Current Operator Docs

- [Container setup](./private-marker-container.md): build the image, start the web service with Docker Compose or `nerdctl compose`, run health checks, and stop the service.
- [Private web API](./private-web-api.md): authentication, supported formats, job endpoints, downloads, and deletion.
- [Private Marker MCP server](./private-marker-mcp.md): run the stdio MCP wrapper around the private web API.
- [Private Marker skill](./private-marker-skill.md): high-level agent workflow for submitting files, polling jobs, downloading archives, and deleting jobs.

## Current Chinese Docs

- [容器設定](./private-marker-container.zh-TW.md)
- [Private Web API 說明](./private-web-api.zh-TW.md)

## Chinese Planning And Reports

- [Unit test plan](./private-marker-unit-test-plan.zh-TW.md)
- [Coverage report](./private-marker-coverage-report.zh-TW.md)

## Planning And Reference Docs

- [PDF to Markdown web app plan](./pdf-to-markdown-web-app-plan.md)
- [PDF to Markdown web app plan, zh-TW](./pdf-to-markdown-web-app-plan.zh-TW.md)
- [Private Marker unit test plan](./private-marker-unit-test-plan.md)
- [Private Marker coverage report](./private-marker-coverage-report.md)

The planning files are retained as implementation history and follow-up notes. Prefer the current operator docs above when you need to run, test, or integrate the service.
