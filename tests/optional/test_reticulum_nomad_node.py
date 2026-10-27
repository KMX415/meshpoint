"""Tests for the NomadNet-node host that don't need a real RNS stack.

Without ``rns`` installed (the dev Mac), ``nomad_node.RNS`` is ``None`` and
``start()`` is a no-op -- construction, ``status()`` and the Micron
generators are what's covered here.
"""

from __future__ import annotations

import asyncio
import unittest

from apps.reticulum.backend import nomad_node as nomad_node_module
from apps.reticulum.backend.nomad_node import NomadNode, _esc


class TestMicronEscape(unittest.TestCase):
    def test_escapes_backtick_and_backslash(self) -> None:
        self.assertEqual(_esc("a`b\\c"), "a\\`b\\\\c")

    def test_plain_text_untouched(self) -> None:
        self.assertEqual(_esc("Rhein-Main RNS"), "Rhein-Main RNS")


class TestNomadNode(unittest.TestCase):
    def _node(self, **kw):
        kw.setdefault("hardware_description", "a SenseCap M1")
        return NomadNode(
            identity=object(), name="PD2EMC Meshpoint",
            pages_dir="/tmp/does-not-exist/pages", announce_interval_s=21600, **kw,
        )

    def test_announce_interval_floored(self) -> None:
        n = NomadNode(identity=object(), name="x", pages_dir="/tmp/x", announce_interval_s=1)
        self.assertGreaterEqual(n._announce_interval_s, 600)

    @unittest.skipIf(
        nomad_node_module.RNS is not None,
        "rns installed -- this covers only the not-available path",
    )
    def test_start_is_a_no_op_without_rns(self) -> None:
        n = self._node()
        asyncio.run(n.start())  # must not raise
        self.assertIsNone(n._destination)
        asyncio.run(n.stop())

    def test_status_shape(self) -> None:
        st = self._node().status()
        self.assertEqual(st["hosting"], False)
        self.assertEqual(st["name"], "PD2EMC Meshpoint")
        self.assertIn("requests_served", st)

    def test_reload_pages_is_a_no_op_when_not_hosting(self) -> None:
        n = self._node()
        self.assertIsNone(n._destination)
        n.reload_pages()  # must not raise (Pages tab calls this after every save)
        self.assertIsNone(n._destination)

    def test_serve_index_returns_branding_page(self) -> None:
        n = self._node()
        out = n._serve_index("/page/index.mu", None, 1, 1, None, 0)
        self.assertIsInstance(out, bytes)
        text = out.decode("utf-8")
        self.assertIn("PD2EMC Meshpoint", text)
        self.assertIn("SenseCap", text)
        self.assertIn("nomadnetwork.node", text)
        self.assertIn(":/page/info.mu", text)
        self.assertEqual(n._requests_served, 1)
        self.assertIn("`F888Node`f", text)          # labelled name row
        self.assertNotIn("a Meshpoint node", text)   # subtitle dropped
        # the figlet MESHPOINT banner, left-aligned (never `c'd) and raw
        for row in nomad_node_module._MESHPOINT_BANNER:
            self.assertIn(row, text)
        self.assertNotIn("`c" + nomad_node_module._MESHPOINT_BANNER[0], text)

    def test_serve_index_shows_the_node_address_once_hosting(self) -> None:
        n = self._node()
        self.assertNotIn("`F888Address`f", n._serve_index("/page/index.mu", None, 1, 1, None, 0).decode())

        class _Dest:
            hash = bytes.fromhex("00112233445566778899aabbccddeeff")
        n._destination = _Dest()
        text = n._serve_index("/page/index.mu", None, 1, 1, None, 0).decode()
        self.assertIn("`F888Address`f : 00112233445566778899aabbccddeeff", text)

    def test_serve_index_without_hardware_description(self) -> None:
        n = self._node(hardware_description="")
        text = n._serve_index("/page/index.mu", None, 1, 1, None, 0).decode("utf-8")
        self.assertIn("runs `!Meshpoint`!. Its optional Reticulum", text)

    def test_serve_info_returns_micron_bytes(self) -> None:
        n = self._node()
        n._stats = {"version": "0.8.1", "uptime": "3h 12m", "reticulum_peers": 11270}
        out = n._serve_info("/page/info.mu", None, 1, 1, None, 0)
        self.assertIsInstance(out, bytes)
        text = out.decode("utf-8")
        self.assertIn("PD2EMC Meshpoint", text)
        self.assertIn("11270", text)
        self.assertIn(":/page/index.mu", text)
        self.assertEqual(n._requests_served, 1)
        # No host/mesh keys -> those sections are simply absent.
        self.assertNotIn(">Host", text)
        self.assertNotIn(">Mesh activity", text)

    def test_serve_info_host_and_mesh_sections(self) -> None:
        n = self._node()
        n._stats = {
            "version": "0.8.1",
            "host": {
                "pi_model": "Raspberry Pi 4 Model B", "cpu_temp_c": 47.2,
                "load_1m": 0.31, "mem_used_mb": 900, "mem_total_mb": 3800,
                "disk_free_gb": 21.4, "disk_total_gb": 29.0,
            },
            "mesh": {
                "packets_total": 1234567, "packets_24h": 8912,
                "by_protocol": {"meshtastic": 900000, "meshcore": 300000, "lorawan": 34567},
            },
        }
        text = n._serve_info("/page/info.mu", None, 1, 1, None, 0).decode("utf-8")
        self.assertIn(">Host", text)
        self.assertIn("Raspberry Pi 4 Model B", text)
        self.assertIn("47.2 C", text)
        self.assertIn("900 / 3800 MB", text)
        self.assertIn(">Mesh activity", text)
        self.assertIn("1,234,567", text)     # thousands-separated
        self.assertIn("meshtastic", text)
        # per-protocol is ordered by count desc
        self.assertLess(text.index("meshtastic"), text.index("lorawan"))
        # deliberately nothing node-level
        self.assertNotIn("source_id", text)

    def test_serve_info_and_index_use_the_project_url(self) -> None:
        n = self._node(project_url="https://github.com/someforker/meshpoint")
        for handler in (n._serve_index, n._serve_info):
            text = handler("/page/x.mu", None, 1, 1, None, 0).decode("utf-8")
            self.assertIn("https://github.com/someforker/meshpoint", text)
            self.assertIn("github.com/someforker/meshpoint]", text)  # link label

    def test_project_url_defaults_to_kmx415(self) -> None:
        text = self._node()._serve_info("/page/info.mu", None, 1, 1, None, 0).decode("utf-8")
        self.assertIn("https://github.com/KMX415/meshpoint", text)

    def test_serve_spacestate_renders_from_cache(self) -> None:
        n = self._node(spaceapi_url="https://x/spaceapi.json")
        n._spaceapi = {
            "space": "Technologia Incognita", "open": False,
            "lastchange": 1, "address": "Louwesweg 1",
            "url": "https://www.techinc.nl", "irc": "#techinc @ OFTC",
        }
        text = n._serve_spacestate("/page/spacestate.mu", None, 1, 1, None, 0).decode()
        self.assertIn("Technologia Incognita", text)
        self.assertIn("CLOSED", text)
        self.assertIn("Louwesweg 1", text)
        self.assertIn("`[https://www.techinc.nl`https://www.techinc.nl]", text)

    def test_serve_spacestate_before_first_fetch(self) -> None:
        n = self._node(spaceapi_url="https://x")
        text = n._serve_spacestate("/page/spacestate.mu", None, 1, 1, None, 0).decode()
        self.assertIn("unknown", text)
        self.assertIn("not fetched yet", text)

    def test_spacestate_token_substituted_in_operator_pages(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "about.mu"
            page.write_text("TechInc is {spacestate} right now\n")
            n = self._node(spaceapi_url="https://x")
            n._spaceapi = {"open": True}
            n._pages_dir = Path(d)
            body = n._make_file_server(page)("/page/about.mu", None, 1, 1, None, 0)
            self.assertIn("`F0a0`!OPEN`!`f", body.decode())
            self.assertNotIn("{spacestate}", body.decode())

    def test_spacestate_lazy_refresh_scheduled_when_stale(self) -> None:
        import time as _t

        n = self._node(spaceapi_url="https://x")
        n._spaceapi = {"open": True}                  # have a value...
        n._spaceapi_fetched_at = _t.monotonic() - 10_000  # ...but it's stale

        scheduled: list = []

        class _FakeLoop:
            def call_soon_threadsafe(self, fn, *a):
                scheduled.append(fn)

            def create_task(self, coro):
                coro.close()

        n._loop = _FakeLoop()
        n._serve_spacestate("/page/spacestate.mu", None, 1, 1, None, 0)
        self.assertEqual(len(scheduled), 1)          # a refresh was kicked
        self.assertTrue(n._spaceapi_refreshing)      # and de-duped until it lands

        scheduled.clear()
        n._serve_spacestate("/page/spacestate.mu", None, 1, 1, None, 0)
        self.assertEqual(scheduled, [])              # second hit doesn't stack

    def test_spacestate_no_refresh_when_cache_fresh(self) -> None:
        import time as _t

        n = self._node(spaceapi_url="https://x")
        n._spaceapi = {"open": True}
        n._spaceapi_fetched_at = _t.monotonic()      # just fetched

        class _BoomLoop:
            def call_soon_threadsafe(self, *a):
                raise AssertionError("should not schedule a refresh")

        n._loop = _BoomLoop()
        n._serve_spacestate("/page/spacestate.mu", None, 1, 1, None, 0)

    def test_spacestate_token_left_alone_when_no_url(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "about.mu"
            page.write_text("status: {spacestate}\n")
            n = self._node()  # no spaceapi_url
            n._pages_dir = Path(d)
            body = n._make_file_server(page)("/page/about.mu", None, 1, 1, None, 0)
            self.assertIn("{spacestate}", body.decode())

    def test_serve_events_renders_from_cache(self) -> None:
        import datetime as _dt

        n = self._node(events_ical_url="https://x/cal.ics")
        n._events_fetched_at = 1.0  # pretend we fetched
        n._events = [
            {"summary": "Social 2026-09-09", "all_day": False,
             "start": _dt.datetime(2026, 9, 9, 19, 0), "end": None,
             "url": "https://wiki.techinc.nl/Social_2026-09-09"},
            {"summary": "ALV", "all_day": True,
             "start": _dt.date(2026, 9, 20), "end": None, "url": ""},
        ]
        text = n._serve_events("/page/events.mu", None, 1, 1, None, 0).decode()
        self.assertIn("Upcoming events", text)
        self.assertIn("Wed 9 Sep  19:00", text)
        self.assertIn("`[Social 2026-09-09`https://wiki.techinc.nl/Social_2026-09-09]", text)
        self.assertIn("Sun 20 Sep", text)
        self.assertNotIn("nothing scheduled", text)

    def test_serve_events_before_first_fetch(self) -> None:
        n = self._node(events_ical_url="https://x")
        text = n._serve_events("/page/events.mu", None, 1, 1, None, 0).decode()
        self.assertIn("not fetched yet", text)

    def test_serve_events_empty_after_fetch(self) -> None:
        n = self._node(events_ical_url="https://x")
        n._events_fetched_at = 1.0
        n._events = []
        text = n._serve_events("/page/events.mu", None, 1, 1, None, 0).decode()
        self.assertIn("nothing scheduled", text)

    def test_events_page_counted_and_gated(self) -> None:
        self.assertEqual(self._node()._page_count(), 3)
        self.assertEqual(self._node(events_ical_url="https://x")._page_count(), 4)
        both = self._node(events_ical_url="https://x", spaceapi_url="https://y")
        self.assertEqual(both._page_count(), 5)

    def test_events_lazy_refresh_scheduled_when_stale(self) -> None:
        n = self._node(events_ical_url="https://x")
        n._events_fetched_at = 0.0  # never fetched -> stale

        scheduled: list = []

        class _FakeLoop:
            def call_soon_threadsafe(self, fn, *a):
                scheduled.append(fn)

            def create_task(self, coro):
                coro.close()

        n._loop = _FakeLoop()
        n._serve_events("/page/events.mu", None, 1, 1, None, 0)
        self.assertEqual(len(scheduled), 1)
        self.assertTrue(n._events_refreshing)

    def test_serve_nodes_lists_recent(self) -> None:
        n = self._node()
        n._stats = {"recent_nodes": [
            {"display_name": "libstalin.so", "destination_hash": "abcd"},
        ]}
        text = n._serve_nodes("/page/nodes.mu", None, 1, 1, None, 0).decode("utf-8")
        self.assertIn("libstalin.so", text)
        self.assertIn("abcd:/page/index.mu", text)

    def test_announce_is_a_no_op_before_start(self) -> None:
        n = self._node()
        n.announce()  # _destination is None -> must not raise
        self.assertIsNone(n._last_announce)

    def test_serve_nodes_empty(self) -> None:
        n = self._node()
        text = n._serve_nodes("/page/nodes.mu", None, 1, 1, None, 0).decode("utf-8")
        self.assertIn("none yet", text)

    def test_events_and_spacestate_cross_link_only_when_both_configured(self) -> None:
        n = self._node(spaceapi_url="https://x", events_ical_url="https://y")
        events_text = n._serve_events("/page/events.mu", None, 1, 1, None, 0).decode()
        self.assertIn(":/page/spacestate.mu", events_text)
        space_text = n._serve_spacestate("/page/spacestate.mu", None, 1, 1, None, 0).decode()
        self.assertIn(":/page/events.mu", space_text)

    def test_events_has_no_spacestate_link_when_not_configured(self) -> None:
        n = self._node(events_ical_url="https://y")  # no spaceapi_url
        text = n._serve_events("/page/events.mu", None, 1, 1, None, 0).decode()
        self.assertNotIn("spacestate.mu", text)

    def test_serve_nodes_links_back_to_info(self) -> None:
        n = self._node()
        text = n._serve_nodes("/page/nodes.mu", None, 1, 1, None, 0).decode()
        self.assertIn(":/page/info.mu", text)
        self.assertIn(":/page/index.mu", text)


class TestNomadNodeTalkbackSnapshots(unittest.TestCase):
    """Public plain-text accessors added for backend/talkback.py -- a
    second, non-Micron consumer of the same cached data the .mu pages
    already read."""

    def _node(self, **kw):
        kw.setdefault("hardware_description", "a SenseCap M1")
        return NomadNode(
            identity=object(), name="PD2EMC Meshpoint",
            pages_dir="/tmp/does-not-exist/pages", announce_interval_s=21600, **kw,
        )

    def test_name_property(self) -> None:
        self.assertEqual(self._node().name, "PD2EMC Meshpoint")

    def test_configured_flags_reflect_urls(self) -> None:
        n = self._node()
        self.assertFalse(n.spaceapi_configured)
        self.assertFalse(n.events_configured)
        n2 = self._node(spaceapi_url="https://x", events_ical_url="https://y")
        self.assertTrue(n2.spaceapi_configured)
        self.assertTrue(n2.events_configured)

    def test_stats_snapshot_is_a_plain_copy(self) -> None:
        n = self._node()
        n._stats = {"version": "0.8.1"}
        snap = n.stats_snapshot()
        self.assertEqual(snap, {"version": "0.8.1"})
        snap["version"] = "mutated"
        self.assertEqual(n._stats["version"], "0.8.1")  # copy, not a live ref

    def test_spaceapi_snapshot_triggers_lazy_refresh_when_stale(self) -> None:
        import time as _t

        n = self._node(spaceapi_url="https://x")
        n._spaceapi = {"open": True}
        n._spaceapi_fetched_at = _t.monotonic() - 10_000

        scheduled: list = []

        class _FakeLoop:
            def call_soon_threadsafe(self, fn, *a):
                scheduled.append(fn)

            def create_task(self, coro):
                coro.close()

        n._loop = _FakeLoop()
        snap = n.spaceapi_snapshot()
        self.assertEqual(snap, {"open": True})
        self.assertEqual(len(scheduled), 1)  # same lazy-refresh path as the .mu page

    def test_events_snapshot_returns_a_plain_list(self) -> None:
        n = self._node(events_ical_url="https://y")
        n._events = [{"summary": "Talk"}]
        self.assertEqual(n.events_snapshot(), [{"summary": "Talk"}])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
