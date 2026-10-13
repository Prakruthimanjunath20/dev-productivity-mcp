"""A throwaway git repository with known authors, dates, tags, TODOs and branches."""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ME = ("Prakruthi", "prakruthi@example.com")
ALEX = ("Alex Dev", "alex@example.com")


def git(repo: Path, *args: str, who=ME, ago: timedelta | None = None) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": who[0],
        "GIT_AUTHOR_EMAIL": who[1],
        "GIT_COMMITTER_NAME": who[0],
        "GIT_COMMITTER_EMAIL": who[1],
    }
    if ago is not None:
        stamp = (datetime.now(UTC) - ago).isoformat()
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
    result = subprocess.run(
        ["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout


def commit(repo: Path, message: str, files: dict[str, str], who=ME, ago=timedelta(hours=1)):
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message, who=who, ago=ago)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", ME[0])
    git(repo, "config", "user.email", ME[1])

    commit(
        repo,
        "chore: initial scaffold",
        {"README.md": "# Demo\n", "app.py": "print('hi')\n"},
        who=ALEX,
        ago=timedelta(days=40),
    )
    git(repo, "tag", "v0.1.0")

    git(repo, "checkout", "-q", "-b", "feature/old")
    commit(repo, "wip: old experiment", {"old.py": "x = 1\n"}, ago=timedelta(days=35))
    git(repo, "checkout", "-q", "main")

    commit(
        repo,
        "feat(api): add search endpoint",
        {"app.py": "def search(q):\n    # TODO: add pagination\n    return []\n"},
        ago=timedelta(hours=3),
    )
    commit(
        repo,
        "fix: handle empty query",
        {"utils.py": "def clean(q):\n    return q.strip()  # FIXME handle unicode\n"},
        ago=timedelta(hours=2),
    )
    commit(
        repo,
        "docs: update README",
        {"README.md": "# Demo\n\nUsage notes.\n"},
        who=ALEX,
        ago=timedelta(minutes=90),
    )
    commit(
        repo,
        "feat!: drop Python 3.10 support",
        {"pyproject.toml": "[project]\n"},
        ago=timedelta(minutes=30),
    )
    return repo


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"
