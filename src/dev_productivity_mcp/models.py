"""Structured results returned by the tools (MCP clients receive them as JSON)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Contributor(BaseModel):
    name: str
    email: str
    commits: int


class FileTypeCount(BaseModel):
    extension: str
    files: int


class RepoOverview(BaseModel):
    name: str
    path: str
    branch: str
    head: str
    total_commits: int
    first_commit: datetime | None
    last_commit: datetime | None
    uncommitted_changes: int
    contributors: list[Contributor]
    file_types: list[FileTypeCount]
    recent_tags: list[str]


class CommitInfo(BaseModel):
    hash: str
    author: str
    email: str
    date: datetime
    subject: str
    files: list[str]
    insertions: int
    deletions: int


class CommitList(BaseModel):
    since_days: int
    author: str | None
    count: int
    commits: list[CommitInfo]


class TodoItem(BaseModel):
    path: str
    line: int
    tag: str
    text: str


class TodoReport(BaseModel):
    total: int
    by_tag: dict[str, int]
    truncated: bool
    items: list[TodoItem]


class BranchInfo(BaseModel):
    name: str
    current: bool
    last_commit: datetime
    last_author: str
    ahead: int
    behind: int
    stale: bool


class BranchReport(BaseModel):
    base_branch: str
    stale_after_days: int
    branches: list[BranchInfo]


class PullRequestInfo(BaseModel):
    number: int
    title: str
    author: str
    draft: bool
    url: str
    created_at: datetime
    updated_at: datetime
    age_days: int
    labels: list[str]
    requested_reviewers: list[str]


class PullRequestReport(BaseModel):
    repo: str
    state: str
    count: int
    pull_requests: list[PullRequestInfo]
