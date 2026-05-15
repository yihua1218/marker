from pathlib import Path


def test_api_and_mcp_docs_exist_with_key_sections():
    root = Path(__file__).resolve().parents[2]

    api_doc = (root / "docs" / "private-web-api.md").read_text(encoding="utf-8")
    assert "GET /api/info" in api_doc
    assert "POST /jobs" in api_doc
    assert "Filename Handling" in api_doc

    mcp_doc = (root / "docs" / "private-marker-mcp.md").read_text(encoding="utf-8")
    assert "marker_web_create_job" in mcp_doc
    assert "JSON-RPC" in mcp_doc

    skill_doc = (root / "docs" / "private-marker-skill.md").read_text(encoding="utf-8")
    assert "Preferred MCP Flow" in skill_doc
    assert "marker_web_download_job" in skill_doc


def test_skill_example_contains_workflow_and_boundaries():
    root = Path(__file__).resolve().parents[2]
    skill = (root / "docs" / "skills" / "private-marker-web" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Workflow" in skill
    assert "Output Formats" in skill
    assert "Do not route documents to public endpoints" in skill
