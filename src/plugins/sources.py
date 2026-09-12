"""Plugin *sources* -- operator-added GitHub repos that offer installable
plugins and themes.

A source repo has a ``repo.json`` at its root listing what it ships;
that file is only a browse catalog -- when a plugin is actually installed
Meshpoint re-reads and re-validates the real ``plugin.toml`` /
``theme.json`` from the downloaded files, so nothing here is trusted
beyond "this is a GitHub URL and the JSON parses".

This module does the network + parsing + validation; the route layer
(``src/api/routes/plugin_source_routes.py``) owns auth, persistence to
``local.yaml`` and the HTTP shapes. FastAPI-free so it unit-tests on the
Mac, same as ``src/plugins/manifest.py`` and ``src/api/theme_registry.py``.

Repo manifest shape (``repo.json`` at the repo root)::

    {
      "meshpoint_repo": 1,
      "name": "javastraat's meshpoint plugins",
      "description": "...",                     # optional
      "plugins": [
        { "id": "hello-service", "kind": "app", "path": "apps/hello-service",
          "version": "0.1.0", "meshpoint_api": 1, "provides": ["service"],
          "description": "...", "author": "...", "homepage": "...",
          "has_setup": false,                   # metadata beyond id/kind/path
          "hook_host": "some-other-plugin" }    # optional -- only for a
                                                 # "hook" plugin; its target's
                                                 # own [sidebar].route
      ],                                         # mirrors each plugin.toml
      "themes": [
        { "id": "dracula", "kind": "theme", "path": "themes/dracula",
          "version": "1.0.0", "description": "...", "author": "..." }
      ]
    }
"""

from __future__ import annotations

import json
import logging
import re
from src.plugins.network import open_github

from src.plugins.manifest import PLUGIN_API_VERSION

logger = logging.getLogger(__name__)

MESHPOINT_REPO_MANIFEST = "repo.json"
_REPO_MANIFEST_VERSION = 1

_TIMEOUT_S = 12
_MAX_CATALOG_BYTES = 256 * 1024

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")
_SSH_URL_RE = re.compile(r"^git@github\.com:(.+?)(?:\.git)?/?$")
_HTTPS_URL_RE = re.compile(
    r"^https?://(?:[^@/]+@)?github\.com/([^/]+/[^/]+?)(?:\.git)?/?$"
)


class PluginSourceError(Exception):
    """A source URL / catalog we can't use. ``code`` is a short slug."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_github_url(url: str) -> tuple[str, str]:
    """``(owner, repo)`` for a GitHub repo URL (https or ssh form). Raises
    :class:`PluginSourceError` for anything that isn't a github.com repo."""
    url = str(url or "").strip()
    for pattern in (_HTTPS_URL_RE, _SSH_URL_RE):
        m = pattern.match(url)
        if m:
            owner, _, repo = m.group(1).partition("/")
            if owner and repo and "/" not in repo:
                return owner, repo
    raise PluginSourceError(
        "url", "must be a github.com repository URL, e.g. "
        "https://github.com/you/meshpoint-plugins",
    )


def normalise_ref(ref: str | None) -> str:
    """A git ref (branch / tag / SHA). Blank -> ``main``.

    The ref is interpolated straight into a ``raw.githubusercontent.com`` /
    ``api.github.com`` path, so it must not be able to smuggle path
    navigation: no whitespace, no leading/trailing slash, and crucially no
    ``..`` segment (``ref="../../other/repo/main"`` would otherwise make
    the catalog fetch resolve to a *different* repo than the source URL
    the operator sees). Slashes are allowed because real branch names use
    them (``feature/x``), but only between non-``..`` segments."""
    ref = str(ref or "").strip() or "main"
    if (
        not re.match(r"^[A-Za-z0-9._\-/]{1,100}$", ref)
        or ref.startswith("/") or ref.endswith("/")
        or ".." in ref.split("/")
    ):
        raise PluginSourceError("ref", "ref must be a branch, tag or commit SHA")
    return ref


def canonical_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}"


def catalog_raw_url(owner: str, repo: str, ref: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/"
        f"{MESHPOINT_REPO_MANIFEST}"
    )


def tarball_url(owner: str, repo: str, ref: str) -> str:
    """GitHub's on-demand source archive -- used by the installer (Phase 3)
    to pull a single plugin's subtree without needing ``git`` on the box."""
    return f"https://api.github.com/repos/{owner}/{repo}/tarball/{ref}"


def commits_api_url(owner: str, repo: str, ref: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}"


_MAX_COMMIT_JSON_BYTES = 512 * 1024


def resolve_commit(url: str, ref: str) -> dict:
    """Resolve a source's branch/tag/SHA ``ref`` to the concrete commit it
    points at *right now* -- used to show "installed abc → will update to
    def" before an Update, and to pin a moving branch. Returns
    ``{sha, short_sha, message, committed_at, html_url}``. Raises
    :class:`PluginSourceError`."""
    owner, repo = parse_github_url(url)
    ref = normalise_ref(ref)
    raw = _http_get(commits_api_url(owner, repo, ref), _MAX_COMMIT_JSON_BYTES)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PluginSourceError("fetch", f"bad commit JSON from GitHub: {exc}") from exc
    sha = data.get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise PluginSourceError("fetch", f"GitHub returned no commit for {ref!r}")
    commit = data.get("commit") or {}
    author = (commit.get("author") or {}) if isinstance(commit, dict) else {}
    return {
        "sha": sha,
        "short_sha": sha[:7],
        "message": (commit.get("message") or "").splitlines()[0][:200]
        if isinstance(commit, dict) else "",
        "committed_at": author.get("date", "") if isinstance(author, dict) else "",
        "html_url": data.get("html_url", "") if isinstance(data, dict) else "",
    }


def _http_get(url: str, max_bytes: int) -> bytes:
    try:
        with open_github(url, timeout=_TIMEOUT_S) as resp:
            data = resp.read(max_bytes + 1)
    except Exception as exc:  # noqa: BLE001 -- network / 404 / DNS -> one error type
        raise PluginSourceError("fetch", f"could not fetch {url}: {exc}") from exc
    if len(data) > max_bytes:
        raise PluginSourceError("fetch", f"{url} is larger than {max_bytes} bytes")
    return data


def _entry(raw: dict, kind: str) -> dict:
    """Validate one catalog entry (a plugin or a theme). ``kind`` is
    ``"app"`` or ``"theme"``; a plugin may override it (``"app"`` is the
    only app kind today). Returns a normalised dict; raises on anything
    structurally wrong so a typo'd catalog is a clear error, not a
    silently-skipped plugin."""
    if not isinstance(raw, dict):
        raise PluginSourceError("catalog", f"each {kind} entry must be an object")

    pid = raw.get("id")
    if not isinstance(pid, str) or not _SLUG_RE.match(pid):
        raise PluginSourceError("catalog", f"{kind} 'id' must be a slug [a-z0-9-]")

    path = raw.get("path")
    expected_prefix = "themes/" if kind == "theme" else "apps/"
    if (
        not isinstance(path, str)
        or not path.startswith(expected_prefix)
        or ".." in path
        or path.strip("/").count("/") != 1
        or path.rstrip("/").rsplit("/", 1)[-1] != pid
    ):
        raise PluginSourceError(
            "catalog",
            f"{kind} 'path' must be {expected_prefix}{pid} (one level, matching id)",
        )

    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PluginSourceError("catalog", f"{kind} 'version' must be a non-empty string")

    api = raw.get("meshpoint_api", 1)
    if not isinstance(api, int) or isinstance(api, bool) or api < 1:
        raise PluginSourceError("catalog", f"{kind} 'meshpoint_api' must be an integer >= 1")

    def _s(key: str) -> str:
        v = raw.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    provides = raw.get("provides", [])
    if not isinstance(provides, list) or any(not isinstance(p, str) for p in provides):
        provides = []

    # Optional: the [sidebar].route of the app this one hooks into (only
    # meaningful for a plugin that provides "hook"). Purely a browse-catalog
    # display/grouping hint -- Meshpoint re-derives the real dependency from
    # the installed plugin's own plugin.toml, same as every other field
    # here, so a malformed/absent value just means no grouping, not an
    # error. Not validated against a sibling entry's id: the host may live
    # outside this catalog entirely (built into Meshpoint core, or a
    # different source).
    hook_host = raw.get("hook_host")
    hook_host = hook_host.strip() if isinstance(hook_host, str) and _SLUG_RE.match(hook_host.strip()) else ""

    entry = {
        "id": pid,
        "kind": "theme" if kind == "theme" else "app",
        "path": path.strip("/"),
        "version": version.strip(),
        "meshpoint_api": api,
        "provides": provides,
        "description": _s("description"),
        "author": _s("author"),
        "homepage": _s("homepage"),
        "has_setup": bool(raw.get("has_setup")),
        # True when this Meshpoint is new enough to load it.
        "compatible": api <= PLUGIN_API_VERSION,
    }
    if kind != "theme" and hook_host:
        entry["hook_host"] = hook_host
    return entry


def parse_catalog(data: bytes) -> dict:
    """Validate a fetched ``repo.json``. Returns
    ``{name, description, plugins: [...], themes: [...]}``."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PluginSourceError("catalog", f"repo.json is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PluginSourceError("catalog", "repo.json must be a JSON object")

    ver = raw.get("meshpoint_repo")
    if ver != _REPO_MANIFEST_VERSION:
        raise PluginSourceError(
            "catalog",
            f"'meshpoint_repo' must be {_REPO_MANIFEST_VERSION} (got {ver!r})",
        )

    plugins = [_entry(e, "app") for e in raw.get("plugins", []) or []]
    themes = [_entry(e, "theme") for e in raw.get("themes", []) or []]

    seen: set[str] = set()
    for e in plugins + themes:
        if e["id"] in seen:
            raise PluginSourceError("catalog", f"duplicate id {e['id']!r} in repo.json")
        seen.add(e["id"])

    name = raw.get("name")
    return {
        "name": name.strip() if isinstance(name, str) and name.strip() else "",
        "description": (raw.get("description") or "").strip()
        if isinstance(raw.get("description"), str) else "",
        "plugins": plugins,
        "themes": themes,
    }


def fetch_catalog(url: str, ref: str) -> dict:
    """Resolve *url*, fetch its ``repo.json`` at *ref*, validate it.
    Returns the parsed catalog plus ``owner``/``repo``/``ref``/``url``."""
    owner, repo = parse_github_url(url)
    ref = normalise_ref(ref)
    catalog = parse_catalog(_http_get(catalog_raw_url(owner, repo, ref), _MAX_CATALOG_BYTES))
    catalog.update(
        owner=owner, repo=repo, ref=ref, url=canonical_url(owner, repo),
    )
    return catalog
