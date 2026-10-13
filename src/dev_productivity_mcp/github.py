"""Pull request summaries from the GitHub REST API (read-only)."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

import httpx

from dev_productivity_mcp.models import PullRequestInfo, PullRequestReport

API_URL = "https://api.github.com"
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class GitHubError(RuntimeError):
    """The GitHub API refused or failed a request."""


async def pull_request_report(
    repo: str,
    state: str = "open",
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
    token: str | None = None,
    now: datetime | None = None,
) -> PullRequestReport:
    if not _REPO.fullmatch(repo):
        raise GitHubError(f"{repo!r} should look like owner/name")
    if state not in {"open", "closed", "all"}:
        raise GitHubError("state must be open, closed or all")

    token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"state": state, "sort": "updated", "direction": "desc", "per_page": min(limit, 100)}

    owns_client = client is None
    client = client or httpx.AsyncClient(base_url=API_URL, timeout=15.0)
    try:
        response = await client.get(f"/repos/{repo}/pulls", params=params, headers=headers)
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 404:
        raise GitHubError(f"{repo} was not found. If it is private, set GITHUB_TOKEN.")
    if response.status_code in (401, 403):
        raise GitHubError(
            f"GitHub refused the request ({response.status_code}): check GITHUB_TOKEN"
        )
    response.raise_for_status()

    now = now or datetime.now(UTC)
    pulls = []
    for item in response.json()[:limit]:
        created = datetime.fromisoformat(item["created_at"])
        pulls.append(
            PullRequestInfo(
                number=item["number"],
                title=item["title"],
                author=(item.get("user") or {}).get("login", "unknown"),
                draft=bool(item.get("draft")),
                url=item["html_url"],
                created_at=created,
                updated_at=datetime.fromisoformat(item["updated_at"]),
                age_days=(now - created).days,
                labels=[label["name"] for label in item.get("labels", [])],
                requested_reviewers=[r["login"] for r in item.get("requested_reviewers", [])],
            )
        )
    return PullRequestReport(repo=repo, state=state, count=len(pulls), pull_requests=pulls)
