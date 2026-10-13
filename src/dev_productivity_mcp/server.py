"""MCP server wiring: exposes the tools and two prompts to any MCP client."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from dev_productivity_mcp import __version__, tools
from dev_productivity_mcp.git import GitError, resolve_repo
from dev_productivity_mcp.github import GitHubError, pull_request_report
from dev_productivity_mcp.models import (
    BranchReport,
    CommitList,
    PullRequestReport,
    RepoOverview,
    TodoReport,
)

INSTRUCTIONS = """\
Read-only tools for understanding local git repositories and GitHub pull requests.
Pass `path` as an absolute path to a folder inside a git repository. Start with
repo_overview for an unfamiliar repository. None of these tools change anything.
"""

LOCAL = ToolAnnotations(read_only_hint=True, open_world_hint=False)
REMOTE = ToolAnnotations(read_only_hint=True, open_world_hint=True)

RepoPath = Annotated[str, Field(description="Absolute path to a folder inside a git repository")]


@contextmanager
def expected_errors() -> Iterator[None]:
    """Show anticipated failures (bad path, unknown ref, GitHub 404) to the assistant.

    MCP servers hide the text of unexpected exceptions; ToolError is the way to say
    "this failure is expected, pass the message on".
    """
    try:
        yield
    except (GitError, GitHubError) as exc:
        raise ToolError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Could not reach GitHub: {exc}") from exc


def create_server(allowed_roots: list[Path] | None = None) -> MCPServer:
    """Build the server. `allowed_roots` overrides DEV_MCP_ALLOWED_ROOTS (used in tests)."""
    server = MCPServer(
        name="dev-productivity",
        title="Developer productivity",
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    def repo(path: str) -> Path:
        return resolve_repo(path, allowed_roots)

    @server.tool(annotations=LOCAL)
    def repo_overview(path: RepoPath) -> RepoOverview:
        """Summarise a repository: branch, commit count, contributors, file types and tags."""
        with expected_errors():
            return tools.repo_overview(repo(path))

    @server.tool(annotations=LOCAL)
    def recent_commits(
        path: RepoPath,
        since_days: Annotated[int, Field(ge=0, le=365)] = 7,
        author: Annotated[str | None, Field(description="Name or email to filter by")] = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
    ) -> CommitList:
        """List recent commits with the files they changed and lines added or removed."""
        with expected_errors():
            return tools.recent_commits(repo(path), since_days, author, limit)

    @server.tool(annotations=LOCAL)
    def find_todos(
        path: RepoPath,
        tags: Annotated[
            list[str] | None, Field(description="Defaults to TODO, FIXME, HACK, XXX")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> TodoReport:
        """Find TODO/FIXME-style comments in tracked files, with file and line numbers."""
        with expected_errors():
            return tools.find_todos(repo(path), tuple(tags or tools.DEFAULT_TODO_TAGS), limit)

    @server.tool(annotations=LOCAL)
    def changelog(
        path: RepoPath,
        since_ref: Annotated[
            str | None, Field(description="Tag or commit to start from; defaults to latest tag")
        ] = None,
        until_ref: str = "HEAD",
    ) -> str:
        """Draft release notes in Markdown, grouped by Conventional Commit type."""
        with expected_errors():
            return tools.changelog(repo(path), since_ref, until_ref)

    @server.tool(annotations=LOCAL)
    def standup_report(
        path: RepoPath,
        author: Annotated[
            str | None, Field(description="Defaults to the repository's git user.name")
        ] = None,
        days: Annotated[int, Field(ge=1, le=14, description="Use 3 on a Monday")] = 1,
    ) -> str:
        """Summarise someone's recent commits, busiest files and open TODOs for a standup."""
        with expected_errors():
            return tools.standup_report(repo(path), author, days)

    @server.tool(annotations=LOCAL)
    def branch_health(
        path: RepoPath,
        stale_after_days: Annotated[int, Field(ge=1, le=365)] = 30,
    ) -> BranchReport:
        """Show local branches with commits ahead of/behind the main branch, flagging stale ones."""
        with expected_errors():
            return tools.branch_report(repo(path), stale_after_days)

    @server.tool(annotations=REMOTE)
    async def pull_requests(
        repo_name: Annotated[str, Field(description="GitHub repository as owner/name")],
        state: Literal["open", "closed", "all"] = "open",
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> PullRequestReport:
        """Summarise a GitHub repository's pull requests: age, author, draft status, reviewers."""
        with expected_errors():
            return await pull_request_report(repo_name, state, limit)

    @server.prompt()
    def daily_standup(path: str, author: str = "") -> str:
        """Prepare a short spoken standup update from recent commits."""
        who = f" for {author}" if author else ""
        return (
            f"Call standup_report for the repository at {path}{who}. Turn the result into a "
            "standup update of at most five bullet points: what was done, what is next "
            "(use the open TODOs), and any blockers. Plain language, no commit hashes."
        )

    @server.prompt()
    def release_notes(path: str, since_ref: str = "") -> str:
        """Turn the changelog into release notes for users."""
        since = f" since {since_ref}" if since_ref else ""
        return (
            f"Call changelog for the repository at {path}{since}. Rewrite it as release notes "
            "for users: lead with breaking changes, then features and fixes, explain each in "
            "one sentence, and leave out internal chores and tests."
        )

    return server


def main() -> None:
    """Run over stdio, which is how desktop MCP clients launch local servers."""
    create_server().run()


if __name__ == "__main__":
    main()
