import json

from marker.scripts.private_mcp import MarkerWebClient, StdioMCPServer, tool_schema


def test_tool_schema_contains_required_tools():
    names = {tool["name"] for tool in tool_schema()}
    assert {
        "marker_web_auth_status",
        "marker_web_api_info",
        "marker_web_list_jobs",
        "marker_web_get_job",
        "marker_web_create_job",
        "marker_web_download_job",
        "marker_web_retry_job",
        "marker_web_delete_job",
    }.issubset(names)


def test_mcp_initialize_and_tools_list():
    server = StdioMCPServer(MarkerWebClient("http://127.0.0.1:1", "token"))

    init_response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_response["result"]["serverInfo"]["name"] == "private-marker-web"

    list_response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = {tool["name"] for tool in list_response["result"]["tools"]}
    assert "marker_web_create_job" in tool_names


def test_mcp_tool_call_serializes_handler_output():
    server = StdioMCPServer(MarkerWebClient("http://127.0.0.1:1", "token"))
    server.handlers["marker_web_api_info"] = lambda args: {"ok": True}

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "marker_web_api_info", "arguments": {}},
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload == {"ok": True}
    assert response["result"]["isError"] is False


def test_mcp_unknown_tool_returns_error():
    server = StdioMCPServer(MarkerWebClient("http://127.0.0.1:1", "token"))
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
    )
    assert response["error"]["code"] == -32603
