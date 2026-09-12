"""Tests for the theme folder scanner (Spike 1 of the plugin work).

FastAPI-free by design -- exercises src/api/theme_registry.py directly,
the same way test_html_assets-style logic runs on the Mac without a
venv. The route in src/api/routes/theme_routes.py is a thin wrapper
over ``scan_themes`` and is covered by that.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.api.theme_registry import (
    inject_theme_links,
    scan_themes,
    stamp_default_theme,
    theme_link_tags,
)


def _write_theme(root: Path, name: str, manifest, css: str | None = None) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    if manifest is not None:
        (folder / "theme.json").write_text(
            manifest if isinstance(manifest, str) else json.dumps(manifest),
            encoding="utf-8",
        )
    if css is not None:
        (folder / "theme.css").write_text(css, encoding="utf-8")


class TestScanThemes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_dark_baseline_when_dir_missing(self) -> None:
        themes = scan_themes(self.root / "nope")
        self.assertEqual([t["id"] for t in themes], ["dark"])
        self.assertIsNone(themes[0]["css"])

    def test_sorted_by_order_then_label(self) -> None:
        _write_theme(self.root, "sunlight", {"label": "Sunlight", "order": 2}, "html{--x:1}")
        _write_theme(self.root, "high-contrast", {"label": "High contrast", "order": 1}, "html{--x:1}")
        _write_theme(self.root, "dark", {"label": "Dark", "order": 0}, "/* baseline */")
        _write_theme(self.root, "amber-mono", {"label": "Amber mono", "order": 3}, "html{--x:1}")

        self.assertEqual(
            [t["id"] for t in scan_themes(self.root)],
            ["dark", "high-contrast", "sunlight", "amber-mono"],
        )

    def test_comment_only_css_counts_as_no_css(self) -> None:
        _write_theme(self.root, "dark", {"label": "Dark", "order": 0},
                     "/* palette lives in dashboard.css */\n")
        _write_theme(self.root, "sunlight", {"label": "Sunlight", "order": 2},
                     "html[data-theme=sunlight]{--bg:#000}")

        by_id = {t["id"]: t for t in scan_themes(self.root)}
        self.assertIsNone(by_id["dark"]["css"])
        self.assertEqual(by_id["sunlight"]["css"], "/themes/sunlight/theme.css")

    def test_skips_malformed_and_non_object_manifests(self) -> None:
        _write_theme(self.root, "broken", "{not json", "html{--x:1}")
        _write_theme(self.root, "listy", "[1, 2, 3]", "html{--x:1}")
        _write_theme(self.root, "nomanifest", None, "html{--x:1}")
        _write_theme(self.root, "sunlight", {"label": "Sunlight", "order": 2}, "html{--x:1}")

        ids = [t["id"] for t in scan_themes(self.root)]
        self.assertEqual(sorted(ids), ["dark", "sunlight"])

    def test_id_defaults_to_folder_name_and_label_is_titlecased(self) -> None:
        _write_theme(self.root, "amber-mono", {"order": 3}, "html{--x:1}")
        entry = next(t for t in scan_themes(self.root) if t["id"] == "amber-mono")
        self.assertEqual(entry["label"], "Amber Mono")

    def test_bad_order_falls_back_without_crashing(self) -> None:
        _write_theme(self.root, "weird", {"label": "Weird", "order": "soon"}, "html{--x:1}")
        entry = next(t for t in scan_themes(self.root) if t["id"] == "weird")
        self.assertEqual(entry["order"], 100)


class TestPluginThemes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.core = base / "frontend" / "themes"
        self.plugins = base / "plugins" / "themes"
        _write_theme(self.core, "dark", {"label": "Dark", "order": 0}, "/* baseline */")
        _write_theme(self.core, "light", {"label": "Light", "order": 1}, "html{--x:1}")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_merges_core_and_plugin_dirs(self) -> None:
        _write_theme(self.plugins, "nord", {"label": "Nord", "order": 9}, "html{--x:1}")
        entries = scan_themes(self.core, self.plugins)
        by_id = {t["id"]: t for t in entries}
        self.assertEqual([t["id"] for t in entries], ["dark", "light", "nord"])
        self.assertEqual(by_id["nord"]["css"], "/plugins/themes/nord/theme.css")
        self.assertEqual(by_id["light"]["css"], "/themes/light/theme.css")
        self.assertEqual(by_id["light"]["source"], "builtin")
        self.assertEqual(by_id["nord"]["source"], "plugin")

    def test_builtins_sort_before_plugins_regardless_of_order(self) -> None:
        # A plugin theme with order 0 must still land after every built-in.
        _write_theme(self.plugins, "greedy", {"label": "Greedy", "order": 0}, "html{--x:1}")
        ids = [t["id"] for t in scan_themes(self.core, self.plugins)]
        self.assertEqual(ids, ["dark", "light", "greedy"])

    def test_plugin_entries_have_no_order_and_sort_by_normalised_label(self) -> None:
        _write_theme(self.plugins, "zulu", {"label": "Zulu"}, "html{--x:1}")
        _write_theme(self.plugins, "sneaky", {"label": "  -alpha"}, "html{--x:1}")
        _write_theme(self.plugins, "mid", {"label": "Mango"}, "html{--x:1}")
        plugins = [t for t in scan_themes(self.core, self.plugins) if t["source"] == "plugin"]
        self.assertEqual([t["id"] for t in plugins], ["sneaky", "mid", "zulu"])
        self.assertNotIn("order", plugins[0])

    def test_plugin_locked_field_defaults_false_and_is_carried_through(self) -> None:
        _write_theme(self.plugins, "nord", {"label": "Nord", "locked": True}, "html{--x:1}")
        _write_theme(self.plugins, "custom", {"label": "Custom"}, "html{--x:1}")
        by_id = {t["id"]: t for t in scan_themes(self.core, self.plugins)}
        self.assertTrue(by_id["nord"]["locked"])
        self.assertFalse(by_id["custom"]["locked"])
        self.assertNotIn("locked", by_id["light"])  # builtins don't carry it

    def test_author_fields_carried_through(self) -> None:
        _write_theme(
            self.plugins, "nord",
            {"label": "Nord", "author": "Arctic Ice Studio",
             "homepage": "https://nordtheme.com", "description": "Bluish."},
            "html{--x:1}",
        )
        nord = next(t for t in scan_themes(self.core, self.plugins) if t["id"] == "nord")
        self.assertEqual(nord["author"], "Arctic Ice Studio")
        self.assertEqual(nord["homepage"], "https://nordtheme.com")
        self.assertEqual(nord["description"], "Bluish.")
        light = next(t for t in scan_themes(self.core, self.plugins) if t["id"] == "light")
        self.assertEqual(light["author"], "")

    def test_core_theme_wins_id_collision(self) -> None:
        _write_theme(self.plugins, "light", {"label": "Impostor", "order": 2}, "html{--y:2}")
        by_id = {t["id"]: t for t in scan_themes(self.core, self.plugins)}
        self.assertEqual(by_id["light"]["label"], "Light")
        self.assertEqual(by_id["light"]["css"], "/themes/light/theme.css")

    def test_plugin_cannot_claim_dark(self) -> None:
        _write_theme(self.plugins, "dark", {"label": "Fake dark", "order": 0}, "html{--z:3}")
        by_id = {t["id"]: t for t in scan_themes(self.core, self.plugins)}
        self.assertIsNone(by_id["dark"]["css"])
        self.assertEqual(by_id["dark"]["label"], "Dark")

    def test_no_plugin_dir_is_unchanged(self) -> None:
        self.assertEqual(
            [t["id"] for t in scan_themes(self.core)],
            [t["id"] for t in scan_themes(self.core, self.plugins / "nope")],
        )

    def test_inject_emits_plugin_link(self) -> None:
        _write_theme(self.plugins, "nord", {"label": "Nord", "order": 9}, "html{--x:1}")
        html = "<html><head></head><body></body></html>"
        out = inject_theme_links(html, self.core, self.plugins, token="abc")
        self.assertIn('href="/plugins/themes/nord/theme.css?v=abc"', out)


class TestThemeLinkInjection(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write_theme(self.root, "dark", {"label": "Dark", "order": 0}, "/* baseline */")
        _write_theme(self.root, "sunlight", {"label": "Sunlight", "order": 2},
                     "html[data-theme=sunlight]{--bg:#000}")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_link_tags_only_for_themes_with_css(self) -> None:
        tags = theme_link_tags(scan_themes(self.root), token="abc")
        self.assertIn('href="/themes/sunlight/theme.css?v=abc"', tags)
        self.assertNotIn("/themes/dark/", tags)

    def test_inject_places_tags_before_head_close(self) -> None:
        html = "<html><head><title>x</title></head><body></body></html>"
        out = inject_theme_links(html, self.root, token="abc")
        self.assertIn('theme.css?v=abc"></head>', out)
        self.assertEqual(out.count("</head>"), 1)

    def test_inject_is_noop_without_head(self) -> None:
        html = "<div>fragment</div>"
        self.assertEqual(inject_theme_links(html, self.root), html)


class TestStampDefaultTheme(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write_theme(self.root, "nord", {"label": "Nord", "order": 6}, "html{--x:1}")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    _HTML = '<!doctype html>\n<html lang="en">\n<head></head>'

    def test_stamps_known_non_dark_theme(self) -> None:
        out = stamp_default_theme(self._HTML, "nord", self.root)
        self.assertIn('<html data-theme="nord" lang="en">', out)

    def test_noop_for_dark(self) -> None:
        self.assertEqual(stamp_default_theme(self._HTML, "dark", self.root), self._HTML)

    def test_noop_for_unknown_theme(self) -> None:
        self.assertEqual(stamp_default_theme(self._HTML, "bogus", self.root), self._HTML)

    def test_noop_when_already_stamped(self) -> None:
        html = '<html data-theme="light" lang="en">'
        self.assertEqual(stamp_default_theme(html, "nord", self.root), html)

    def test_noop_for_empty(self) -> None:
        self.assertEqual(stamp_default_theme(self._HTML, "", self.root), self._HTML)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
