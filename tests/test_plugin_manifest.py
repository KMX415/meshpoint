"""Tests for plugins/apps/<name>/plugin.toml parsing + discovery.

Pure Python -- src/plugins/manifest.py has no FastAPI import (stdlib tomllib
only), same as src/api/theme_registry.py.
"""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from src.plugins.manifest import (
    PLUGIN_API_VERSION,
    PluginManifestError,
    discover_plugins,
    parse_manifest,
)

_VALID = """\
name = "acars"
version = "0.1.0"
meshpoint_api = 1
provides = ["listener", "routes"]
"""


def _write_plugin(root: Path, name: str, toml: str, *, extra_files=()) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "plugin.toml").write_text(toml, encoding="utf-8")
    for fname in extra_files:
        f = d / fname
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("#!/bin/sh\n", encoding="utf-8")
    return d


class TestParseManifest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _code(self, name: str, toml: str, **kw) -> str:
        d = _write_plugin(self.root, name, toml, **kw)
        with self.assertRaises(PluginManifestError) as ctx:
            parse_manifest(d)
        return ctx.exception.code

    def test_valid_minimal(self) -> None:
        d = _write_plugin(self.root, "acars", _VALID)
        m = parse_manifest(d)
        self.assertEqual(m.name, "acars")
        self.assertEqual(m.version, "0.1.0")
        self.assertEqual(m.api_version, 1)
        self.assertEqual(m.provides, ("listener", "routes"))
        self.assertEqual(m.apt, ())
        self.assertIsNone(m.setup)
        self.assertIsNone(m.check)
        self.assertIsNone(m.check_path)
        self.assertEqual(m.description, "")
        self.assertEqual(m.homepage, "")
        self.assertEqual(m.author, "")
        self.assertEqual(m.path, d)
        self.assertIsNone(m.setup_path)
        self.assertEqual(m.source, "community")
        self.assertFalse(m.is_builtin)
        self.assertEqual(m.frontend_scripts, ())
        self.assertEqual(m.frontend_styles, ())
        self.assertFalse(m.locked)

    def test_source_builtin(self) -> None:
        from src.plugins.manifest import SOURCE_BUILTIN

        d = _write_plugin(self.root, "acars", _VALID)
        m = parse_manifest(d, SOURCE_BUILTIN)
        self.assertEqual(m.source, "builtin")
        self.assertTrue(m.is_builtin)

    def test_valid_full(self) -> None:
        toml = _VALID + """
[deps]
apt = ["cmake", "pkg-config"]
setup = "setup.sh"
check = "check.sh"

[meta]
description = "ACARS decoding"
homepage = "https://example.org"
author = "Einstein"
"""
        d = _write_plugin(
            self.root, "acars", toml, extra_files=("setup.sh", "check.sh"),
        )
        m = parse_manifest(d)
        self.assertEqual(m.apt, ("cmake", "pkg-config"))
        self.assertEqual(m.setup, "setup.sh")
        self.assertEqual(m.setup_path, d / "setup.sh")
        self.assertEqual(m.check, "check.sh")
        self.assertEqual(m.check_path, d / "check.sh")
        self.assertEqual(m.description, "ACARS decoding")
        self.assertEqual(m.author, "Einstein")

    def test_missing_manifest(self) -> None:
        d = self.root / "empty"
        d.mkdir()
        with self.assertRaises(PluginManifestError) as ctx:
            parse_manifest(d)
        self.assertEqual(ctx.exception.code, "missing")

    def test_bad_toml(self) -> None:
        self.assertEqual(self._code("x", "name = "), "toml")

    def test_bad_name_slug(self) -> None:
        self.assertEqual(
            self._code("Acars", _VALID.replace('"acars"', '"Acars"')), "name",
        )

    def test_name_must_match_folder(self) -> None:
        self.assertEqual(self._code("other", _VALID), "name")

    def test_missing_version(self) -> None:
        toml = _VALID.replace('version = "0.1.0"\n', "")
        self.assertEqual(self._code("acars", toml), "version")

    def test_api_not_int(self) -> None:
        self.assertEqual(
            self._code("acars", _VALID.replace("meshpoint_api = 1", 'meshpoint_api = "1"')),
            "api",
        )

    def test_api_too_new(self) -> None:
        toml = _VALID.replace("meshpoint_api = 1", f"meshpoint_api = {PLUGIN_API_VERSION + 1}")
        self.assertEqual(self._code("acars", toml), "api")

    def test_api_zero(self) -> None:
        self.assertEqual(
            self._code("acars", _VALID.replace("meshpoint_api = 1", "meshpoint_api = 0")),
            "api",
        )

    def test_provides_empty(self) -> None:
        self.assertEqual(
            self._code("acars", _VALID.replace('["listener", "routes"]', "[]")),
            "provides",
        )

    def test_provides_unknown(self) -> None:
        self.assertEqual(
            self._code("acars", _VALID.replace('"routes"', '"telepathy"')),
            "provides",
        )

    def test_capture_and_protocol_are_known_provides_values(self) -> None:
        # Same precedent as bare "listener": neither needs its own TOML
        # table -- everything a capture-source/protocol plugin needs comes
        # from reg.config and closures at register() time.
        toml = _VALID.replace(
            'provides = ["listener", "routes"]',
            'provides = ["capture", "protocol", "routes"]',
        )
        d = _write_plugin(self.root, "acars", toml)
        m = parse_manifest(d)
        self.assertEqual(m.provides, ("capture", "protocol", "routes"))

    def test_service_is_a_known_provides_value(self) -> None:
        # Backend-only, like bare "listener"/"capture" -- a lifespan-managed
        # async service is registered from register() via reg.add_service();
        # no dedicated TOML table and no frontend script required.
        toml = _VALID.replace(
            'provides = ["listener", "routes"]',
            'provides = ["service", "routes"]',
        )
        d = _write_plugin(self.root, "acars", toml)
        m = parse_manifest(d)
        self.assertEqual(m.provides, ("service", "routes"))

    def test_topbar_is_a_known_provides_value(self) -> None:
        # No dedicated TOML table (a chip is fully custom-rendered, no
        # route/label/icon to declare) -- but like panel/sidebar/hook, it
        # still needs at least one frontend script, since the chip is
        # registered from JS (window.registerTopbarChip()), not Python.
        toml = _VALID.replace(
            'provides = ["listener", "routes"]',
            'provides = ["topbar", "routes"]',
        ) + '\n[frontend]\nscripts = ["frontend/x.js"]\n'
        d = _write_plugin(self.root, "acars", toml, extra_files=("frontend/x.js",))
        m = parse_manifest(d)
        self.assertEqual(m.provides, ("topbar", "routes"))

    def test_topbar_without_frontend_scripts_is_rejected(self) -> None:
        toml = _VALID.replace(
            'provides = ["listener", "routes"]', 'provides = ["topbar"]',
        )
        self.assertEqual(self._code("acars", toml), "frontend")

    def test_frontend_table_parsed(self) -> None:
        toml = _VALID.replace(
            'provides = ["listener", "routes"]',
            'provides = ["routes", "panel"]',
        ) + """
[frontend]
scripts = ["frontend/panel.js", "/frontend/extra.js"]
styles = ["frontend/panel.css"]
"""
        d = _write_plugin(self.root, "acars", toml, extra_files=(
            "frontend/panel.js", "frontend/extra.js", "frontend/panel.css",
        ))
        m = parse_manifest(d)
        self.assertEqual(
            m.frontend_scripts, ("frontend/panel.js", "frontend/extra.js"),
        )
        self.assertEqual(m.frontend_styles, ("frontend/panel.css",))

    def test_panel_without_scripts_is_rejected(self) -> None:
        toml = _VALID.replace(
            'provides = ["listener", "routes"]', 'provides = ["panel"]',
        )
        self.assertEqual(self._code("acars", toml), "frontend")

    def test_frontend_script_must_exist(self) -> None:
        toml = _VALID.replace(
            'provides = ["listener", "routes"]', 'provides = ["panel"]',
        ) + '\n[frontend]\nscripts = ["frontend/missing.js"]\n'
        self.assertEqual(self._code("acars", toml), "frontend")

    def test_frontend_path_cannot_escape(self) -> None:
        toml = _VALID.replace(
            'provides = ["listener", "routes"]', 'provides = ["panel"]',
        ) + '\n[frontend]\nscripts = ["../evil.js"]\n'
        self.assertEqual(self._code("acars", toml), "frontend")

    def test_non_panel_plugin_ignores_frontend(self) -> None:
        toml = _VALID + '\n[frontend]\nscripts = ["frontend/x.js"]\n'
        d = _write_plugin(self.root, "acars", toml,
                          extra_files=("frontend/x.js",))
        m = parse_manifest(d)
        self.assertEqual(m.frontend_scripts, ("frontend/x.js",))

    def test_apt_not_strings(self) -> None:
        toml = _VALID + '\n[deps]\napt = ["cmake", 3]\n'
        self.assertEqual(self._code("acars", toml), "deps")

    def test_setup_file_absent(self) -> None:
        toml = _VALID + '\n[deps]\nsetup = "setup.sh"\n'
        self.assertEqual(self._code("acars", toml), "deps")

    def test_check_file_absent(self) -> None:
        toml = _VALID + '\n[deps]\ncheck = "check.sh"\n'
        self.assertEqual(self._code("acars", toml), "deps")

    def test_meta_not_string(self) -> None:
        toml = _VALID + "\n[meta]\nauthor = 42\n"
        self.assertEqual(self._code("acars", toml), "meta")

    def test_locked_true(self) -> None:
        toml = _VALID + "\nlocked = true\n"
        d = _write_plugin(self.root, "acars", toml)
        m = parse_manifest(d)
        self.assertTrue(m.locked)

    def test_locked_not_bool(self) -> None:
        toml = _VALID + '\nlocked = "yes"\n'
        self.assertEqual(self._code("acars", toml), "locked")

    def _sidebar_toml(self, sidebar_table: str) -> str:
        return (
            _VALID.replace(
                'provides = ["listener", "routes"]', 'provides = ["sidebar"]',
            )
            + '\n[frontend]\nscripts = ["frontend/x.js"]\n'
            + sidebar_table
        )

    def test_valid_sidebar_table(self) -> None:
        toml = self._sidebar_toml(
            '\n[sidebar]\nroute = "hello-world"\nlabel = "Hello World"\n'
            'category = "networks"\n',
        )
        d = _write_plugin(self.root, "acars", toml, extra_files=("frontend/x.js",))
        m = parse_manifest(d)
        self.assertEqual(m.sidebar.route, "hello-world")
        self.assertEqual(m.sidebar.label, "Hello World")
        self.assertEqual(m.sidebar.category, "networks")
        self.assertEqual(m.sidebar.icon, "plug")  # default when omitted

    def test_sidebar_icon_explicit(self) -> None:
        toml = self._sidebar_toml(
            '\n[sidebar]\nroute = "x"\nlabel = "X"\ncategory = "networks"\n'
            'icon = "antenna"\n',
        )
        d = _write_plugin(self.root, "acars", toml, extra_files=("frontend/x.js",))
        m = parse_manifest(d)
        self.assertEqual(m.sidebar.icon, "antenna")

    def test_sidebar_icon_unknown_is_rejected(self) -> None:
        toml = self._sidebar_toml(
            '\n[sidebar]\nroute = "x"\nlabel = "X"\ncategory = "networks"\n'
            'icon = "unicorn"\n',
        )
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "sidebar",
        )

    def test_sidebar_provides_without_table_is_rejected(self) -> None:
        toml = (
            _VALID.replace(
                'provides = ["listener", "routes"]', 'provides = ["sidebar"]',
            )
            + '\n[frontend]\nscripts = ["frontend/x.js"]\n'
        )
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "sidebar",
        )

    def test_sidebar_table_without_provides_is_rejected(self) -> None:
        toml = _VALID + '\n[sidebar]\nroute = "x"\nlabel = "X"\ncategory = "networks"\n'
        self.assertEqual(self._code("acars", toml), "sidebar")

    def test_sidebar_needs_frontend_scripts(self) -> None:
        toml = (
            _VALID.replace(
                'provides = ["listener", "routes"]', 'provides = ["sidebar"]',
            )
            + '\n[sidebar]\nroute = "x"\nlabel = "X"\ncategory = "networks"\n'
        )
        self.assertEqual(self._code("acars", toml), "frontend")

    def test_sidebar_bad_category(self) -> None:
        toml = self._sidebar_toml(
            '\n[sidebar]\nroute = "x"\nlabel = "X"\ncategory = "nope"\n',
        )
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "sidebar",
        )

    def test_sidebar_bad_route_slug(self) -> None:
        toml = self._sidebar_toml(
            '\n[sidebar]\nroute = "Hello World"\nlabel = "X"\ncategory = "networks"\n',
        )
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "sidebar",
        )

    def test_sidebar_blank_label(self) -> None:
        toml = self._sidebar_toml(
            '\n[sidebar]\nroute = "x"\nlabel = "   "\ncategory = "networks"\n',
        )
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "sidebar",
        )

    def _hook_toml(self, hook_table: str) -> str:
        return (
            _VALID.replace(
                'provides = ["listener", "routes"]', 'provides = ["hook"]',
            )
            + '\n[frontend]\nscripts = ["frontend/x.js"]\n'
            + hook_table
        )

    def test_valid_hook_table(self) -> None:
        toml = self._hook_toml('\n[hook]\nhost = "hello-world"\n')
        d = _write_plugin(self.root, "acars", toml, extra_files=("frontend/x.js",))
        m = parse_manifest(d)
        self.assertEqual(m.hook.host, "hello-world")
        self.assertIsNone(m.sidebar)

    def test_hook_provides_without_table_is_rejected(self) -> None:
        toml = (
            _VALID.replace(
                'provides = ["listener", "routes"]', 'provides = ["hook"]',
            )
            + '\n[frontend]\nscripts = ["frontend/x.js"]\n'
        )
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "hook",
        )

    def test_hook_table_without_provides_is_rejected(self) -> None:
        toml = _VALID + '\n[hook]\nhost = "hello-world"\n'
        self.assertEqual(self._code("acars", toml), "hook")

    def test_hook_needs_frontend_scripts(self) -> None:
        toml = (
            _VALID.replace(
                'provides = ["listener", "routes"]', 'provides = ["hook"]',
            )
            + '\n[hook]\nhost = "hello-world"\n'
        )
        self.assertEqual(self._code("acars", toml), "frontend")

    def test_hook_bad_host_slug(self) -> None:
        toml = self._hook_toml('\n[hook]\nhost = "Hello World"\n')
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "hook",
        )

    def test_hook_missing_host(self) -> None:
        toml = self._hook_toml('\n[hook]\n')
        self.assertEqual(
            self._code("acars", toml, extra_files=("frontend/x.js",)), "hook",
        )


class TestDiscoverPlugins(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.builtin = root / "builtin"
        self.community = root / "community"
        self.builtin.mkdir()
        self.community.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_dirs_return_empty(self) -> None:
        self.assertEqual(discover_plugins(self.builtin / "nope"), [])
        self.assertEqual(
            discover_plugins(self.builtin / "nope", self.community / "nope"), [],
        )

    def test_returns_valid_sorted_skips_bad(self) -> None:
        _write_plugin(self.community, "zulu", _VALID.replace('"acars"', '"zulu"'))
        _write_plugin(self.community, "acars", _VALID)
        _write_plugin(self.community, "broken", 'name = "broken"\nmeshpoint_api = 99\n')
        (self.community / "not-a-plugin").mkdir()  # no plugin.toml
        (self.community / "loose.txt").write_text("x", encoding="utf-8")

        with self.assertLogs("src.plugins.manifest", level=logging.WARNING) as logs:
            found = discover_plugins(self.builtin, self.community)

        self.assertEqual([m.name for m in found], ["acars", "zulu"])
        self.assertTrue(all(m.source == "community" for m in found))
        self.assertTrue(any("broken" in line for line in logs.output))

    def test_builtins_come_first_and_win_id_collisions(self) -> None:
        _write_plugin(self.builtin, "acars", _VALID)
        _write_plugin(self.community, "acars", _VALID)  # same id -> skipped
        _write_plugin(self.community, "extra", _VALID.replace('"acars"', '"extra"'))

        with self.assertLogs("src.plugins.manifest", level=logging.WARNING):
            found = discover_plugins(self.builtin, self.community)

        self.assertEqual([(m.name, m.source) for m in found],
                         [("acars", "builtin"), ("extra", "community")])


class TestShippedPluginManifests(unittest.TestCase):
    """Every plugin folder that actually ships in this repo has a manifest
    that parses, and every ``[deps]`` script it names really exists (a
    typo'd ``check =`` key or a renamed script would be caught here rather
    than only at boot on the device)."""

    def setUp(self) -> None:
        self._community = Path(__file__).resolve().parents[1] / "plugins" / "apps"
        self._builtin = Path(__file__).resolve().parents[1] / "src" / "plugins" / "apps"

    def _dirs(self):
        for base in (self._builtin, self._community):
            if base.is_dir():
                for d in sorted(base.iterdir()):
                    if (d / "plugin.toml").is_file():
                        yield d

    def test_every_shipped_manifest_parses(self) -> None:
        found = list(self._dirs())
        # Optional apps are downloaded through the catalog, not bundled.
        for d in found:
            with self.subTest(plugin=d.name):
                m = parse_manifest(d)
                if m.setup is not None:
                    self.assertTrue(m.setup_path.is_file())
                if m.check is not None:
                    self.assertTrue(m.check_path.is_file())
                    self.assertGreater(m.check_path.stat().st_size, 0)

    def test_every_plugin_with_setup_also_ships_a_check(self) -> None:
        # Not enforced by the parser -- but the whole point of the deps
        # check is that Settings -> Plugins can tell the truth for every
        # plugin that needs a setup step, so a new setup.sh without a
        # check.sh should be a deliberate, noticed choice.
        for d in self._dirs():
            m = parse_manifest(d)
            if m.setup is not None:
                with self.subTest(plugin=d.name):
                    self.assertIsNotNone(
                        m.check,
                        f"{d.name} declares [deps] setup but no [deps] check",
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
