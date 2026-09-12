"""Tests for the drop-in theme writer/deleter.

FastAPI-free by design -- exercises src/api/theme_store.py directly, the
same way test_theme_registry does. The route wrappers in
src/api/routes/theme_routes.py just map ThemeSaveError.code -> HTTP.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.api.theme_store import (
    MAX_CSS_BYTES,
    ThemeSaveError,
    delete_theme,
    save_theme,
)

_BUILTINS = {"dark", "light", "high-contrast", "sunlight", "solarized-dark"}
_CSS = 'html[data-theme="x"] { --bg-primary: #fff; }'


class TestSaveTheme(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _spec(self, **over) -> dict:
        base = {"id": "my-theme", "label": "My Theme", "css": _CSS}
        base.update(over)
        return base

    def test_happy_path_writes_both_files(self) -> None:
        res = save_theme(self.dir, self._spec(author="Me", description="Nice."), _BUILTINS)
        self.assertEqual(res, {"id": "my-theme", "overwritten": False})
        folder = self.dir / "my-theme"
        manifest = json.loads((folder / "theme.json").read_text())
        self.assertEqual(manifest["id"], "my-theme")
        self.assertEqual(manifest["label"], "My Theme")
        self.assertEqual(manifest["author"], "Me")
        self.assertNotIn("order", manifest)
        self.assertNotIn("homepage", manifest)  # omitted when empty
        self.assertEqual((folder / "theme.css").read_text(), _CSS)

    def test_second_save_reports_overwritten(self) -> None:
        save_theme(self.dir, self._spec(), _BUILTINS)
        res = save_theme(self.dir, self._spec(label="Renamed"), _BUILTINS)
        self.assertTrue(res["overwritten"])
        manifest = json.loads((self.dir / "my-theme" / "theme.json").read_text())
        self.assertEqual(manifest["label"], "Renamed")

    def test_rejects_bad_slug(self) -> None:
        # note: save_theme lowercases first, so "Foo" -> "foo" is valid
        for bad in ["../evil", "a", "x" * 60, "has space", "-lead", "", "a/b", "a.b"]:
            with self.assertRaises(ThemeSaveError) as cm:
                save_theme(self.dir, self._spec(id=bad), _BUILTINS)
            self.assertEqual(cm.exception.code, "slug")

    def test_rejects_builtin_id(self) -> None:
        for bad in ["dark", "light", "sunlight"]:
            with self.assertRaises(ThemeSaveError) as cm:
                save_theme(self.dir, self._spec(id=bad), _BUILTINS)
            self.assertEqual(cm.exception.code, "reserved")

    def test_rejects_missing_label(self) -> None:
        with self.assertRaises(ThemeSaveError) as cm:
            save_theme(self.dir, self._spec(label="   "), _BUILTINS)
        self.assertEqual(cm.exception.code, "label")

    def test_rejects_import(self) -> None:
        css = '@import url("https://evil.example/x.css");\nhtml{--x:1}'
        with self.assertRaises(ThemeSaveError) as cm:
            save_theme(self.dir, self._spec(css=css), _BUILTINS)
        self.assertEqual(cm.exception.code, "import")

    def test_rejects_external_assets_and_escaped_imports(self) -> None:
        for css in ('html {background: url(https://example.invalid/image)}',
                    r'@\69mport "https://example.invalid/theme.css";',
                    'html {background: u/**/rl(https://example.invalid/image)}'):
            with self.subTest(css=css), self.assertRaises(ThemeSaveError):
                save_theme(self.dir, self._spec(css=css), _BUILTINS)

    def test_rejects_oversize_css(self) -> None:
        with self.assertRaises(ThemeSaveError) as cm:
            save_theme(self.dir, self._spec(css="/*" + "a" * MAX_CSS_BYTES + "*/"), _BUILTINS)
        self.assertEqual(cm.exception.code, "toobig")

    def test_sanitises_icon_and_homepage_and_truncates(self) -> None:
        res = save_theme(self.dir, self._spec(
            icon="skull", homepage="ftp://nope", description="d" * 300,
        ), _BUILTINS)
        manifest = json.loads((self.dir / res["id"] / "theme.json").read_text())
        self.assertEqual(manifest["icon"], "palette")
        self.assertNotIn("homepage", manifest)
        self.assertEqual(len(manifest["description"]), 120)

    def test_keeps_valid_icon_and_homepage(self) -> None:
        save_theme(self.dir, self._spec(icon="terminal", homepage="https://ok.example"), _BUILTINS)
        manifest = json.loads((self.dir / "my-theme" / "theme.json").read_text())
        self.assertEqual(manifest["icon"], "terminal")
        self.assertEqual(manifest["homepage"], "https://ok.example")

    def test_keeps_pack_icons(self) -> None:
        # icons introduced with the community pack (theme_glyphs.js)
        for icon in ("snowflake", "leaf", "wave", "droplet", "atom", "eye"):
            save_theme(self.dir, self._spec(id=f"t-{icon}", icon=icon), _BUILTINS)
            manifest = json.loads((self.dir / f"t-{icon}" / "theme.json").read_text())
            self.assertEqual(manifest["icon"], icon)

    def test_refuses_to_overwrite_locked_theme(self) -> None:
        save_theme(self.dir, self._spec(), _BUILTINS)
        manifest_path = self.dir / "my-theme" / "theme.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["locked"] = True
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaises(ThemeSaveError) as cm:
            save_theme(self.dir, self._spec(label="Hijacked"), _BUILTINS)
        self.assertEqual(cm.exception.code, "reserved")
        self.assertEqual(json.loads(manifest_path.read_text())["label"], "My Theme")


class TestDeleteTheme(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        save_theme(self.dir, {"id": "doomed", "label": "Doomed", "css": _CSS}, _BUILTINS)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_removes_the_folder(self) -> None:
        delete_theme(self.dir, "doomed", _BUILTINS)
        self.assertFalse((self.dir / "doomed").exists())

    def test_unknown_raises_filenotfound(self) -> None:
        with self.assertRaises(FileNotFoundError):
            delete_theme(self.dir, "ghost", _BUILTINS)

    def test_refuses_builtin(self) -> None:
        with self.assertRaises(ThemeSaveError) as cm:
            delete_theme(self.dir, "dark", _BUILTINS)
        self.assertEqual(cm.exception.code, "reserved")

    def test_refuses_traversal(self) -> None:
        with self.assertRaises(ThemeSaveError):
            delete_theme(self.dir, "../../etc", _BUILTINS)

    def test_refuses_locked_theme(self) -> None:
        manifest_path = self.dir / "doomed" / "theme.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["locked"] = True
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaises(ThemeSaveError) as cm:
            delete_theme(self.dir, "doomed", _BUILTINS)
        self.assertEqual(cm.exception.code, "reserved")
        self.assertTrue((self.dir / "doomed").is_dir())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
