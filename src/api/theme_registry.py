"""Discover dashboard themes from two locations.

* ``frontend/themes/<id>/`` -- the built-in themes, curated and reviewed
  as part of the app. Served through the ``/`` static mount at
  ``/themes/<id>/theme.css``.
* ``plugins/themes/<id>/`` -- extra / community themes, dropped in
  without touching the app. Served through a dedicated
  ``/plugins/themes`` mount. This is the first concrete ``plugins/``
  directory (see ``memory/plugin-architecture-review.md``).

Each theme folder holds a ``theme.json`` manifest and a ``theme.css``;
adding one and restarting makes the theme show up in the picker with no
code change. A built-in theme id always wins an id collision with a
plugin theme, and a plugin folder can never claim ``dark``.

``dark`` is a folder too, but a registry-entry-only one: its ``theme.css``
is empty because the baseline palette lives on bare ``:root`` in
``dashboard.css`` (a synchronously-loaded stylesheet, so no flash).

Kept free of FastAPI imports so the scan + HTML injection unit-test on
the Mac, same pattern as ``src/api/html_assets.py``.
"""

from __future__ import annotations

import json
from html import escape
import logging
import re
from pathlib import Path

from src.api.html_assets import BOOT_TOKEN

logger = logging.getLogger(__name__)

# The built-in baseline. Always present in the returned list and always
# the fallback selection even if its folder is missing.
DEFAULT_THEME_ID = "dark"


def scan_themes(themes_dir: Path, plugin_themes_dir: Path | None = None) -> list[dict]:
    """Return the sorted theme manifest list.

    Built-in themes come from *themes_dir* (``/themes/<id>/theme.css``);
    optional extra themes from *plugin_themes_dir*
    (``/plugins/themes/<id>/theme.css``). Each entry:
    ``{"id", "label", "icon", "css", "source", "author", "homepage",
    "description"}`` -- ``css`` is the browser URL for a non-empty
    ``theme.css`` or ``None``; ``source`` is ``"builtin"`` or
    ``"plugin"``; ``author``/``homepage``/``description`` are ``""`` when
    absent. Built-in entries also carry ``order`` (an integer curation
    sequence); plugin entries do not -- they sort alphabetically. Plugin
    entries instead carry ``locked`` (bool, from the manifest's
    ``"locked"`` field) -- ``theme_store.py`` refuses to overwrite or
    delete a locked folder, so the UI can hide the delete affordance for
    themes that shipped with the app rather than ones a user saved.

    Folders with a missing/unparseable ``theme.json`` are skipped with a
    warning. A built-in id wins an id collision with a plugin theme; a
    plugin folder can't claim ``dark``. Built-ins always sort first (by
    ``order`` then label); plugin themes follow, sorted by a normalised
    label so a leading ``-``/space can't game the order.
    """
    themes: list[dict] = []
    seen: set[str] = set()

    _scan_dir(themes_dir, "/themes", "builtin", themes, seen)
    if plugin_themes_dir is not None:
        _scan_dir(
            plugin_themes_dir, "/plugins/themes", "plugin", themes, seen,
            block={DEFAULT_THEME_ID},
        )

    if DEFAULT_THEME_ID not in seen:
        # The baseline is valid even without a folder on disk.
        themes.append(
            {
                "id": DEFAULT_THEME_ID, "label": "Dark", "order": 0,
                "icon": "moon", "css": None, "source": "builtin",
                "author": "", "homepage": "", "description": "",
            }
        )

    themes.sort(key=_sort_key)
    return themes


def _sort_key(theme: dict) -> tuple:
    """Built-ins first (by ``order`` then label); plugins after, by a
    normalised label (leading non-alphanumerics stripped) so a ``-`` or
    space prefix can't float a drop-in to the top of its group."""
    label_key = re.sub(r"^[^a-z0-9]+", "", theme["label"].strip().lower())
    if theme["source"] == "builtin":
        return (0, theme.get("order", 100), label_key)
    return (1, 0, label_key)


def _scan_dir(
    themes_dir: Path,
    css_url_prefix: str,
    source: str,
    themes: list[dict],
    seen: set[str],
    block: set[str] | None = None,
) -> None:
    """Append the themes found in *themes_dir* to *themes*, in place.

    *source* is stamped on each entry (``"builtin"`` / ``"plugin"``).
    *seen* is shared across calls so an id discovered by an earlier call
    (a built-in) shadows a later one (a plugin). *block* is a set of ids
    this call must never emit regardless of *seen*.
    """
    block = block or set()
    if not themes_dir.is_dir():
        return
    for entry in sorted(themes_dir.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        manifest_path = entry / "theme.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            continue
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError, UnicodeDecodeError):
            logger.warning("theme: skipping %s -- unreadable theme.json", entry.name)
            continue
        if not isinstance(raw, dict):
            logger.warning("theme: skipping %s -- theme.json is not an object", entry.name)
            continue

        theme_id = str(raw.get("id") or entry.name).strip()
        if (not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,38}", theme_id)
                or theme_id != entry.name or theme_id in seen
                or (entry / "theme.css").is_symlink()):
            continue
        if theme_id in block:
            logger.warning("theme: skipping %s -- %r is reserved", entry.name, theme_id)
            continue
        seen.add(theme_id)

        has_css = _has_css_rules(entry / "theme.css")

        entry_dict = {
            "id": theme_id,
            "label": str(raw.get("label") or theme_id.replace("-", " ").title()),
            "icon": str(raw.get("icon") or ""),
            "css": f"{css_url_prefix}/{theme_id}/theme.css" if has_css else None,
            "source": source,
            "author": str(raw.get("author") or ""),
            "homepage": str(raw.get("homepage") or ""),
            "description": str(raw.get("description") or ""),
        }
        # `order` is a built-in-only curation sequence; plugin themes sort
        # alphabetically so contributors don't pick a meaningless number.
        if source == "builtin":
            entry_dict["order"] = _as_int(raw.get("order"), default=100)
        else:
            entry_dict["locked"] = bool(raw.get("locked"))
        themes.append(entry_dict)


def theme_link_tags(themes: list[dict], token: str = BOOT_TOKEN) -> str:
    """``<link>`` tags for every theme that ships its own CSS.

    Server-rendered into ``<head>`` so a persisted non-default theme
    paints correctly on first load instead of flashing the baseline
    while a script fetches the manifest.
    """
    return "".join(
        f'<link rel="stylesheet" href="{escape(t["css"], quote=True)}?v={escape(token, quote=True)}">'
        for t in themes
        if t.get("css")
    )


def inject_theme_links(
    html: str,
    themes_dir: Path,
    plugin_themes_dir: Path | None = None,
    token: str = BOOT_TOKEN,
) -> str:
    """Insert :func:`theme_link_tags` just before ``</head>`` in *html*."""
    tags = theme_link_tags(scan_themes(themes_dir, plugin_themes_dir), token)
    if not tags or "</head>" not in html:
        return html
    return html.replace("</head>", tags + "</head>", 1)


_HTML_TAG_RE = re.compile(r"<html\b(?![^>]*\bdata-theme=)", re.IGNORECASE)


def stamp_default_theme(
    html: str,
    theme_id: str,
    themes_dir: Path,
    plugin_themes_dir: Path | None = None,
) -> str:
    """Stamp ``data-theme`` on the ``<html>`` tag so the server default
    paints on first load with no flash. No-op for ``dark`` (the bare
    ``:root`` baseline) or an unknown id. A per-browser choice in
    localStorage still overrides this once ``theme_controller.js`` runs.
    """
    theme_id = (theme_id or "").strip()
    if not theme_id or theme_id == DEFAULT_THEME_ID:
        return html
    if theme_id not in {t["id"] for t in scan_themes(themes_dir, plugin_themes_dir)}:
        return html
    return _HTML_TAG_RE.sub(f'<html data-theme="{theme_id}"', html, count=1)


_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _has_css_rules(css_file: Path) -> bool:
    """True when ``theme.css`` carries anything past comments/whitespace.

    A comment-only placeholder (``dark``'s) counts as no CSS, so it gets
    no ``<link>`` and no wasted request.
    """
    if not css_file.is_file():
        return False
    try:
        body = css_file.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(_CSS_COMMENT_RE.sub("", body).strip())


def _as_int(value, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
