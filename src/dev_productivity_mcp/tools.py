"""The git-based tools. Plain functions, so they can be tested without an MCP client."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from dev_productivity_mcp.git import GitError, check_ref, run_git
from dev_productivity_mcp.models import (
    BranchInfo,
    BranchReport,
    CommitInfo,
    CommitList,
    Contributor,
    FileTypeCount,
    RepoOverview,
    TodoItem,
    TodoReport,
)

DEFAULT_TODO_TAGS = ("TODO", "FIXME", "HACK", "XXX")
_RECORD, _FIELD = "\x1e", "\x1f"


def _parse_date(text: str) -> datetime:
    return datetime.fromisoformat(text.strip())


# --- repo overview ---------------------------------------------------------------


def repo_overview(repo: Path, top_contributors: int = 10) -> RepoOverview:
    try:
        head = run_git(repo, "rev-parse", "--short", "HEAD").strip()
    except GitError as exc:
        raise GitError(f"{repo.name} has no commits yet") from exc

    contributors = []
    for line in run_git(repo, "shortlog", "-sne", "HEAD").splitlines()[:top_contributors]:
        count, _, who = line.strip().partition("\t")
        name, _, email = who.rpartition(" <")
        contributors.append(Contributor(name=name, email=email.rstrip(">"), commits=int(count)))

    extensions = Counter(
        PurePosixPath(f).suffix.lower() or "(none)" for f in run_git(repo, "ls-files").splitlines()
    )
    roots = run_git(repo, "log", "--max-parents=0", "--format=%aI", "HEAD").split()
    last = run_git(repo, "log", "-1", "--format=%cI").strip()

    return RepoOverview(
        name=repo.name,
        path=str(repo),
        branch=run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        head=head,
        total_commits=int(run_git(repo, "rev-list", "--count", "HEAD")),
        first_commit=min(_parse_date(r) for r in roots) if roots else None,
        last_commit=_parse_date(last) if last else None,
        uncommitted_changes=len(run_git(repo, "status", "--porcelain").splitlines()),
        contributors=contributors,
        file_types=[FileTypeCount(extension=e, files=n) for e, n in extensions.most_common(8)],
        recent_tags=run_git(repo, "tag", "--sort=-creatordate").split()[:5],
    )


# --- commits ---------------------------------------------------------------------


def recent_commits(
    repo: Path,
    since_days: int = 7,
    author: str | None = None,
    limit: int = 50,
    include_merges: bool = False,
) -> CommitList:
    args = [
        "log",
        f"--since={max(since_days, 0)} days ago",
        f"--max-count={max(1, min(limit, 500))}",
        "--numstat",
        f"--format={_RECORD}%H{_FIELD}%an{_FIELD}%ae{_FIELD}%aI{_FIELD}%s",
    ]
    if author:
        args.append(f"--author={author}")
    if not include_merges:
        args.append("--no-merges")

    commits: list[CommitInfo] = []
    for record in run_git(repo, *args).split(_RECORD)[1:]:
        header, *stats = record.strip("\n").split("\n")
        sha, name, email, date, subject = header.split(_FIELD, 4)
        files, added, removed = [], 0, 0
        for line in filter(None, stats):
            plus, minus, path = line.split("\t", 2)
            files.append(path)
            added += int(plus) if plus.isdigit() else 0  # "-" for binary files
            removed += int(minus) if minus.isdigit() else 0
        commits.append(
            CommitInfo(
                hash=sha[:10],
                author=name,
                email=email,
                date=_parse_date(date),
                subject=subject,
                files=files[:50],
                insertions=added,
                deletions=removed,
            )
        )
    return CommitList(since_days=since_days, author=author, count=len(commits), commits=commits)


# --- TODOs -----------------------------------------------------------------------


def find_todos(
    repo: Path, tags: tuple[str, ...] | list[str] = DEFAULT_TODO_TAGS, limit: int = 100
) -> TodoReport:
    tags = tuple(tags) or DEFAULT_TODO_TAGS
    if not all(re.fullmatch(r"[A-Za-z]{2,20}", t) for t in tags):
        raise GitError("Tags must be single words such as TODO or FIXME")
    output = run_git(
        repo, "grep", "-n", "-I", "-z", "-w", "-E", "-e", "|".join(tags), ok_codes=(0, 1)
    )

    matcher = re.compile(rf"\b({'|'.join(tags)})\b[\s:(\-]*")
    items: list[TodoItem] = []
    for line in output.splitlines():
        path, line_no, content = line.split("\0", 2)
        match = matcher.search(content)
        if not match:
            continue
        text = content[match.end() :].strip().rstrip("*/-# ").strip() or content.strip()
        items.append(TodoItem(path=path, line=int(line_no), tag=match.group(1), text=text[:200]))

    limit = max(1, limit)
    return TodoReport(
        total=len(items),
        by_tag=dict(Counter(i.tag for i in items).most_common()),
        truncated=len(items) > limit,
        items=items[:limit],
    )


# --- changelog -------------------------------------------------------------------

_CONVENTIONAL = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<desc>.+)"
)
_SECTIONS = {
    "feat": "Features",
    "fix": "Bug fixes",
    "perf": "Performance",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "build": "Build and CI",
    "ci": "Build and CI",
    "chore": "Chores",
}
_SECTION_ORDER = ["Breaking changes", *dict.fromkeys(_SECTIONS.values()), "Other changes"]


def changelog(repo: Path, since_ref: str | None = None, until_ref: str = "HEAD") -> str:
    """Markdown release notes grouped by Conventional Commit type."""
    until_ref = check_ref(until_ref)
    if since_ref:
        since_ref = check_ref(since_ref)
    else:
        # Latest tag *before* until_ref, so notes for a freshly tagged release still
        # cover that release. Fails on the first commit or with no tags: use all history.
        try:
            since_ref = run_git(repo, "describe", "--tags", "--abbrev=0", f"{until_ref}^").strip()
        except GitError:
            since_ref = None
    revision = f"{since_ref}..{until_ref}" if since_ref else until_ref

    log = run_git(repo, "log", "--no-merges", f"--format=%h{_FIELD}%s{_FIELD}%an", revision)
    sections: dict[str, list[str]] = {}
    count = 0
    for line in filter(None, log.splitlines()):
        sha, subject, author = line.split(_FIELD, 2)
        count += 1
        match = _CONVENTIONAL.match(subject)
        if match:
            scope = f"**{match['scope']}:** " if match["scope"] else ""
            entry = f"- {scope}{match['desc']} ({sha}, {author})"
            section = _SECTIONS.get(match["type"], "Other changes")
            if match["bang"]:
                sections.setdefault("Breaking changes", []).append(entry)
        else:
            entry, section = f"- {subject} ({sha}, {author})", "Other changes"
        sections.setdefault(section, []).append(entry)

    title = f"since {since_ref}" if since_ref else "(full history)"
    if not count:
        return f"## Changes {title}\n\nNo commits in {revision}."
    lines = [f"## Changes {title}", "", f"{count} commit{'s' if count != 1 else ''}."]
    for name in _SECTION_ORDER:
        if name in sections:
            lines += ["", f"### {name}", *sections[name]]
    return "\n".join(lines)


# --- standup ---------------------------------------------------------------------


def standup_report(repo: Path, author: str | None = None, days: int = 1) -> str:
    """Markdown summary of what someone committed recently, for a daily standup."""
    if author is None:
        author = run_git(repo, "config", "user.name", ok_codes=(0, 1)).strip() or None
    commits = recent_commits(repo, since_days=days, author=author, limit=200).commits
    who = author or "everyone"
    period = "day" if days == 1 else f"{days} days"
    heading = f"### Standup: {who}, last {period} in {repo.name}"
    if not commits:
        hint = " (on a Monday, try days=3)" if days == 1 else ""
        return f"{heading}\n\nNo commits found{hint}."

    touched = Counter(path for c in commits for path in c.files)
    added = sum(c.insertions for c in commits)
    removed = sum(c.deletions for c in commits)
    lines = [
        heading,
        "",
        f"**Done** ({len(commits)} commits, +{added}/-{removed} lines)",
        *(f"- {c.subject} ({c.hash[:7]})" for c in commits),
        "",
        "**Most-touched files**",
        *(f"- {path} ({n})" for path, n in touched.most_common(8)),
    ]
    todos = [t for t in find_todos(repo, limit=500).items if t.path in touched]
    if todos:
        lines += ["", "**Open TODOs in those files**"]
        lines += [f"- {t.path}:{t.line} {t.tag}: {t.text}" for t in todos[:10]]
    return "\n".join(lines)


# --- branches --------------------------------------------------------------------


def _base_branch(repo: Path, local: set[str]) -> str:
    remote_head = run_git(
        repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", ok_codes=(0, 1, 128)
    ).strip()
    if remote_head.removeprefix("origin/") in local:
        return remote_head.removeprefix("origin/")
    for name in ("main", "master", "develop"):
        if name in local:
            return name
    return run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def branch_report(
    repo: Path, stale_after_days: int = 30, now: datetime | None = None
) -> BranchReport:
    now = now or datetime.now(UTC)
    refs = run_git(
        repo,
        "for-each-ref",
        "refs/heads",
        "--format=%(refname:short)%1f%(committerdate:iso-strict)%1f%(authorname)%1f%(HEAD)",
    )
    rows = [line.split(_FIELD) for line in refs.splitlines() if line]
    base = _base_branch(repo, {r[0] for r in rows})

    branches = []
    for name, date, author, head_marker in rows:
        behind, ahead = run_git(
            repo, "rev-list", "--left-right", "--count", f"{base}...{name}"
        ).split()
        last = _parse_date(date)
        branches.append(
            BranchInfo(
                name=name,
                current=head_marker == "*",
                last_commit=last,
                last_author=author,
                ahead=int(ahead),
                behind=int(behind),
                stale=name != base and now - last > timedelta(days=stale_after_days),
            )
        )
    branches.sort(key=lambda b: b.last_commit, reverse=True)
    return BranchReport(base_branch=base, stale_after_days=stale_after_days, branches=branches)
