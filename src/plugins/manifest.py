"""Parse and validate ``plugins/apps/<name>/plugin.toml``.

An "app" plugin is out-of-core code that hooks the seams built in the plugin
roadmap so far -- ``src.api.route_registry`` (routes), ``src.api.listener_registry``
(RTL-SDR listeners), ``src.api.capture_source_registry`` (a capture source
joining the real packet pipeline), ``src.api.protocol_registry`` (decode +
classification for a protocol the plugin owns end to end), and
``window.registerSidebarPage``/``window.registerPageHook`` (a top-level page,
or content injected into another plugin's page). This module only *reads*
the manifest and enumerates the folders; importing the plugin and calling
its ``register()`` is a later step (B4b).

``PLUGIN_API_VERSION`` is the contract number those seams collectively define.
A manifest declaring a higher ``meshpoint_api`` targets a newer Meshpoint than
this one and is refused.

Kept free of FastAPI imports so it unit-tests on the Mac, same as
``src/api/theme_registry.py``.

Manifest shape::

    name = "acars"                 # must equal the folder name
    version = "0.1.0"
    meshpoint_api = 1
    provides = ["listener", "routes", "panel"]
    locked = false                 # optional, default false. true = shipped/bundled
                                    # community plugin; refuses an "uninstall" delete.

    [deps]                         # optional
    apt = ["cmake", "pkg-config"]
    setup = "setup.sh"             # relative to the plugin dir, must exist
    check = "check.sh"             # optional, relative to the plugin dir, must
                                    # exist. Run unprivileged at boot (and on
                                    # demand from Settings -> Plugins): exit 0 =
                                    # deps satisfied, non-zero = setup needed,
                                    # stdout/stderr = the reason shown to the admin.

    [frontend]                     # required when "panel", "sidebar", "hook" or "topbar" in provides
    scripts = ["frontend/acars_panel.js"]   # rel paths, must exist
    styles  = ["frontend/acars_panel.css"]  # optional

    [sidebar]                      # required when "sidebar" in provides
    route = "hello-world"          # url route id (bare slug, [a-z0-9-])
    label = "Hello World"          # sidebar link text
    category = "networks"          # one of: networks, radio, ops, configuration, settings
    icon = "plug"                  # optional, default "plug" -- one of KNOWN_SIDEBAR_ICONS

    [hook]                         # required when "hook" in provides
    host = "hello-world"           # target host page's id (a "sidebar" plugin's
                                    # own [sidebar].route) -- window.registerPageHook()
                                    # injects this plugin's content into that host's
                                    # page instead of owning a page of its own.

    [meta]                         # optional, all strings
    description = "..."
    homepage = "..."
    author = "..."
"""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Bump when a plugin seam's contract changes in a way a plugin can observe.
PLUGIN_API_VERSION = 1

MANIFEST_NAME = "plugin.toml"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")
_ROUTE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,58}$")

KNOWN_PROVIDES = frozenset({
    "listener", "routes", "panel", "sidebar", "hook", "capture", "protocol",
    "topbar", "service",
})

# The existing top-level sidebar sections a plugin's page can be placed
# under -- "networks"/"radio"/"ops" are flat item runs (LoRaWAN, Radio, the
# Terminal link, ...); "configuration"/"settings" are the two collapsible
# submenus, where a plugin's route is nested as "<category>/<route>" the
# same way the built-in subitems are (e.g. "settings/plugins").
KNOWN_SIDEBAR_CATEGORIES = frozenset({
    "networks", "radio", "ops", "configuration", "settings",
})

# A curated icon set for a sidebar page, keyed by name -- not arbitrary SVG
# from a manifest (that's a real injection surface for a file some other
# person authored). frontend/sidebar/sidebar_plugin_registry.js owns the
# actual glyphs; this is just the set of valid keys. "plug" (the original,
# only, generic icon) stays the default. topology/rf/pager/dapnet/
# reticulum/lorawan/gear/usb are exact copies of Meshpoint's own existing
# sidebar icons for those pages -- reuse, not new geometry ("usb" is the
# RTL-SDR page's own dongle glyph, inherited from the built-in Listener
# page's nav item once that page was deleted).
KNOWN_SIDEBAR_ICONS = frozenset({
    "plug", "antenna", "chart", "message", "terminal", "map", "list", "grid",
    "topology", "rf", "pager", "dapnet", "reticulum", "lorawan", "gear", "usb",
})
_DEFAULT_SIDEBAR_ICON = "plug"

# Where a plugin folder was found. Built-ins ship in the repo under
# src/plugins/apps/ and load unless explicitly disabled; community drop-ins
# live in <plugins_dir>/apps/ and are opt-in. Mirrors themes' builtin/plugin
# split (see src/api/theme_registry.py).
SOURCE_BUILTIN = "builtin"
SOURCE_COMMUNITY = "community"


class PluginManifestError(Exception):
    """A ``plugin.toml`` that can't be trusted. ``code`` is a short slug
    (``name`` / ``api`` / ``provides`` / ...) for callers that want to
    branch; ``str(exc)`` is the human message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SidebarSpec:
    """A plugin's ``[sidebar]`` table -- where it wants a top-level nav
    entry placed. See :data:`KNOWN_SIDEBAR_CATEGORIES`."""

    route: str
    label: str
    category: str
    icon: str = _DEFAULT_SIDEBAR_ICON


@dataclass(frozen=True)
class HookSpec:
    """A plugin's ``[hook]`` table -- which host page it injects content
    into via ``window.registerPageHook()``, instead of owning a page of
    its own. ``host`` is another plugin's ``[sidebar].route`` (no backend
    validation that the host actually exists -- resolved at runtime in the
    browser, same as a dangling ``registerSidebarPage()`` call just logs a
    console warning rather than failing to load)."""

    host: str


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    api_version: int
    provides: tuple[str, ...]
    apt: tuple[str, ...]
    setup: str | None  # relative path within `path`, verified to exist
    check: str | None  # relative path within `path`, verified to exist -- an
                       # unprivileged "are my deps installed?" probe (exit 0 =
                       # yes). None = no probe declared; caller assumes ok.
    description: str
    homepage: str
    author: str
    frontend_scripts: tuple[str, ...]  # relative paths, verified to exist
    frontend_styles: tuple[str, ...]
    path: Path
    source: str = SOURCE_COMMUNITY  # SOURCE_BUILTIN or SOURCE_COMMUNITY
    # Mirrors theme.json's "locked": true (src/api/theme_store.py) -- marks a
    # shipped/bundled community plugin (e.g. ACARS) so an "uninstall" button
    # can refuse to delete it. Meaningless for built-ins, which are never
    # offered a delete button regardless of this flag.
    locked: bool = False
    # Set iff "sidebar" in provides.
    sidebar: SidebarSpec | None = None
    # Set iff "hook" in provides.
    hook: HookSpec | None = None
    executables: tuple[str, ...] = ()

    @property
    def setup_path(self) -> Path | None:
        return self.path / self.setup if self.setup else None

    @property
    def check_path(self) -> Path | None:
        return self.path / self.check if self.check else None

    @property
    def is_builtin(self) -> bool:
        return self.source == SOURCE_BUILTIN


def _str_field(table: dict, key: str, code: str) -> str:
    value = table.get(key, "")
    if not isinstance(value, str):
        raise PluginManifestError(code, f"{key!r} must be a string.")
    return value


def _rel_paths(value, plugin_dir: Path, key: str) -> tuple[str, ...]:
    """Validate a ``[frontend]`` list: relative-path strings, inside the
    plugin dir, that exist."""
    if not isinstance(value, list) or any(not isinstance(p, str) for p in value):
        raise PluginManifestError(
            "frontend", f"'frontend.{key}' must be a list of path strings.",
        )
    out: list[str] = []
    for rel in value:
        rel = rel.strip().lstrip("/")
        target = (plugin_dir / rel).resolve()
        if plugin_dir.resolve() not in target.parents:
            raise PluginManifestError(
                "frontend", f"'frontend.{key}' entry {rel!r} escapes the plugin dir.",
            )
        if not target.is_file():
            raise PluginManifestError(
                "frontend", f"'frontend.{key}' file {rel!r} does not exist.",
            )
        out.append(rel)
    return tuple(out)


def parse_manifest(
    plugin_dir: Path, source: str = SOURCE_COMMUNITY,
) -> PluginManifest:
    """Read and validate ``<plugin_dir>/plugin.toml``.

    *source* records where the folder was found (:data:`SOURCE_BUILTIN` for
    ``src/plugins/apps/``, :data:`SOURCE_COMMUNITY` for a drop-in). Raises
    :class:`PluginManifestError` on anything wrong.
    """
    manifest_file = plugin_dir / MANIFEST_NAME
    if not manifest_file.is_file():
        raise PluginManifestError("missing", f"no {MANIFEST_NAME} in {plugin_dir}")

    try:
        data = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise PluginManifestError("toml", f"can't read {manifest_file}: {exc}") from exc

    name = data.get("name")
    if not isinstance(name, str) or not _SLUG_RE.match(name):
        raise PluginManifestError(
            "name",
            "'name' must be lowercase [a-z0-9-], 2-39 chars, starting alphanumeric.",
        )
    if name != plugin_dir.name:
        raise PluginManifestError(
            "name", f"'name' ({name!r}) must match the folder ({plugin_dir.name!r}).",
        )

    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PluginManifestError("version", "'version' must be a non-empty string.")

    locked = data.get("locked", False)
    if not isinstance(locked, bool):
        raise PluginManifestError("locked", "'locked' must be a boolean.")

    api_version = data.get("meshpoint_api")
    if not isinstance(api_version, int) or isinstance(api_version, bool):
        raise PluginManifestError("api", "'meshpoint_api' must be an integer.")
    if api_version < 1:
        raise PluginManifestError("api", "'meshpoint_api' must be >= 1.")
    if api_version > PLUGIN_API_VERSION:
        raise PluginManifestError(
            "api",
            f"plugin targets meshpoint_api {api_version}; this Meshpoint "
            f"supports up to {PLUGIN_API_VERSION}.",
        )

    provides = data.get("provides")
    if not isinstance(provides, list) or not provides:
        raise PluginManifestError("provides", "'provides' must be a non-empty list.")
    unknown = [p for p in provides if not isinstance(p, str) or p not in KNOWN_PROVIDES]
    if unknown:
        raise PluginManifestError(
            "provides",
            f"unknown provides {unknown}; known: {sorted(KNOWN_PROVIDES)}.",
        )

    deps = data.get("deps", {})
    if not isinstance(deps, dict):
        raise PluginManifestError("deps", "'[deps]' must be a table.")
    apt = deps.get("apt", [])
    executables = deps.get("executables", [])
    if not isinstance(executables, list) or any(
        not isinstance(p, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", p)
        for p in executables
    ):
        raise PluginManifestError("deps", "'deps.executables' must contain command names, without paths.")
    if not isinstance(apt, list) or any(
        not isinstance(p, str) or not p.strip() for p in apt
    ):
        raise PluginManifestError("deps", "'deps.apt' must be a list of package names.")
    setup = deps.get("setup")
    if setup is not None:
        if not isinstance(setup, str) or not setup.strip():
            raise PluginManifestError("deps", "'deps.setup' must be a path string.")
        if (not (plugin_dir / setup).is_file()
                or plugin_dir.resolve() not in (plugin_dir / setup).resolve().parents):
            raise PluginManifestError(
                "deps", f"'deps.setup' ({setup!r}) does not exist in the plugin.",
            )
    check = deps.get("check")
    if check is not None:
        if not isinstance(check, str) or not check.strip():
            raise PluginManifestError("deps", "'deps.check' must be a path string.")
        if (not (plugin_dir / check).is_file()
                or plugin_dir.resolve() not in (plugin_dir / check).resolve().parents):
            raise PluginManifestError(
                "deps", f"'deps.check' ({check!r}) does not exist in the plugin.",
            )

    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        raise PluginManifestError("meta", "'[meta]' must be a table.")

    frontend = data.get("frontend", {})
    if not isinstance(frontend, dict):
        raise PluginManifestError("frontend", "'[frontend]' must be a table.")
    scripts = _rel_paths(frontend.get("scripts", []), plugin_dir, "scripts")
    styles = _rel_paths(frontend.get("styles", []), plugin_dir, "styles")
    if (
        "panel" in provides or "sidebar" in provides
        or "hook" in provides or "topbar" in provides
    ) and not scripts:
        raise PluginManifestError(
            "frontend",
            "a 'panel', 'sidebar', 'hook' or 'topbar' plugin must list at "
            "least one 'frontend.scripts' file.",
        )

    sidebar = _parse_sidebar(data.get("sidebar"), provides)
    hook = _parse_hook(data.get("hook"), provides)

    return PluginManifest(
        name=name,
        version=version,
        api_version=api_version,
        provides=tuple(provides),
        apt=tuple(apt),
        setup=setup,
        check=check,
        description=_str_field(meta, "description", "meta"),
        homepage=_str_field(meta, "homepage", "meta"),
        author=_str_field(meta, "author", "meta"),
        frontend_scripts=scripts,
        frontend_styles=styles,
        path=plugin_dir,
        source=source,
        locked=locked,
        sidebar=sidebar,
        hook=hook,
        executables=tuple(executables),
    )


def _parse_sidebar(value, provides: list) -> SidebarSpec | None:
    """Validate ``[sidebar]``. Required iff ``"sidebar"`` is in ``provides``;
    an error either way if the two disagree (present-but-not-declared is
    almost always a typo in ``provides``, not intentional)."""
    if "sidebar" not in provides:
        if value is not None:
            raise PluginManifestError(
                "sidebar", "'[sidebar]' is set but 'sidebar' is not in 'provides'.",
            )
        return None

    if not isinstance(value, dict):
        raise PluginManifestError(
            "sidebar", "'sidebar' is in 'provides' but '[sidebar]' is missing.",
        )

    route = value.get("route")
    if not isinstance(route, str) or not _ROUTE_RE.match(route):
        raise PluginManifestError(
            "sidebar",
            "'sidebar.route' must be lowercase [a-z0-9-], starting alphanumeric.",
        )

    label = value.get("label")
    if not isinstance(label, str) or not label.strip():
        raise PluginManifestError("sidebar", "'sidebar.label' must be a non-empty string.")

    category = value.get("category")
    if category not in KNOWN_SIDEBAR_CATEGORIES:
        raise PluginManifestError(
            "sidebar",
            f"'sidebar.category' must be one of {sorted(KNOWN_SIDEBAR_CATEGORIES)}.",
        )

    icon = value.get("icon", _DEFAULT_SIDEBAR_ICON)
    if icon not in KNOWN_SIDEBAR_ICONS:
        raise PluginManifestError(
            "sidebar",
            f"'sidebar.icon' must be one of {sorted(KNOWN_SIDEBAR_ICONS)}.",
        )

    return SidebarSpec(route=route, label=label.strip(), category=category, icon=icon)


def _parse_hook(value, provides: list) -> HookSpec | None:
    """Validate ``[hook]``. Required iff ``"hook"`` is in ``provides``; an
    error either way if the two disagree, same reasoning as ``_parse_sidebar``."""
    if "hook" not in provides:
        if value is not None:
            raise PluginManifestError(
                "hook", "'[hook]' is set but 'hook' is not in 'provides'.",
            )
        return None

    if not isinstance(value, dict):
        raise PluginManifestError(
            "hook", "'hook' is in 'provides' but '[hook]' is missing.",
        )

    host = value.get("host")
    if not isinstance(host, str) or not _ROUTE_RE.match(host):
        raise PluginManifestError(
            "hook",
            "'hook.host' must be lowercase [a-z0-9-], starting alphanumeric.",
        )

    return HookSpec(host=host)


def _scan_dir(apps_dir: Path, source: str, seen: set[str]) -> list[PluginManifest]:
    if not apps_dir.is_dir():
        return []
    found: list[PluginManifest] = []
    for child in sorted(apps_dir.iterdir()):
        if not child.is_dir() or not (child / MANIFEST_NAME).is_file():
            continue
        try:
            manifest = parse_manifest(child, source)
        except PluginManifestError as exc:
            logger.warning("skipping plugin %s: %s", child.name, exc)
            continue
        if manifest.name in seen:
            logger.warning(
                "skipping %s plugin %s: a built-in plugin already owns that id",
                source, manifest.name,
            )
            continue
        seen.add(manifest.name)
        found.append(manifest)
    return found


def discover_plugins(
    builtin_dir: Path, community_dir: Path | None = None,
) -> list[PluginManifest]:
    """Every valid plugin, built-ins first then community, sorted by name
    within each tier.

    *builtin_dir* is ``src/plugins/apps/`` (ships in the repo); *community_dir*
    is ``<plugins_dir>/apps/`` (drop-ins). A folder with a missing/invalid
    ``plugin.toml`` is logged and skipped. A built-in id wins an id collision --
    the community folder of the same name is skipped.
    """
    seen: set[str] = set()
    result = _scan_dir(builtin_dir, SOURCE_BUILTIN, seen)
    if community_dir is not None:
        result.extend(_scan_dir(community_dir, SOURCE_COMMUNITY, seen))
    return result
