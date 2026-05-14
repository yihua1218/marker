import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import click
import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT = 30


class MarkerWebClient:
    def __init__(self, base_url: str, token: str | None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def request(self, method: str, path: str, **kwargs) -> Any:
        headers = kwargs.pop("headers", {})
        headers = {**self.headers(), **headers}
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=kwargs.pop("timeout", DEFAULT_TIMEOUT),
            **kwargs,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def auth_status(self) -> Any:
        return self.request("GET", "/auth/status")

    def api_info(self) -> Any:
        return self.request("GET", "/api/info")

    def list_jobs(self) -> Any:
        return self.request("GET", "/jobs")

    def get_job(self, job_id: str) -> Any:
        return self.request("GET", f"/jobs/{job_id}")

    def delete_job(self, job_id: str) -> Any:
        return self.request("DELETE", f"/jobs/{job_id}")

    def create_job(self, file_path: str, output_format: str = "markdown") -> Any:
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        with path.open("rb") as file_obj:
            response = requests.post(
                f"{self.base_url}/jobs",
                headers=self.headers(),
                files={"file": (path.name, file_obj)},
                data={"output_format": output_format},
                timeout=DEFAULT_TIMEOUT,
            )
        response.raise_for_status()
        return response.json()

    def download_job(self, job_id: str, archive_format: str, destination_path: str) -> Any:
        destination = Path(destination_path).expanduser()
        if destination.is_dir():
            suffix = "zip" if archive_format == "zip" else "tar.gz"
            destination = destination / f"{job_id}.{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(
            f"{self.base_url}/jobs/{job_id}/download",
            headers=self.headers(),
            params={"format": archive_format},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        destination.write_bytes(response.content)
        return {"saved_to": str(destination), "bytes": len(response.content)}


def tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "marker_web_auth_status",
            "description": "Check whether the private Marker web API is authenticated.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "marker_web_api_info",
            "description": "Return supported formats and endpoint metadata for the private Marker web API.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "marker_web_list_jobs",
            "description": "List retained Marker conversion jobs.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "marker_web_get_job",
            "description": "Get one Marker conversion job by id.",
            "inputSchema": {
                "type": "object",
                "required": ["job_id"],
                "properties": {"job_id": {"type": "string"}},
            },
        },
        {
            "name": "marker_web_create_job",
            "description": "Upload a local file to the private Marker web API and start a conversion job.",
            "inputSchema": {
                "type": "object",
                "required": ["file_path"],
                "properties": {
                    "file_path": {"type": "string"},
                    "output_format": {
                        "type": "string",
                        "enum": ["markdown", "json", "html", "chunks"],
                        "default": "markdown",
                    },
                },
            },
        },
        {
            "name": "marker_web_download_job",
            "description": "Download a completed Marker conversion archive.",
            "inputSchema": {
                "type": "object",
                "required": ["job_id", "destination_path"],
                "properties": {
                    "job_id": {"type": "string"},
                    "archive_format": {
                        "type": "string",
                        "enum": ["zip", "tar.gz"],
                        "default": "zip",
                    },
                    "destination_path": {"type": "string"},
                },
            },
        },
        {
            "name": "marker_web_delete_job",
            "description": "Delete a completed or failed Marker conversion job.",
            "inputSchema": {
                "type": "object",
                "required": ["job_id"],
                "properties": {"job_id": {"type": "string"}},
            },
        },
    ]


class StdioMCPServer:
    def __init__(self, client: MarkerWebClient):
        self.client = client
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "marker_web_auth_status": lambda args: self.client.auth_status(),
            "marker_web_api_info": lambda args: self.client.api_info(),
            "marker_web_list_jobs": lambda args: self.client.list_jobs(),
            "marker_web_get_job": lambda args: self.client.get_job(args["job_id"]),
            "marker_web_create_job": lambda args: self.client.create_job(
                args["file_path"], args.get("output_format", "markdown")
            ),
            "marker_web_download_job": lambda args: self.client.download_job(
                args["job_id"], args.get("archive_format", "zip"), args["destination_path"]
            ),
            "marker_web_delete_job": lambda args: self.client.delete_job(args["job_id"]),
        }

    def run(self):
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = self.handle(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as exc:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(exc)},
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")

        if method == "notifications/initialized":
            return None

        try:
            match method:
                case "initialize":
                    result = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "private-marker-web", "version": "0.1.0"},
                    }
                case "tools/list":
                    result = {"tools": tool_schema()}
                case "tools/call":
                    params = request.get("params", {})
                    name = params.get("name")
                    arguments = params.get("arguments") or {}
                    if name not in self.handlers:
                        raise ValueError(f"Unknown tool: {name}")
                    output = self.handlers[name](arguments)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(output, indent=2, ensure_ascii=False),
                            }
                        ],
                        "isError": False,
                    }
                case _:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(exc)},
            }

        return {"jsonrpc": "2.0", "id": request_id, "result": result}


@click.command()
@click.option("--base-url", default=None, help="Private Marker web base URL")
@click.option("--token", default=None, help="Private Marker web token")
def private_mcp_cli(base_url: str | None, token: str | None):
    client = MarkerWebClient(
        base_url or os.environ.get("MARKER_WEB_BASE_URL", DEFAULT_BASE_URL),
        token or os.environ.get("MARKER_WEB_TOKEN"),
    )
    StdioMCPServer(client).run()
