"""src/plugins/installer.py -- download + extract + validate a plugin from a
source repo's GitHub tarball. The network fetch is stubbed with an in-test
``.tar.gz`` fixture; everything else (subtree extraction, path-safety,
manifest re-validation, atomic-ish place) runs for real."""

from __future__ import annotations

import io
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.plugins import installer
from src.plugins.installer import (
    PluginInstallError,
    install_from_source,
    place,
    stage_from_tarball,
    validate_staged_app,
)

_TOPLEVEL = "javastraat-meshpoint-plugins-deadbeef"

_PLUGIN_TOML = """\
name = "hello-svc"
version = "0.2.0"
meshpoint_api = 1
provides = ["service"]

[meta]
description = "a test plugin"
author = "einstein"
"""


def _add(tar: tarfile.TarFile, name: str, body: str) -> None:
    data = body.encode("utf-8")
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _make_tarball(
    *, plugin_toml: str = _PLUGIN_TOML, extra: list | None = None,
) -> Path:
    """A repo archive shaped like GitHub's: a single ``<owner>-<repo>-<sha>/``
    top dir. Ships two plugins so tests can prove only the requested subtree
    comes out."""
    fd, path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    with tarfile.open(path, "w:gz") as tar:
        _add(tar, f"{_TOPLEVEL}/README.md", "# repo\n")
        _add(tar, f"{_TOPLEVEL}/repo.json", "{}\n")
        _add(tar, f"{_TOPLEVEL}/apps/hello-svc/plugin.toml", plugin_toml)
        _add(tar, f"{_TOPLEVEL}/apps/hello-svc/backend/__init__.py", "def register(reg):\n    pass\n")
        _add(tar, f"{_TOPLEVEL}/apps/other-plugin/plugin.toml", 'name = "other-plugin"\n')
        for info, body in (extra or []):
            tar.addfile(info, io.BytesIO(body) if body is not None else None)
    return Path(path)


class StageFromTarball(unittest.TestCase):
    def setUp(self) -> None:
        self.tarball = _make_tarball()
        self.addCleanup(lambda: self.tarball.unlink(missing_ok=True))
        patcher = mock.patch.object(
            installer, "_download_tarball",
            side_effect=lambda owner, repo, ref, dest: shutil.copyfile(self.tarball, dest),
        )
        self.dl = patcher.start()
        self.addCleanup(patcher.stop)

    def _stage(self, subpath="apps/hello-svc", pid="hello-svc") -> Path:
        out, commit = stage_from_tarball("o", "r", "main", subpath, pid)
        self._last_commit = commit
        self.addCleanup(lambda: shutil.rmtree(out.parent, ignore_errors=True))
        return out

    def test_reports_the_commit_from_the_archive_root_dir(self) -> None:
        self._stage()
        # _TOPLEVEL is "<owner>-<repo>-deadbeef"
        self.assertEqual(self._last_commit, "deadbeef")

    def test_extracts_only_the_requested_subtree(self) -> None:
        out = self._stage()
        self.assertTrue((out / "plugin.toml").is_file())
        self.assertTrue((out / "backend" / "__init__.py").is_file())
        # nothing from outside apps/hello-svc/
        self.assertFalse((out / "README.md").exists())
        self.assertFalse((out.parent / "other-plugin").exists())
        self.assertEqual(out.name, "hello-svc")

    def test_explicit_directory_members_are_fine(self) -> None:
        # GitHub tarballs ship explicit dir entries (trailing slash),
        # including the plugin's own top dir -- these must not trip the
        # path-safety check.
        dirs = []
        for dname in ("apps/", "apps/hello-svc/", "apps/hello-svc/backend/"):
            di = tarfile.TarInfo(name=f"{_TOPLEVEL}/{dname}")
            di.type = tarfile.DIRTYPE
            dirs.append((di, None))
        self.tarball.unlink()
        self.tarball = _make_tarball(extra=dirs)
        out = self._stage()
        self.assertTrue((out / "plugin.toml").is_file())

    def test_missing_subtree_is_an_error(self) -> None:
        with self.assertRaises(PluginInstallError) as cm:
            self._stage(subpath="apps/nope", pid="nope")
        self.assertEqual(cm.exception.code, "archive")

    def test_parent_traversal_member_aborts(self) -> None:
        bad = tarfile.TarInfo(name=f"{_TOPLEVEL}/apps/hello-svc/../../../etc/evil")
        bad.size = 3
        self.tarball.unlink()
        self.tarball = _make_tarball(extra=[(bad, b"x\n\n"[:3])])
        with self.assertRaises(PluginInstallError) as cm:
            self._stage()
        self.assertEqual(cm.exception.code, "archive")

    def test_uncompressed_size_cap(self) -> None:
        with mock.patch.object(installer, "_MAX_UNCOMPRESSED_BYTES", 8):
            with self.assertRaises(PluginInstallError) as cm:
                self._stage()
        self.assertEqual(cm.exception.code, "archive")
        self.assertIn("MB", str(cm.exception))

    def test_member_count_cap(self) -> None:
        with mock.patch.object(installer, "_MAX_MEMBERS", 1):
            with self.assertRaises(PluginInstallError) as cm:
                self._stage()
        self.assertEqual(cm.exception.code, "archive")

    def test_symlink_member_aborts(self) -> None:
        link = tarfile.TarInfo(name=f"{_TOPLEVEL}/apps/hello-svc/passwd")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        self.tarball.unlink()
        self.tarball = _make_tarball(extra=[(link, None)])
        with self.assertRaises(PluginInstallError) as cm:
            self._stage()
        self.assertEqual(cm.exception.code, "archive")


class ValidateStagedApp(unittest.TestCase):
    def _write(self, toml: str) -> Path:
        d = Path(tempfile.mkdtemp()) / "hello-svc"
        d.mkdir(parents=True)
        (d / "plugin.toml").write_text(toml, encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(d.parent, ignore_errors=True))
        return d

    def test_accepts_a_good_manifest(self) -> None:
        manifest = validate_staged_app(self._write(_PLUGIN_TOML))
        self.assertEqual(manifest.name, "hello-svc")
        self.assertEqual(manifest.version, "0.2.0")

    def test_rejects_locked(self) -> None:
        locked_toml = _PLUGIN_TOML.replace(
            'provides = ["service"]', 'provides = ["service"]\nlocked = true',
        )
        with self.assertRaises(PluginInstallError) as cm:
            validate_staged_app(self._write(locked_toml))
        self.assertEqual(cm.exception.code, "manifest")
        self.assertIn("locked", str(cm.exception))

    def test_rejects_a_broken_manifest(self) -> None:
        with self.assertRaises(PluginInstallError):
            validate_staged_app(self._write('name = "hello-svc"\n'))  # no version/api


class Place(unittest.TestCase):
    def test_replaces_an_existing_folder(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        dest = root / "community" / "hello-svc"
        dest.mkdir(parents=True)
        (dest / "OLD").write_text("old", encoding="utf-8")

        staged = root / "staging" / "hello-svc"
        staged.mkdir(parents=True)
        (staged / "NEW").write_text("new", encoding="utf-8")

        place(staged, dest)
        self.assertTrue((dest / "NEW").is_file())
        self.assertFalse((dest / "OLD").exists())
        self.assertFalse(staged.exists())


class InstallFromSource(unittest.TestCase):
    def setUp(self) -> None:
        self.tarball = _make_tarball()
        self.addCleanup(lambda: self.tarball.unlink(missing_ok=True))
        patcher = mock.patch.object(
            installer, "_download_tarball",
            side_effect=lambda owner, repo, ref, dest: shutil.copyfile(self.tarball, dest),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plugins_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.plugins_dir, ignore_errors=True))
        self.community = self.plugins_dir / "apps"
        self.community.mkdir()

    def test_end_to_end(self) -> None:
        entry = {
            "id": "hello-svc", "kind": "app", "path": "apps/hello-svc",
            "version": "0.2.0", "meshpoint_api": 1,
        }
        result = install_from_source("javastraat", "meshpoint-plugins", "main", entry, self.community)
        self.assertEqual(result["id"], "hello-svc")
        self.assertEqual(result["version"], "0.2.0")
        self.assertEqual(result["commit"], "deadbeef")
        self.assertFalse(result["has_setup"])
        self.assertTrue((self.community / "hello-svc" / "plugin.toml").is_file())
        self.assertTrue((self.community / "hello-svc" / "backend" / "__init__.py").is_file())
        # a second install (an "update") replaces cleanly
        install_from_source("javastraat", "meshpoint-plugins", "main", entry, self.community)
        self.assertTrue((self.community / "hello-svc" / "plugin.toml").is_file())


if __name__ == "__main__":
    unittest.main()
