"""End-to-end: a real MCP client talking to the server in-process."""

import pytest
from mcp import Client

from dev_productivity_mcp.server import create_server

EXPECTED_TOOLS = {
    "repo_overview",
    "recent_commits",
    "find_todos",
    "changelog",
    "standup_report",
    "branch_health",
    "pull_requests",
}


@pytest.mark.anyio
async def test_lists_read_only_tools(repo):
    async with Client(create_server([repo.parent])) as client:
        listed = (await client.list_tools()).tools
    assert {t.name for t in listed} == EXPECTED_TOOLS
    assert all(t.annotations and t.annotations.read_only_hint for t in listed)


@pytest.mark.anyio
async def test_repo_overview_returns_structured_data(repo):
    async with Client(create_server([repo.parent])) as client:
        result = await client.call_tool("repo_overview", {"path": str(repo)})
    assert not result.is_error
    assert result.structured_content["total_commits"] == 5
    assert result.structured_content["branch"] == "main"


@pytest.mark.anyio
async def test_markdown_tool(repo):
    async with Client(create_server([repo.parent])) as client:
        result = await client.call_tool("changelog", {"path": str(repo)})
    assert "## Changes since v0.1.0" in result.content[0].text


@pytest.mark.anyio
async def test_disallowed_path_is_an_error_not_a_crash(repo, tmp_path):
    async with Client(create_server([tmp_path / "only-here"])) as client:
        result = await client.call_tool("repo_overview", {"path": str(repo)})
    assert result.is_error
    assert "outside the allowed folders" in result.content[0].text


@pytest.mark.anyio
async def test_prompts(repo):
    async with Client(create_server([repo.parent])) as client:
        names = {p.name for p in (await client.list_prompts()).prompts}
        prompt = await client.get_prompt("daily_standup", {"path": str(repo)})
    assert names == {"daily_standup", "release_notes"}
    assert "standup_report" in prompt.messages[0].content.text
