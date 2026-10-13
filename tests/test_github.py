from datetime import UTC, datetime

import httpx
import pytest

from dev_productivity_mcp.github import API_URL, GitHubError, pull_request_report

PULLS = [
    {
        "number": 42,
        "title": "Add search endpoint",
        "user": {"login": "prakruthi"},
        "draft": False,
        "html_url": "https://github.com/acme/app/pull/42",
        "created_at": "2026-10-01T09:00:00Z",
        "updated_at": "2026-10-10T09:00:00Z",
        "labels": [{"name": "enhancement"}],
        "requested_reviewers": [{"login": "alex"}],
    }
]


def client_for(status: int, payload, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(base_url=API_URL, transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_pull_request_report():
    seen = []
    async with client_for(200, PULLS, seen) as client:
        report = await pull_request_report(
            "acme/app", client=client, token="t0ken", now=datetime(2026, 10, 13, 12, tzinfo=UTC)
        )
    pr = report.pull_requests[0]
    assert (report.count, pr.number, pr.author, pr.age_days) == (1, 42, "prakruthi", 12)
    assert pr.labels == ["enhancement"] and pr.requested_reviewers == ["alex"]
    request = seen[0]
    assert request.url.path == "/repos/acme/app/pulls"
    assert request.url.params["state"] == "open"
    assert request.headers["Authorization"] == "Bearer t0ken"


@pytest.mark.anyio
async def test_not_found_explains_private_repos():
    async with client_for(404, {"message": "Not Found"}, []) as client:
        with pytest.raises(GitHubError, match="GITHUB_TOKEN"):
            await pull_request_report("acme/private", client=client, token="")


@pytest.mark.anyio
@pytest.mark.parametrize("repo", ["acme", "acme/app/extra", "../etc/passwd"])
async def test_rejects_malformed_repo_names(repo):
    with pytest.raises(GitHubError):
        await pull_request_report(repo, token="")
