"""Install a plugin or theme from a source repo's GitHub tarball.

The operator has already added the source (the trust decision) and browsed
its ``repo.json`` catalog. This does the actual fetch:

  1. download ``api.github.com/repos/<o>/<r>/tarball/<ref>`` (a ``.tar.gz``
     with a single ``<owner>-<repo>-<sha>/`` top dir) -- stdlib only, no
     ``git``, runs as the unprivileged ``meshpoint`` user
  2. extract **only** the one plugin's subtree (``apps/<id>/`` or
     ``themes/<id>/``), rejecting any unsafe tar member
  3. re-validate the extracted folder with Meshpoint's own
     ``parse_manifest`` (apps) -- the ``repo.json`` catalog is never
     trusted for this
  4. move it into ``plugins/apps/<id>/`` (or ``plugins/themes/<id>/``)

FastAPI-free so it unit-tests on the Mac with a fixture tarball.
``setup.sh`` is **not** run here -- that stays the operator's separate,
explicit "Run setup" step.
"""

from __future__ import annotations

import logging
import re
import shutil
import tarfile
import tempfile
from src.plugins.network import open_github
from pathlib import Path

from src.plugins.manifest import PluginManifest, PluginManifestError, parse_manifest
from src.plugins.sources import tarball_url

logger = logging.getLogger(__name__)

_TIMEOUT_S = 30
_MAX_TARBALL_BYTES = 25 * 1024 * 1024          # compressed download cap
_MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024     # sum of extracted member sizes
_MAX_MEMBERS = 4000                            # entries in the subtree


class PluginInstallError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _download_tarball(owner: str, repo: str, ref: str, dest: Path) -> None:
    url = tarball_url(owner, repo, ref)
    try:
        with open_github(url, timeout=_TIMEOUT_S) as resp, open(dest, "wb") as fh:
            total = 0
            while chunk := resp.read(64 * 1024):
                total += len(chunk)
                if total > _MAX_TARBALL_BYTES:
                    raise PluginInstallError(
                        "size", f"archive exceeds {_MAX_TARBALL_BYTES // 1024 // 1024} MB",
                    )
                fh.write(chunk)
    except PluginInstallError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PluginInstallError("fetch", f"could not download {url}: {exc}") from exc


def _safe_members(tar: tarfile.TarFile, subpath: str):
    """Yield (member, relative_path) for the tar members that live under
    ``<toplevel>/<subpath>/`` and are plain files or dirs. Anything else --
    a symlink, hardlink, device, an entry with ``..``, an absolute path --
    aborts the whole install rather than being silently skipped (the same
    stance ``restore_service.py`` takes)."""
    names = tar.getnames()
    if not names:
        raise PluginInstallError("archive", "the archive is empty")
    toplevel = names[0].split("/", 1)[0]
    prefix = f"{toplevel}/{subpath.strip('/')}/"

    matched = False
    count = 0
    total_bytes = 0
    for member in tar.getmembers():
        name = member.name
        if name == prefix.rstrip("/"):
            continue
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):].strip("/")
        if not rel:
            continue  # the plugin's own top dir entry -- nothing to write
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise PluginInstallError("archive", f"unsafe path in archive: {name!r}")
        if not (member.isfile() or member.isdir()):
            raise PluginInstallError(
                "archive", f"archive member {name!r} is not a regular file or dir",
            )
        # Bound the extraction -- the 25 MB compressed cap says nothing
        # about the uncompressed size, and a hostile source could ship a
        # gzip bomb that fills the disk. This checks the header's declared
        # size; stage_from_tarball also caps the real bytes written.
        count += 1
        total_bytes += max(member.size, 0)
        if count > _MAX_MEMBERS:
            raise PluginInstallError("archive", f"more than {_MAX_MEMBERS} files in {subpath!r}")
        if total_bytes > _MAX_UNCOMPRESSED_BYTES:
            raise PluginInstallError(
                "archive",
                f"{subpath!r} unpacks to more than "
                f"{_MAX_UNCOMPRESSED_BYTES // 1024 // 1024} MB",
            )
        matched = True
        yield member, rel

    if not matched:
        raise PluginInstallError(
            "archive", f"{subpath!r} is not in the repo at that ref",
        )


def _commit_from_toplevel(toplevel: str) -> str:
    """GitHub names a tarball's root dir ``<owner>-<repo>-<short-sha>``.
    The short SHA is always the final ``-``-delimited segment (owner and
    repo may themselves contain dashes). Returns ``""`` if it doesn't
    look like a commit -- provenance is best-effort, never a hard error."""
    tail = toplevel.rsplit("-", 1)[-1] if "-" in toplevel else ""
    return tail if re.fullmatch(r"[0-9a-f]{7,40}", tail) else ""


def stage_from_tarball(
    owner: str, repo: str, ref: str, subpath: str, plugin_id: str,
) -> tuple[Path, str]:
    """Download + extract just ``<subpath>/**`` into a fresh temp dir.
    Returns ``(plugin_folder, commit)`` -- ``plugin_folder`` is
    ``<tmp>/<plugin_id>/`` and ``commit`` is the short SHA the ref
    resolved to (from the archive's root dir name; ``""`` if unreadable).
    The caller cleans the temp dir's parent."""
    staging = Path(tempfile.mkdtemp(prefix="meshpoint-plugin-"))
    archive = staging / "src.tar.gz"
    try:
        _download_tarball(owner, repo, ref, archive)
        out_dir = staging / plugin_id
        out_dir.mkdir()
        written = 0
        commit = ""
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            if names:
                commit = _commit_from_toplevel(names[0].split("/", 1)[0])
            for member, rel in _safe_members(tar, subpath):
                target = out_dir / rel
                if out_dir.resolve() not in target.resolve().parents:
                    raise PluginInstallError("archive", "extracted path escapes plugin directory")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise PluginInstallError("archive", f"could not read {member.name!r}")
                with open(target, "wb") as fh:
                    while chunk := extracted.read(256 * 1024):
                        written += len(chunk)
                        if written > _MAX_UNCOMPRESSED_BYTES:
                            raise PluginInstallError(
                                "archive",
                                f"{subpath!r} unpacks to more than "
                                f"{_MAX_UNCOMPRESSED_BYTES // 1024 // 1024} MB",
                            )
                        fh.write(chunk)
        archive.unlink(missing_ok=True)
        return out_dir, commit
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_staged_app(staged_dir: Path) -> PluginManifest:
    """Run Meshpoint's own manifest validator on the extracted folder.
    Refuses ``locked = true`` -- that flag marks a plugin shipped *with*
    the fork, never something installed from a source."""
    try:
        manifest = parse_manifest(staged_dir)
    except PluginManifestError as exc:
        raise PluginInstallError("manifest", f"invalid plugin: {exc}") from exc
    if manifest.locked:
        raise PluginInstallError(
            "manifest",
            "this plugin sets 'locked = true', which is reserved for plugins "
            "shipped with Meshpoint -- a source plugin must be removable",
        )
    return manifest


def validate_staged_theme(staged_dir: Path, theme_id: str) -> dict:
    import json

    manifest_path = staged_dir / "theme.json"
    css_path = staged_dir / "theme.css"
    if not manifest_path.is_file() or not css_path.is_file():
        raise PluginInstallError("manifest", "a theme needs theme.json and theme.css")
    try:
        raw = json.loads(manifest_path.read_text("utf-8"))
    except ValueError as exc:
        raise PluginInstallError("manifest", f"theme.json is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PluginInstallError("manifest", "theme.json must be an object")
    if str(raw.get("id") or theme_id) != theme_id:
        raise PluginInstallError("manifest", "theme.json 'id' must match the folder")
    from src.api.theme_store import ThemeSaveError, validate_css
    try:
        validate_css(css_path.read_text(encoding="utf-8"))
    except (ThemeSaveError, UnicodeDecodeError) as exc:
        raise PluginInstallError("manifest", "Theme CSS is not a valid local palette") from exc
    return raw


def place(staged_dir: Path, dest_dir: Path) -> None:
    """Move a validated staged folder to its final home, replacing any
    existing folder of the same id (an update)."""
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        backup = dest_dir.with_name(dest_dir.name + ".replacing")
        shutil.rmtree(backup, ignore_errors=True)
        dest_dir.rename(backup)
        try:
            shutil.move(str(staged_dir), str(dest_dir))
        except BaseException:
            backup.rename(dest_dir)  # roll back
            raise
        shutil.rmtree(backup, ignore_errors=True)
    else:
        shutil.move(str(staged_dir), str(dest_dir))


def install_from_source(
    owner: str, repo: str, ref: str, entry: dict, community_dir: Path,
) -> dict:
    """End to end: stage -> validate -> place. *entry* is a catalog entry
    (``{id, kind, path, version, ...}``). *community_dir* is
    ``<plugins_dir>/apps`` -- themes go to its sibling ``themes/``.
    Returns ``{id, kind, version, has_setup, commit}``."""
    pid = entry["id"]
    kind = entry.get("kind", "app")
    subpath = entry["path"]

    staged, commit = stage_from_tarball(owner, repo, ref, subpath, pid)
    staging_root = staged.parent
    try:
        if kind == "theme":
            validate_staged_theme(staged, pid)
            dest = community_dir.parent / "themes" / pid
            has_setup, version = False, entry.get("version", "")
        else:
            manifest = validate_staged_app(staged)
            dest = community_dir / pid
            has_setup, version = manifest.setup is not None, manifest.version
        place(staged, dest)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    logger.info(
        "installed %s %s v%s (%s) from %s/%s@%s",
        kind, pid, version, commit or "unknown-commit", owner, repo, ref,
    )
    return {
        "id": pid, "kind": kind, "version": version,
        "has_setup": has_setup, "commit": commit,
    }


__all__ = [
    "PluginInstallError",
    "install_from_source",
    "place",
    "stage_from_tarball",
    "validate_staged_app",
    "validate_staged_theme",
]
