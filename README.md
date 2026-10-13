# dev-productivity-mcp

[![CI](https://github.com/Prakruthimanjunath20/dev-productivity-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Prakruthimanjunath20/dev-productivity-mcp/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Python%20SDK%202.x-6E56CF)

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants such as
Claude a set of **read-only developer-productivity tools**: understand an unfamiliar
repository, write a standup from yesterday's commits, draft release notes, find
forgotten TODOs, spot stale branches and summarise open pull requests.

Ask your assistant things like:

> *"Give me an overview of ~/code/payments-service."*
> *"Write my standup for ~/code/api, I was off Friday so cover three days."*
> *"Draft release notes for everything since v1.4.0."*
> *"Which branches in this repo are stale, and what PRs are waiting for review on acme/api?"*

## Tools

| Tool | What it returns |
| --- | --- |
| `repo_overview` | Branch, commit count, first/last commit dates, top contributors, file types, recent tags, uncommitted changes |
| `recent_commits` | Commits in the last *n* days (optionally by author) with files changed and lines added/removed |
| `standup_report` | Markdown standup: what you committed, your most-touched files, and open TODOs in those files |
| `changelog` | Markdown release notes since the latest tag, grouped by [Conventional Commit](https://www.conventionalcommits.org) type, breaking changes first |
| `find_todos` | `TODO` / `FIXME` / `HACK` / `XXX` comments with file and line, counted by tag |
| `branch_health` | Local branches with commits ahead/behind the main branch, flagging stale ones |
| `pull_requests` | A GitHub repository's PRs: age, author, draft status, labels, requested reviewers |

Structured tools return typed JSON (Pydantic models), so the assistant gets exact
numbers rather than parsing text. Two **prompts** are included as well:
`daily_standup` and `release_notes`.

## Safe by design

- **Read-only.** No tool writes, commits, pushes or deletes anything, and every tool
  is annotated `readOnlyHint` so clients can show that.
- **Folder allow-list.** Tools only open repositories inside `DEV_MCP_ALLOWED_ROOTS`
  (default: the folder the server starts in). Anything else is refused with a clear
  message the assistant can relay.
- **No shell.** git runs with an argument list and a timeout. Branch and tag names are
  validated, so a crafted value such as `--output=/some/file` cannot be passed to git
  as an option.
- **Expected errors are explained.** A wrong path, unknown tag or private repository
  comes back as a readable tool error, not a crash.

## Setup

Requires Python 3.11+, git and [uv](https://docs.astral.sh/uv/).

Add the server to your MCP client's configuration. For Claude Desktop that is
`claude_desktop_config.json`; other clients use the same `mcpServers` shape:

```json
{
  "mcpServers": {
    "dev-productivity": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/Prakruthimanjunath20/dev-productivity-mcp",
        "dev-productivity-mcp"
      ],
      "env": {
        "DEV_MCP_ALLOWED_ROOTS": "/Users/you/code",
        "GITHUB_TOKEN": "optional, for private repos and higher rate limits"
      }
    }
  }
}
```

| Variable | Purpose |
| --- | --- |
| `DEV_MCP_ALLOWED_ROOTS` | Folders the tools may read, separated by `:` (`;` on Windows). Defaults to the current folder. |
| `GITHUB_TOKEN` | Optional. A read-only token for private repositories and the higher API rate limit. |

To try it from a clone instead:

```bash
git clone https://github.com/Prakruthimanjunath20/dev-productivity-mcp.git
cd dev-productivity-mcp
uv sync
uv run dev-productivity-mcp          # speaks MCP over stdio
```

## How it is built

```text
src/dev_productivity_mcp/
  server.py   MCP wiring: tools, prompts, annotations, error handling (MCP Python SDK 2.x MCPServer)
  tools.py    The git tools as plain functions, testable without MCP
  git.py      Folder allow-list, safe git runner and ref validation
  github.py   Async pull request summaries over the GitHub REST API (httpx)
  models.py   Pydantic models for every structured result
tests/        23 tests, including end-to-end calls through a real MCP client
```

The tests build a throwaway git repository with known authors, dates, tags, TODOs and
a stale branch, then check each tool against it, both directly and through an
in-process MCP client. GitHub calls are tested against a mocked transport, so the
suite needs no network.

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Acknowledgements

The idea grew out of a shared project idea with
[@shashanksuresh18](https://github.com/shashanksuresh18)
([dev-productivity-agents-mcp](https://github.com/shashanksuresh18/dev-productivity-agents-mcp)).
This repository is an independent implementation.

## Author

**Prakruthi Manjunath** · [GitHub](https://github.com/Prakruthimanjunath20) ·
[LinkedIn](https://www.linkedin.com/in/prakruthi21)

Licensed under the [MIT License](LICENSE).
