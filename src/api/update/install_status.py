"""Read the live install tree branch and compare to upstream."""

from __future__ import annotations

import logging
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from src.api.update.channels import ReleaseChannelRegistry, TIER_CUSTOM
from src.api.update.rollback_state import (
    DEFAULT_ROLLBACK_STATE_PATH,
    read_rollback_state,
)
from src.version import __version__

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
GitRunner = Callable[[list[str], Optional[str], float], tuple[int, str, str]]


def default_git_runner(
    args: list[str], cwd: Optional[str], timeout_seconds: float,
) -> tuple[int, str, str]:
    completed = subprocess.run(  # noqa: S603
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def read_install_git_ref(
    repo_path: str,
    *,
    runner: GitRunner = default_git_runner,
    use_sudo: bool = True,
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(branch_name, short_sha)`` for HEAD in the install tree.

    Uses ``cwd=repo_path`` (not ``git -C``) so commands match the
    passwordless sudoers entries granted to the ``meshpoint`` service
    user. The apply chain already uses the same pattern.
    """
    git = ["sudo", "git"] if use_sudo else ["git"]

    rc, branch_out, _ = runner(
        [*git, "rev-parse", "--abbrev-ref", "HEAD"], repo_path, 10.0,
    )
    branch = branch_out.strip() if rc == 0 else None
    if branch == "HEAD":
        branch = _read_detached_branch_name(git, repo_path, runner)

    rc, sha_out, _ = runner(
        [*git, "rev-parse", "--short=8", "HEAD"], repo_path, 10.0,
    )
    sha = sha_out.strip() if rc == 0 else None
    if branch is None or sha is None:
        logger.warning(
            "install_status: could not read git ref in %s (branch=%s sha=%s)",
            repo_path, branch, sha,
        )
    return branch or None, sha or None


def read_head_full_sha(
    repo_path: str,
    *,
    runner: GitRunner = default_git_runner,
    use_sudo: bool = True,
    timeout_seconds: float = 30.0,
) -> Optional[str]:
    """Return the full 40-char (or longer) SHA for HEAD in the install tree."""
    git = ["sudo", "git"] if use_sudo else ["git"]
    rc, out, stderr = runner(
        [*git, "rev-parse", "HEAD"], repo_path, timeout_seconds,
    )
    if rc != 0:
        logger.warning(
            "read_head_full_sha: rev-parse failed in %s (rc=%s): %s",
            repo_path,
            rc,
            (stderr or "").strip()[:300],
        )
        return None
    sha = out.strip()
    return sha if sha else None


def _read_detached_branch_name(
    git: list[str], repo_path: str, runner: GitRunner,
) -> Optional[str]:
    """Best-effort branch name when HEAD is detached at a remote tip."""
    rc, out, _ = runner(
        [*git, "rev-parse", "--abbrev-ref", "HEAD@{upstream}"],
        repo_path,
        10.0,
    )
    if rc != 0:
        return None
    ref = out.strip()
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    return ref or None


def match_channel_for_branch(
    registry: ReleaseChannelRegistry, branch: str,
) -> dict[str, str]:
    """Map an install branch name back to a picker channel (or custom)."""
    for channel in registry.channels():
        if channel.branch and channel.branch == branch:
            return {
                "active_channel_id": channel.id,
                "active_channel_label": channel.label,
                "channel_tier": channel.tier,
            }
    if branch == "main":
        stable = registry.find("stable")
        if stable is not None:
            return {
                "active_channel_id": stable.id,
                "active_channel_label": stable.label,
                "channel_tier": stable.tier,
            }
    return {
        "active_channel_id": "custom",
        "active_channel_label": f"Custom ({branch})" if branch else "Custom branch",
        "channel_tier": TIER_CUSTOM,
    }


def fetch_remote_version_sync(branch: str) -> Optional[str]:
    url = (
        "https://raw.githubusercontent.com/KMX415/meshpoint/"
        f"{branch}/src/version.py"
    )
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode()
            match = _VERSION_RE.search(text)
            return match.group(1) if match else None
    except Exception:
        logger.debug(
            "Could not fetch remote version for branch %s", branch, exc_info=True,
        )
        return None


def _parse_version(version_str: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version_str.split("."))


def resolve_compare_branch(
    registry: ReleaseChannelRegistry,
    *,
    channel_id: Optional[str],
    custom_branch: Optional[str],
    install_branch: Optional[str],
) -> Optional[str]:
    """Branch used for ``origin/<branch>`` comparison (picker or install)."""
    if channel_id:
        channel = registry.find(channel_id)
        if channel is None:
            return None
        if channel.tier == TIER_CUSTOM:
            branch = (custom_branch or "").strip()
            return branch or None
        return channel.branch
    return install_branch


def git_fetch_origin_branch(
    repo_path: str,
    branch: str,
    *,
    runner: GitRunner = default_git_runner,
    use_sudo: bool = True,
    timeout_seconds: float = 120.0,
) -> tuple[bool, Optional[str]]:
    """Fetch ``origin/<branch>``. Returns ``(ok, error_message)``."""
    git = ["sudo", "git"] if use_sudo else ["git"]
    rc, _, stderr = runner(
        [*git, "fetch", "origin", branch],
        repo_path,
        timeout_seconds,
    )
    if rc != 0:
        detail = (stderr or "git fetch failed").strip().replace("\n", " ")
        return False, detail[:500] if detail else "git fetch failed"
    return True, None


def _revision_count(
    repo_path: str,
    revision_range: str,
    *,
    runner: GitRunner,
    use_sudo: bool,
    timeout_seconds: float = 15.0,
) -> Optional[int]:
    """Count commits in ``revision_range`` (e.g. ``HEAD..origin/main``).

    Uses ``git rev-list --count`` when sudoers allows it; falls back to
    ``git log --oneline`` (already whitelisted on older installs) when
    ``rev-list`` is denied.
    """
    git = ["sudo", "git"] if use_sudo else ["git"]
    rc, out, _ = runner(
        [*git, "rev-list", "--count", revision_range],
        repo_path,
        timeout_seconds,
    )
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())

    rc, log_out, _ = runner(
        [*git, "log", "--oneline", revision_range],
        repo_path,
        timeout_seconds,
    )
    if rc != 0:
        logger.warning(
            "install_status: could not count revisions for %s "
            "(rev-list denied and log failed)",
            revision_range,
        )
        return None
    return sum(1 for line in log_out.splitlines() if line.strip())


def count_commits_behind_ahead(
    repo_path: str,
    branch: str,
    *,
    runner: GitRunner = default_git_runner,
    use_sudo: bool = True,
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Compare HEAD to ``origin/<branch>``. Returns behind, ahead, remote short SHA."""
    git = ["sudo", "git"] if use_sudo else ["git"]
    upstream = f"origin/{branch}"

    behind = _revision_count(
        repo_path,
        f"HEAD..{upstream}",
        runner=runner,
        use_sudo=use_sudo,
    )
    ahead = _revision_count(
        repo_path,
        f"{upstream}..HEAD",
        runner=runner,
        use_sudo=use_sudo,
    )

    rc, sha_out, _ = runner(
        [*git, "rev-parse", "--short=8", upstream],
        repo_path,
        10.0,
    )
    remote_sha = sha_out.strip() if rc == 0 else None
    return behind, ahead, remote_sha


def build_install_status_payload(
    *,
    registry: ReleaseChannelRegistry,
    repo_path: str = "/opt/meshpoint",
    runner: GitRunner = default_git_runner,
    use_sudo: bool = True,
    sync_remote: bool = False,
    channel_id: Optional[str] = None,
    custom_branch: Optional[str] = None,
    rollback_state_path: Path | None = None,
) -> dict:
    """Assemble install/update status JSON for the dashboard."""
    branch, sha = read_install_git_ref(
        repo_path, runner=runner, use_sudo=use_sudo,
    )
    if branch:
        channel_info = match_channel_for_branch(registry, branch)
    else:
        channel_info = {
            "active_channel_id": None,
            "active_channel_label": None,
            "channel_tier": None,
        }

    compare_branch = resolve_compare_branch(
        registry,
        channel_id=channel_id,
        custom_branch=custom_branch,
        install_branch=branch,
    )

    commits_behind: Optional[int] = None
    commits_ahead: Optional[int] = None
    remote_sha_short: Optional[str] = None
    sync_error: Optional[str] = None
    checked_at: Optional[str] = None

    if sync_remote and compare_branch:
        ok, err = git_fetch_origin_branch(
            repo_path, compare_branch, runner=runner, use_sudo=use_sudo,
        )
        if ok:
            behind, ahead, remote_sha = count_commits_behind_ahead(
                repo_path, compare_branch, runner=runner, use_sudo=use_sudo,
            )
            commits_behind = behind
            commits_ahead = ahead
            remote_sha_short = remote_sha
            checked_at = datetime.now(timezone.utc).isoformat()
        else:
            sync_error = err

    remote_version = None
    update_available = False
    version_branch = compare_branch or branch
    if version_branch:
        remote_version = fetch_remote_version_sync(version_branch)
    if sync_remote and commits_behind is not None:
        update_available = commits_behind > 0
    elif remote_version:
        try:
            update_available = (
                _parse_version(remote_version) > _parse_version(__version__)
            )
        except ValueError:
            update_available = False

    rb_path = rollback_state_path or DEFAULT_ROLLBACK_STATE_PATH
    rollback = read_rollback_state(path=rb_path)
    rollback_pre_sha = rollback["pre_update_sha"] if rollback else None

    return {
        "local_version": __version__,
        "install_branch": branch,
        "install_sha_short": sha,
        "remote_version": remote_version,
        "remote_branch": compare_branch or branch,
        "compare_branch": compare_branch,
        "commits_behind": commits_behind,
        "commits_ahead": commits_ahead,
        "remote_sha_short": remote_sha_short,
        "sync_error": sync_error,
        "checked_at": checked_at,
        "update_available": update_available,
        "rollback_pre_sha": rollback_pre_sha,
        **channel_info,
    }
