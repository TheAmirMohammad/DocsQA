"""Git repository ingestion source for cloning and preparing documentation repositories."""

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.observability.logging import logger


def sanitize_repo_name(git_url: str) -> str:
    """Extract a safe directory name from a git repository URL."""
    parsed = urlparse(git_url)
    path = parsed.path.rstrip("/")
    path = path.removesuffix(".git")
    name = Path(path).name or "cloned_repo"
    # Replace non-alphanumeric chars
    return re.sub(r"[^\w\-_]", "_", name)


def clone_git_repository(
    git_url: str,
    branch: str = "main",
    target_dir: Path | None = None,
    depth: int = 1,
) -> Path:
    """
    Shallow clones a remote git repository into a local directory for documentation indexing.
    
    Args:
        git_url: HTTPS or SSH repository URL.
        branch: Git branch or tag name.
        target_dir: Optional specific directory. If omitted, uses settings.DOCS_ROOT / 'git_repos' / <repo>.
        depth: Shallow clone depth (default 1).
    """
    if not git_url or not git_url.strip():
        raise ValueError("Invalid or empty git_url.")

    # Validate scheme: only allow http/https or git/ssh
    if not git_url.startswith(("http://", "https://", "git@")):
        raise ValueError(f"Unsupported git URL protocol: {git_url}")

    if target_dir is None:
        repo_name = sanitize_repo_name(git_url)
        dest_root = Path(settings.DOCS_ROOT) / "git_repos"
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / repo_name
    else:
        dest = Path(target_dir)

    # Clean existing directory if present
    if dest.exists():
        logger.info("Removing existing cloned directory before fresh clone", path=str(dest))
        shutil.rmtree(dest, ignore_errors=True)

    dest.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning git repository for documentation indexing", git_url=git_url, branch=branch, dest=str(dest))

    cmd = [
        "git",
        "clone",
        "--depth",
        str(depth),
        "--single-branch",
        "-b",
        branch,
        git_url,
        str(dest),
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"Git clone timed out after 120s: {git_url}") from e
    except FileNotFoundError as e:
        raise RuntimeError("git CLI executable is not installed or available in PATH") from e

    if res.returncode != 0:
        # If branch is not found or other clone error, try default clone without -b branch
        logger.warning(
            "Failed cloning specific branch, retrying default branch",
            branch=branch,
            stderr=res.stderr,
        )
        retry_cmd = ["git", "clone", "--depth", str(depth), git_url, str(dest)]
        retry_res = subprocess.run(retry_cmd, capture_output=True, text=True, timeout=120, check=False)
        if retry_res.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            raise RuntimeError(f"Git clone failed: {retry_res.stderr.strip() or res.stderr.strip()}")

    # Strip .git directory to prevent indexing internal git history or packfiles
    dot_git = dest / ".git"
    if dot_git.exists():
        shutil.rmtree(dot_git, ignore_errors=True)

    logger.info("Successfully cloned documentation repository", path=str(dest))
    return dest
