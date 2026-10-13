import pytest

from dev_productivity_mcp import tools
from dev_productivity_mcp.git import GitError, check_ref, resolve_repo


def test_repo_overview(repo):
    overview = tools.repo_overview(repo)
    assert overview.branch == "main"
    assert overview.total_commits == 5
    assert {c.name for c in overview.contributors} == {"Prakruthi", "Alex Dev"}
    assert overview.contributors[0].name == "Prakruthi"  # most commits first
    assert any(f.extension == ".py" for f in overview.file_types)
    assert overview.recent_tags == ["v0.1.0"]
    assert overview.uncommitted_changes == 0
    assert overview.first_commit < overview.last_commit

    (repo / "scratch.txt").write_text("not committed")
    assert tools.repo_overview(repo).uncommitted_changes == 1


def test_recent_commits_window_and_author(repo):
    week = tools.recent_commits(repo, since_days=7)
    assert week.count == 4  # the 40-day-old scaffold commit is excluded
    assert week.commits[0].subject == "feat!: drop Python 3.10 support"
    search = next(c for c in week.commits if "search" in c.subject)
    assert search.files == ["app.py"] and search.insertions == 3 and search.deletions == 1

    alex = tools.recent_commits(repo, since_days=7, author="Alex")
    assert [c.subject for c in alex.commits] == ["docs: update README"]


def test_find_todos(repo):
    report = tools.find_todos(repo)
    assert report.total == 2
    assert report.by_tag == {"TODO": 1, "FIXME": 1}
    todo = next(i for i in report.items if i.tag == "TODO")
    assert (todo.path, todo.line, todo.text) == ("app.py", 2, "add pagination")
    assert tools.find_todos(repo, ["HACK"]).total == 0
    assert tools.find_todos(repo, limit=1).truncated


def test_find_todos_rejects_patterns(repo):
    with pytest.raises(GitError):
        tools.find_todos(repo, ["TODO|.*"])


def test_changelog_since_latest_tag(repo):
    notes = tools.changelog(repo)
    assert notes.startswith("## Changes since v0.1.0")
    assert "4 commits." in notes
    assert "### Breaking changes\n- drop Python 3.10 support" in notes
    assert "- **api:** add search endpoint" in notes
    assert "### Bug fixes" in notes and "### Documentation" in notes
    assert "initial scaffold" not in notes
    assert notes.index("### Breaking changes") < notes.index("### Features")


def test_changelog_full_history_when_no_tag(repo):
    notes = tools.changelog(repo, since_ref=None, until_ref="v0.1.0")
    assert "(full history)" in notes and "initial scaffold" in notes


@pytest.mark.parametrize("ref", ["--output=/tmp/pwned", "-p", "main;rm", ""])
def test_refs_that_look_like_options_are_rejected(ref):
    with pytest.raises(GitError):
        check_ref(ref)


def test_standup_report(repo):
    report = tools.standup_report(repo)  # author from git config: Prakruthi
    assert report.startswith("### Standup: Prakruthi, last day in demo-repo")
    assert "add search endpoint" in report and "update README" not in report
    assert "app.py:2 TODO: add pagination" in report
    assert "No commits found (on a Monday" in tools.standup_report(repo, author="Nobody")


def test_branch_health(repo):
    report = tools.branch_report(repo)
    assert report.base_branch == "main"
    branches = {b.name: b for b in report.branches}
    old = branches["feature/old"]
    assert (old.ahead, old.behind, old.stale) == (1, 4, True)
    assert branches["main"].current and not branches["main"].stale


def test_paths_outside_allowed_roots_are_refused(repo, tmp_path):
    (repo / "docs").mkdir()
    assert resolve_repo(str(repo / "docs"), [tmp_path]) == repo  # subfolders map to the root
    with pytest.raises(GitError, match="outside the allowed folders"):
        resolve_repo(str(repo), [tmp_path / "somewhere-else"])
    with pytest.raises(GitError):
        resolve_repo(str(tmp_path), [tmp_path])  # allowed, but not a git repository
