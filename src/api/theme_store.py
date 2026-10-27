"""Write / delete drop-in themes under ``plugins/themes/<id>/``.

The theme builder (Settings -> Themes) posts a built theme here and the
"Installed themes" card deletes them. Kept free of FastAPI imports so the
validation + filesystem logic unit-tests on the Mac without a venv, same
pattern as ``src/api/theme_registry.py``; the route handlers in
``src/api/routes/theme_routes.py`` are thin wrappers that map
:class:`ThemeSaveError` codes onto HTTP status.

Only ``plugins/themes/`` is ever touched -- built-in themes live in
``frontend/themes/`` and their ids are refused here. A plugin theme can
also carry ``"locked": true`` in its ``theme.json`` (the community pack
and the repo's own example themes ship this way); locked folders can't
be overwritten or deleted through this module, only edited on disk.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

# No dot, no slash -> nothing that can escape the plugin themes dir.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")

MAX_CSS_BYTES = 64 * 1024

# Keep in sync with THEME_GLYPH_KEYS in frontend/js/theme_glyphs.js;
# anything else falls back to "palette".
_KNOWN_ICONS = {
    "moon", "contrast", "sun", "day", "monitor", "terminal", "palette", "circle",
    "snowflake", "leaf", "flower", "wave", "droplet", "sparkles", "atom",
    "mountain", "eye",
}

_IMPORT_RE = re.compile(r"@import\b", re.IGNORECASE)


class ThemeSaveError(Exception):
    """Raised for a rejected save/delete. ``code`` picks the HTTP status."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_locked(folder: Path) -> bool:
    """True when ``folder/theme.json`` sets ``"locked": true``."""
    try:
        raw = json.loads((folder / "theme.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return bool(isinstance(raw, dict) and raw.get("locked"))


def _chown_hint(path: Path) -> str:
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "meshpoint"
    return (
        f"Cannot write {path} -- the service user lacks permission. "
        f"Fix with: sudo chown -R {user}:{user} {path.parent}"
    )


def validate_css(css: str) -> None:
    """Theme palettes may not trigger external stylesheet or asset requests."""
    if len(css.encode("utf-8")) > MAX_CSS_BYTES:
        raise ThemeSaveError("toobig", f"theme.css exceeds {MAX_CSS_BYTES // 1024} KiB.")
    if _IMPORT_RE.search(css):
        raise ThemeSaveError(
            "import",
            "theme.css can't use @import -- a remote import leaks every "
            "dashboard visitor's IP to a third party. Inline the rules instead.",
        )
    normalized = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    if "\\" in normalized or re.search(r"(?:url\s*\(|@import\b)", normalized, re.I):
        raise ThemeSaveError("import", "Theme CSS cannot load external assets or use escaped rules.")


def save_theme(plugin_dir: Path, spec: dict, builtin_ids: set[str]) -> dict:
    """Write ``plugin_dir/<id>/{theme.json,theme.css}`` from *spec*.

    *spec* keys: ``id``, ``label``, ``css`` (required); ``icon``,
    ``author``, ``homepage``, ``description`` (optional). Returns
    ``{"id", "overwritten"}``. Raises :class:`ThemeSaveError`.
    """
    theme_id = str(spec.get("id") or "").strip().lower()
    if not SLUG_RE.match(theme_id):
        raise ThemeSaveError(
            "slug",
            "Theme id must be 2-39 chars, lowercase letters/digits/hyphens, "
            "starting with a letter or digit.",
        )
    if theme_id in builtin_ids or theme_id == "dark":
        raise ThemeSaveError("reserved", f"{theme_id!r} is a built-in theme id.")

    label = str(spec.get("label") or "").strip()[:60]
    if not label:
        raise ThemeSaveError("label", "Theme needs a name.")

    css = str(spec.get("css") or "")
    validate_css(css)

    icon = str(spec.get("icon") or "").strip()
    if icon not in _KNOWN_ICONS:
        icon = "palette"

    homepage = str(spec.get("homepage") or "").strip()
    if not homepage.startswith(("http://", "https://")):
        homepage = ""

    manifest: dict = {"id": theme_id, "label": label, "icon": icon}
    author = str(spec.get("author") or "").strip()[:80]
    description = str(spec.get("description") or "").strip()[:120]
    if author:
        manifest["author"] = author
    if homepage:
        manifest["homepage"] = homepage
    if description:
        manifest["description"] = description

    folder = plugin_dir / theme_id
    if (folder.is_symlink() or folder.resolve().parent != plugin_dir.resolve()
            or any((folder / name).is_symlink() for name in ("theme.json", "theme.css"))):
        raise ThemeSaveError("slug", "Theme paths cannot be symbolic links.")
    overwritten = folder.is_dir()
    if overwritten and _is_locked(folder):
        raise ThemeSaveError("reserved", f"{theme_id!r} is a locked theme and can't be overwritten.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "theme.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (folder / "theme.css").write_text(css, encoding="utf-8")
    except PermissionError as exc:
        raise ThemeSaveError("perm", _chown_hint(folder)) from exc

    return {"id": theme_id, "overwritten": overwritten}


def delete_theme(plugin_dir: Path, theme_id: str, builtin_ids: set[str]) -> None:
    """Remove ``plugin_dir/<theme_id>/``. Raises :class:`ThemeSaveError`
    (``slug`` / ``reserved``) or ``FileNotFoundError``."""
    theme_id = str(theme_id or "").strip().lower()
    if not SLUG_RE.match(theme_id):
        raise ThemeSaveError("slug", "Bad theme id.")
    if theme_id in builtin_ids or theme_id == "dark":
        raise ThemeSaveError("reserved", f"{theme_id!r} is a built-in theme and can't be deleted.")

    target = plugin_dir / theme_id
    if target.is_symlink() or target.resolve().parent != plugin_dir.resolve():
        raise ThemeSaveError("slug", "Bad theme id.")
    if not target.is_dir():
        raise FileNotFoundError(theme_id)
    if _is_locked(target):
        raise ThemeSaveError("reserved", f"{theme_id!r} is a locked theme and can't be deleted.")

    try:
        shutil.rmtree(target)
    except PermissionError as exc:
        raise ThemeSaveError("perm", _chown_hint(target)) from exc
