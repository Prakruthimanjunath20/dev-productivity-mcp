"""Safe access to local git repositories.

Every tool goes through two guards:

* `resolve_repo` only accepts folders inside the allowed roots
  (`DEV_MCP_ALLOWED_ROOTS`, defaulting to the folder the server was started in),
  so an assistant cannot read arbitrary parts of the disk.
* `run_git` calls git with an argument list (never a shell) and a timeout, and
  `check_ref` rejects anything that could be read as a git option, such as
  `--output=...`, which would otherwise let a crafted ref write files.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """A git command failed or a request was not allowed."""


_REF = re.compile(r"[A-Za-z0-9._/@^~{}+-]+")


def allowed_roots() -> list[Path]:
    raw = os.environ.get("DEV_MCP_ALLOWED_ROOTS", "")
    roots = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
    return [r.resolve() for r in (roots or [Path.cwd()])]


def _inside(path: Path, roots: list[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def run_git(repo: Path, *args: str, timeout: float = 20.0, ok_codes: tuple[int, ...] = (0,)) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "--no-pager", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed on this machine") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} took longer than {timeout:.0f}s") from exc
    if result.returncode not in ok_codes:
        message = result.stderr.strip() or f"git {args[0]} exited with {result.returncode}"
        raise GitError(message)
    return result.stdout


def resolve_repo(path: str, roots: list[Path] | None = None) -> Path:
    """Return the top-level folder of the repository at `path`, if it is allowed."""
    roots = roots if roots is not None else allowed_roots()
    candidate = Path(path).expanduser().resolve()
    allowed = ", ".join(str(r) for r in roots)
    if not _inside(candidate, roots):
        raise GitError(
            f"{candidate} is outside the allowed folders ({allowed}). "
            "Add it to DEV_MCP_ALLOWED_ROOTS to allow it."
        )
    if not candidate.is_dir():
        raise GitError(f"{candidate} is not a folder")
    top = Path(run_git(candidate, "rev-parse", "--show-toplevel").strip()).resolve()
    if not _inside(top, roots):
        raise GitError(f"The repository root {top} is outside the allowed folders ({allowed})")
    return top


def check_ref(ref: str) -> str:
    """Accept branch, tag and commit names; refuse anything that looks like an option."""
    if not ref or ref.startswith("-") or not _REF.fullmatch(ref):
        raise GitError(f"{ref!r} is not a valid branch, tag or commit name")
    return ref
