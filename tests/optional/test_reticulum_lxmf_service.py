"""Tests for LxmfService that don't need a real RNS/LXMF stack.

On a machine without ``rns``/``lxmf`` installed (this project's dev Mac),
``RNS``/``LXMF`` are ``None`` and ``.available`` is ``False``. That path --
construction, the not-available guard in ``start()``, ``own_address``
before start -- is what's covered here. The real attach/announce/send
round trip is integration-level (needs rnsd) and lives on the Pi.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from apps.reticulum.backend import lxmf_service
from apps.reticulum.backend.lxmf_service import LxmfService, _route_rns_log


def _make_service(**kw) -> LxmfService:
    return LxmfService(
        display_name="Meshpoint",
        reticulum_config_dir="/tmp/does-not-matter/rns_config",
        identity_path="/tmp/does-not-matter/identity",
        lxmf_storage_dir="/tmp/does-not-matter/lxmf",
        message_repo=kw.pop("message_repo", object()),
        peer_repo=kw.pop("peer_repo", object()),
        ws_manager=kw.pop("ws_manager", object()),
        **kw,
    )


class _FakePeerRepo:
    def __init__(self):
        self.recorded = []

    async def record_announce(self, dh, name, aspect):
        self.recorded.append((dh, name, aspect))

    async def list_peers(self, *a, **kw):
        return []


class _FakeWs:
    def __init__(self):
        self.events = []

    async def broadcast(self, event_type, data):
        self.events.append((event_type, data))


class _FakeMessageRepo:
    def __init__(self):
        self._next_id = 1

    async def save_received(self, *, text, node_id, node_name, protocol, packet_id):
        row_id = self._next_id
        self._next_id += 1
        return row_id, False


@unittest.skipIf(
    lxmf_service.RNS is not None,
    "rns/lxmf installed -- this covers only the not-available path",
)
class TestLxmfServiceWithoutRns(unittest.TestCase):
    def test_available_is_false_without_rns(self) -> None:
        self.assertFalse(_make_service().available)

    def test_own_address_is_none_before_start(self) -> None:
        self.assertIsNone(_make_service().own_address)

    def test_start_is_a_no_op_when_not_available(self) -> None:
        svc = _make_service()
        asyncio.run(svc.start())  # logs a warning, returns -- must not raise
        self.assertIsNone(svc.own_address)

    def test_announce_before_start_raises_runtimeerror(self) -> None:
        with self.assertRaises(RuntimeError):
            _make_service().announce()

    def test_send_message_raises_runtimeerror_when_not_running(self) -> None:
        with self.assertRaises(RuntimeError):
            asyncio.run(_make_service().send_message("abcd", "hi"))


class TestRnsLogBridge(unittest.TestCase):
    """_route_rns_log parses RNS's "[ts] [Level] msg" format, maps the
    level into Python logging, and demotes one known-noisy LXMF line."""

    def test_real_error_stays_at_error(self):
        with self.assertLogs("RNS", level="DEBUG") as cm:
            _route_rns_log("[2026-09-06 14:15:44] [Error] Something actually broke")
        self.assertEqual(len(cm.records), 1)
        self.assertEqual(cm.records[0].levelname, "ERROR")
        self.assertEqual(cm.records[0].getMessage(), "Something actually broke")

    def test_noisy_announce_line_is_demoted_to_debug(self):
        with self.assertLogs("RNS", level="DEBUG") as cm:
            _route_rns_log(
                "[2026-09-06 14:15:44] [Error] Could not decode display name in "
                "included announce data. The contained exception was: "
                "'bool' object has no attribute 'decode'"
            )
        self.assertEqual(cm.records[0].levelname, "DEBUG")

    def test_notice_maps_to_info(self):
        with self.assertLogs("RNS", level="DEBUG") as cm:
            _route_rns_log("[2026-09-06 14:15:44] [Notice] Reticulum Transport enabled")
        self.assertEqual(cm.records[0].levelname, "INFO")

    def test_unparseable_line_falls_back_to_info(self):
        with self.assertLogs("RNS", level="DEBUG") as cm:
            _route_rns_log("a bare line with no prefix")
        self.assertEqual(cm.records[0].levelname, "INFO")
        self.assertEqual(cm.records[0].getMessage(), "a bare line with no prefix")


class TestAnnounceLog(unittest.TestCase):
    """_handle_announce feeds both the roster (roster aspects only) and the
    in-memory Activity ring buffer (every aspect), newest-first."""

    def _svc(self):
        return _make_service(peer_repo=_FakePeerRepo(), ws_manager=_FakeWs())

    def test_starts_empty(self) -> None:
        self.assertEqual(_make_service().announce_log(), [])

    def test_roster_aspect_records_and_broadcasts_both(self) -> None:
        svc = self._svc()
        asyncio.run(svc._handle_announce("aa" * 16, "Bob", "lxmf.delivery"))
        self.assertEqual(len(svc._peer_repo.recorded), 1)
        kinds = [e[0] for e in svc._ws_manager.events]
        self.assertIn("reticulum_announce", kinds)
        self.assertIn("reticulum_peer", kinds)
        log = svc.announce_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["display_name"], "Bob")
        self.assertTrue(log[0]["ts"])

    def test_call_audio_is_stream_only(self) -> None:
        svc = self._svc()
        asyncio.run(svc._handle_announce("bb" * 16, "", "call.audio"))
        self.assertEqual(svc._peer_repo.recorded, [])          # not in the roster
        kinds = [e[0] for e in svc._ws_manager.events]
        self.assertEqual(kinds, ["reticulum_announce"])         # stream only
        self.assertEqual(len(svc.announce_log()), 1)

    def test_newest_first_and_capped(self) -> None:
        svc = self._svc()
        for i in range(lxmf_service._ANNOUNCE_LOG_MAX + 25):
            asyncio.run(svc._handle_announce(f"{i:032x}", str(i), "lxmf.delivery"))
        log = svc.announce_log()
        self.assertEqual(len(log), lxmf_service._ANNOUNCE_LOG_MAX)
        self.assertEqual(log[0]["display_name"], str(lxmf_service._ANNOUNCE_LOG_MAX + 24))


class TestAnnounceSignalCapture(unittest.TestCase):
    """_on_announce resolves RSSI/SNR/quality for the announce packet
    hash RNS hands it (see peer_link_info's docstring for why this only
    ever comes from an interface that reports signal, e.g. RNode/LoRa,
    never a TCP backbone peer)."""

    def _svc(self):
        return _make_service(peer_repo=_FakePeerRepo(), ws_manager=_FakeWs())

    def test_captures_signal_when_reticulum_instance_available(self) -> None:
        svc = self._svc()
        svc._reticulum = mock.Mock()
        svc._reticulum.get_packet_rssi.return_value = -72.0
        svc._reticulum.get_packet_snr.return_value = 8.5
        svc._reticulum.get_packet_q.return_value = 91
        dest_bytes = b"\xaa" * 16
        packet_hash = b"\x01\x02\x03\x04"

        async def runner():
            svc._loop = asyncio.get_running_loop()
            with mock.patch.object(lxmf_service, "RNS") as mock_rns:
                mock_rns.hexrep.side_effect = lambda b, delimit=None: b.hex()
                svc._on_announce("lxmf.delivery", dest_bytes, None, packet_hash)
            await asyncio.sleep(0)
        asyncio.run(runner())

        log = svc.announce_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["rssi"], -72.0)
        self.assertEqual(log[0]["snr"], 8.5)
        self.assertEqual(log[0]["quality"], 91)
        self.assertEqual(log[0]["packet_hash"], packet_hash.hex())
        svc._reticulum.get_packet_rssi.assert_called_once_with(packet_hash)

    def test_no_signal_fields_without_a_packet_hash(self) -> None:
        # A TCP-backbone-only setup, or an announce RNS didn't attach a
        # hash to -- must not crash, just report no signal.
        svc = self._svc()
        svc._reticulum = mock.Mock()

        async def runner():
            svc._loop = asyncio.get_running_loop()
            with mock.patch.object(lxmf_service, "RNS") as mock_rns:
                mock_rns.hexrep.side_effect = lambda b, delimit=None: b.hex()
                svc._on_announce("lxmf.delivery", b"\xbb" * 16, None, None)
            await asyncio.sleep(0)
        asyncio.run(runner())

        log = svc.announce_log()
        self.assertIsNone(log[0]["rssi"])
        self.assertIsNone(log[0]["packet_hash"])
        svc._reticulum.get_packet_rssi.assert_not_called()

    def test_signal_lookup_failure_is_swallowed(self) -> None:
        svc = self._svc()
        svc._reticulum = mock.Mock()
        svc._reticulum.get_packet_rssi.side_effect = RuntimeError("rpc down")

        async def runner():
            svc._loop = asyncio.get_running_loop()
            with mock.patch.object(lxmf_service, "RNS") as mock_rns:
                mock_rns.hexrep.side_effect = lambda b, delimit=None: b.hex()
                svc._on_announce("lxmf.delivery", b"\xcc" * 16, None, b"\x01")
            await asyncio.sleep(0)
        asyncio.run(runner())  # must not raise

        log = svc.announce_log()
        self.assertIsNone(log[0]["rssi"])


class TestPeerLinkInfo(unittest.TestCase):
    """peer_link_info() is tested directly with RNS mocked at module
    level (real RNS.Transport is a static-method API on the actual
    Transport class, unlike LXMF's own instance-based router)."""

    def _svc(self):
        return _make_service(peer_repo=_FakePeerRepo(), ws_manager=_FakeWs())

    def test_no_rns_returns_all_empty(self) -> None:
        svc = self._svc()
        with mock.patch.object(lxmf_service, "RNS", None):
            info = svc.peer_link_info("aa" * 16)
        self.assertEqual(info["hops"], None)
        self.assertFalse(info["has_path"])
        self.assertFalse(info["identity_resolved"])
        self.assertEqual(info["announces_this_session"], 0)

    def test_invalid_hex_returns_empty_without_raising(self) -> None:
        svc = self._svc()
        info = svc.peer_link_info("not-hex")
        self.assertFalse(info["has_path"])

    def test_reports_hops_and_path_and_identity(self) -> None:
        svc = self._svc()
        dest_hex = "aa" * 16
        with mock.patch.object(lxmf_service, "RNS") as mock_rns:
            mock_rns.Transport.has_path.return_value = True
            mock_rns.Transport.hops_to.return_value = 3
            mock_rns.Transport.PATHFINDER_M = 128
            mock_rns.Identity.recall.return_value = object()  # "known" identity
            svc._reticulum = mock.Mock()
            svc._reticulum.get_next_hop_if_name.return_value = "RNodeInterface"
            info = svc.peer_link_info(dest_hex)
        self.assertEqual(info["hops"], 3)
        self.assertTrue(info["has_path"])
        self.assertEqual(info["next_hop_interface"], "RNodeInterface")
        self.assertTrue(info["identity_resolved"])

    def test_unknown_hops_reported_as_none(self) -> None:
        svc = self._svc()
        with mock.patch.object(lxmf_service, "RNS") as mock_rns:
            mock_rns.Transport.has_path.return_value = False
            mock_rns.Transport.hops_to.return_value = 128
            mock_rns.Transport.PATHFINDER_M = 128
            mock_rns.Identity.recall.return_value = None
            info = svc.peer_link_info("bb" * 16)
        self.assertIsNone(info["hops"])
        self.assertFalse(info["has_path"])
        self.assertFalse(info["identity_resolved"])

    def test_counts_announces_and_returns_most_recent_signal(self) -> None:
        svc = self._svc()
        dest_hex = "cc" * 16
        asyncio.run(svc._handle_announce(dest_hex, "Bob", "lxmf.delivery", None, "old-hash", -100.0, 2.0, 30))
        asyncio.run(svc._handle_announce(dest_hex, "Bob", "lxmf.delivery", None, "new-hash", -60.0, 9.0, 95))
        with mock.patch.object(lxmf_service, "RNS") as mock_rns:
            mock_rns.Transport.has_path.return_value = False
            mock_rns.Transport.hops_to.return_value = 128
            mock_rns.Transport.PATHFINDER_M = 128
            mock_rns.Identity.recall.return_value = None
            info = svc.peer_link_info(dest_hex)
        self.assertEqual(info["announces_this_session"], 2)
        self.assertEqual(info["rssi"], -60.0)  # the most recent one, not the first

    def test_most_recent_with_no_signal_is_not_shadowed_by_an_older_signal(self) -> None:
        # Regression guard: the "most recent match" tracking must not use
        # "signal_at is None" as its own found-latest flag, since the most
        # recent announce can legitimately have no signal (heard over TCP)
        # while an older one from the same peer did have signal (RNode).
        svc = self._svc()
        dest_hex = "dd" * 16
        asyncio.run(svc._handle_announce(dest_hex, "Bob", "lxmf.delivery", None, "rnode-hash", -60.0, 9.0, 95))
        asyncio.run(svc._handle_announce(dest_hex, "Bob", "lxmf.delivery"))  # newer, no signal (e.g. TCP)
        with mock.patch.object(lxmf_service, "RNS") as mock_rns:
            mock_rns.Transport.has_path.return_value = False
            mock_rns.Transport.hops_to.return_value = 128
            mock_rns.Transport.PATHFINDER_M = 128
            mock_rns.Identity.recall.return_value = None
            info = svc.peer_link_info(dest_hex)
        self.assertIsNone(info["rssi"])  # the newest entry's (lack of) signal wins
        self.assertEqual(info["announces_this_session"], 2)


class _FakeRouter:
    def __init__(self):
        self.calls = []
        self.propagation_entries = {"a": 1, "b": 2}

        class _Dest:
            hash = b"\x01" * 16

        self.propagation_destination = _Dest()

        self.outbound_propagation_node = None
        self.propagation_transfer_state = None
        self.propagation_transfer_progress = 0.0
        self.propagation_transfer_last_result = None

    def set_message_storage_limit(self, **kw):
        self.calls.append(("limit", kw))

    def enable_propagation(self):
        self.calls.append(("enable",))

    def announce_propagation_node(self):
        self.calls.append(("announce",))

    def set_outbound_propagation_node(self, dest_bytes):
        self.calls.append(("set_outbound", dest_bytes))
        self.outbound_propagation_node = dest_bytes

    def get_outbound_propagation_node(self):
        return self.outbound_propagation_node

    def cancel_propagation_node_requests(self):
        self.calls.append(("cancel",))

    def request_messages_from_propagation_node(self, identity):
        self.calls.append(("sync", identity))


class TestPropagationNode(unittest.TestCase):
    def test_start_enables_caps_store_and_announces(self) -> None:
        svc = _make_service(propagation_cfg={"enabled": True, "storage_limit_mb": 500})
        svc._router = _FakeRouter()
        svc._loop = None  # skip the periodic re-announce task
        svc._start_propagation()
        self.assertEqual([c[0] for c in svc._router.calls], ["limit", "enable", "announce"])
        self.assertEqual(svc._router.calls[0][1], {"megabytes": 500})

    def test_start_skips_limit_when_zero(self) -> None:
        svc = _make_service(propagation_cfg={"enabled": True, "storage_limit_mb": 0})
        svc._router = _FakeRouter()
        svc._loop = None
        svc._start_propagation()
        self.assertEqual([c[0] for c in svc._router.calls], ["enable", "announce"])

    def test_status_none_when_disabled(self) -> None:
        svc = _make_service()
        svc._router = _FakeRouter()
        self.assertIsNone(svc.propagation_status())

    def test_status_reports_held_count_and_limit(self) -> None:
        svc = _make_service(propagation_cfg={"enabled": True, "storage_limit_mb": 250})
        svc._router = _FakeRouter()
        st = svc.propagation_status()
        self.assertTrue(st["enabled"])
        self.assertEqual(st["messages_held"], 2)
        self.assertEqual(st["storage_limit_mb"], 250)

    def test_enable_failure_is_swallowed(self) -> None:
        svc = _make_service(propagation_cfg={"enabled": True})

        class _Boom:
            def enable_propagation(self):
                raise RuntimeError("nope")

        svc._router = _Boom()
        svc._loop = None
        svc._start_propagation()  # must not raise
        self.assertIsNone(svc._pn_task)


class TestPropagationClient(unittest.TestCase):
    def test_set_outbound_node_normalises_and_calls_router(self) -> None:
        svc = _make_service()
        svc._router = _FakeRouter()
        ok = svc.set_outbound_propagation_node("AB:CD" + "ef" * 14)
        self.assertTrue(ok)
        self.assertEqual(svc._prop_outbound, "abcd" + "ef" * 14)
        self.assertEqual(svc._router.calls[-1][0], "set_outbound")

    def test_clearing_outbound_node_cancels_and_nulls(self) -> None:
        svc = _make_service()
        svc._router = _FakeRouter()
        svc.set_outbound_propagation_node("ab" * 16)
        self.assertFalse(svc.set_outbound_propagation_node(""))
        self.assertEqual(svc._prop_outbound, "")
        self.assertIn(("cancel",), svc._router.calls)
        self.assertIsNone(svc._router.outbound_propagation_node)

    def test_bad_hash_is_swallowed_and_clears(self) -> None:
        svc = _make_service()
        svc._router = _FakeRouter()
        self.assertFalse(svc.set_outbound_propagation_node("nothex!!"))
        self.assertEqual(svc._prop_outbound, "")

    def test_sync_needs_an_outbound_node(self) -> None:
        svc = _make_service()
        svc._router = _FakeRouter()
        svc._identity = object()
        res = svc.sync_propagation_messages()
        self.assertFalse(res["ok"])
        self.assertIn("outbound propagation node", res["error"])

    def test_sync_dispatches_the_request(self) -> None:
        svc = _make_service()
        svc._router = _FakeRouter()
        svc._identity = object()
        svc.set_outbound_propagation_node("cd" * 16)
        res = svc.sync_propagation_messages()
        self.assertTrue(res["ok"])
        self.assertEqual(svc._router.calls[-1][0], "sync")

    def test_client_status_shape(self) -> None:
        svc = _make_service(propagation_cfg={"outbound_node": "ab" * 16, "auto_sync_interval_s": 600})
        svc._router = _FakeRouter()
        svc._router.propagation_transfer_last_result = 3
        st = svc.propagation_client_status()
        self.assertEqual(st["outbound_node"], "ab" * 16)
        self.assertEqual(st["auto_sync_interval_s"], 600)
        self.assertEqual(st["last_result"], 3)
        self.assertEqual(st["state"], "idle")  # None -> idle

    def test_client_status_none_without_router(self) -> None:
        svc = _make_service(propagation_cfg={"outbound_node": "ab" * 16})
        self.assertIsNone(svc.propagation_client_status())

    def test_watch_propagation_sync_broadcasts_the_result(self) -> None:
        svc = _make_service(ws_manager=_FakeWs())
        svc._router = _FakeRouter()
        svc._router.propagation_transfer_last_result = 4
        # state None -> "idle" (terminal) -> broadcasts on the first poll
        asyncio.run(svc._watch_propagation_sync(timeout_s=5, initial_delay_s=0))
        ev = [e for e in svc._ws_manager.events if e[0] == "reticulum_propagation_sync"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0][1]["last_result"], 4)

    def test_watch_propagation_sync_bails_without_a_router(self) -> None:
        svc = _make_service(ws_manager=_FakeWs())
        asyncio.run(svc._watch_propagation_sync(timeout_s=5, initial_delay_s=0))
        self.assertEqual(svc._ws_manager.events, [])


class TestTelemetryPublish(unittest.TestCase):
    def test_status_none_when_disabled(self) -> None:
        self.assertIsNone(_make_service().telemetry_status())

    def test_status_shape_when_enabled(self) -> None:
        svc = _make_service(telemetry_cfg={
            "enabled": True, "collectors": ["cd" * 16, "ab" * 16], "interval_s": 600,
        })
        st = svc.telemetry_status()
        self.assertTrue(st["enabled"])
        self.assertEqual(st["collectors"], ["cd" * 16, "ab" * 16])
        self.assertEqual(st["collector_count"], 2)
        self.assertEqual(st["collector"], "cd" * 16)  # back-compat: first
        self.assertEqual(st["interval_s"], 600)
        self.assertFalse(st["location_included"])
        self.assertIsNone(st["last_sent_at"])

    def test_status_reports_location_included(self) -> None:
        svc = _make_service(telemetry_cfg={
            "enabled": True, "collectors": ["cd" * 16], "location": (1.0, 2.0, 0.0),
        })
        self.assertTrue(svc.telemetry_status()["location_included"])

    def test_send_without_collector_errors(self) -> None:
        svc = _make_service(telemetry_cfg={"enabled": True, "collectors": []})
        res = svc.send_telemetry()
        self.assertFalse(res["ok"])
        self.assertEqual(res["sent"], 0)
        self.assertIn("collector", res["error"])

    def test_send_when_not_running_errors(self) -> None:
        # RNS/LXMF absent on the dev Mac -> .available is False
        svc = _make_service(telemetry_cfg={"enabled": True, "collectors": ["cd" * 16]})
        res = svc.send_telemetry()
        self.assertFalse(res["ok"])
        self.assertIn("not running", res["error"])

    def test_record_inbound_telemetry_ignores_a_plain_message(self) -> None:
        svc = _make_service()

        class _Msg:
            fields = {}

        self.assertFalse(svc._record_inbound_telemetry(_Msg(), "abc", ""))
        self.assertFalse(svc._record_inbound_telemetry(object(), "abc", ""))

    def test_record_inbound_telemetry_stores_a_decoded_frame(self) -> None:
        svc = _make_service()

        class _Msg:
            # an already-unpacked frame dict (RNS.vendor.umsgpack absent on
            # the Mac -> the code passes a non-bytes value straight through)
            fields = {0x02: {0x01: 111, 0x07: 44.0, 0x0F: "node X"}}

        with self.assertLogs("apps.reticulum.backend.lxmf_service", "INFO"):
            had = svc._record_inbound_telemetry(_Msg(), "deadbeef", "X")
        self.assertTrue(had)
        peers = svc.telemetry_peers()
        self.assertEqual(peers[0]["destination_hash"], "deadbeef")
        self.assertEqual(peers[0]["temperature_c"], 44.0)
        self.assertEqual(peers[0]["info"], "node X")
        self.assertEqual(peers[0]["name"], "X")


class TestInboundNotify(unittest.TestCase):
    def test_notify_inbound_posts_preview_and_sender(self) -> None:
        svc = _make_service(notify_url="https://ntfy.sh/topic")
        with mock.patch.object(lxmf_service.notify, "post") as post:
            asyncio.run(svc._notify_inbound("Bob", "hello there"))
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["title"], "LXMF from Bob")
        self.assertEqual(post.call_args.kwargs["body"], "hello there")

    def test_notify_inbound_truncates_long_text(self) -> None:
        svc = _make_service(notify_url="https://x")
        with mock.patch.object(lxmf_service.notify, "post") as post:
            asyncio.run(svc._notify_inbound("Bob", "x" * 500))
        body = post.call_args.kwargs["body"]
        self.assertEqual(len(body), 240)
        self.assertTrue(body.endswith("..."))

    def test_notify_inbound_swallows_errors(self) -> None:
        svc = _make_service(notify_url="https://x")
        with mock.patch.object(lxmf_service.notify, "post", side_effect=RuntimeError):
            asyncio.run(svc._notify_inbound("Bob", "hi"))  # must not raise


class _FakeNode:
    """Stand-in for NomadNode's public snapshot surface (nomad_node.py) --
    talkback only ever reads through these, never a real hosted node."""

    def __init__(self, name="TestNode", spaceapi_configured=False,
                 events_configured=False, stats=None, spaceapi=None, events=None):
        self.name = name
        self.spaceapi_configured = spaceapi_configured
        self.events_configured = events_configured
        self._stats = stats if stats is not None else {}
        self._spaceapi = spaceapi if spaceapi is not None else {}
        self._events = events if events is not None else []

    def stats_snapshot(self):
        return dict(self._stats)

    def spaceapi_snapshot(self):
        return dict(self._spaceapi)

    def events_snapshot(self):
        return list(self._events)


class TestInboundMessageBroadcast(unittest.TestCase):
    """Confirmed live 2026-09-08: the core cross-protocol Messages page
    only listens for 'message_received' -- 'reticulum_message' is
    plugin-private (reticulum_panel.js's own listener), so without also
    firing the core event an inbound Reticulum message (including a
    talkback reply) never live-updates an open thread there, only after
    a manual page reload."""

    def test_fires_only_reticulum_events(self) -> None:
        svc = _make_service(
            peer_repo=_FakePeerRepo(), message_repo=_FakeMessageRepo(), ws_manager=_FakeWs(),
        )
        message = mock.Mock(source_hash=b"\xaa" * 16, content=b"hello", hash=b"\xbb" * 8)
        with mock.patch.object(lxmf_service, "RNS") as mock_rns:
            mock_rns.hexrep.return_value = "aa" * 16
            asyncio.run(svc._handle_inbound_message(message))

        kinds = [e[0] for e in svc._ws_manager.events]
        self.assertIn("reticulum_message", kinds)
        self.assertIn("reticulum_message_received", kinds)

        core_payload = next(d for k, d in svc._ws_manager.events if k == "reticulum_message_received")
        self.assertEqual(core_payload["protocol"], "reticulum")
        self.assertEqual(core_payload["direction"], "received")
        self.assertEqual(core_payload["text"], "hello")
        self.assertEqual(core_payload["node_id"], "aa" * 16)


class TestTalkback(unittest.TestCase):
    """``_maybe_talkback`` is tested directly with plain source_hex/text
    strings, the same way ``_handle_announce`` is tested separately from
    ``_on_announce`` -- ``_handle_inbound_message`` itself needs a real RNS
    ``message`` object and stays integration-level (see this file's module
    docstring)."""

    def _svc(self, **node_kw) -> LxmfService:
        svc = _make_service(talkback_enabled=True)
        svc._node = _FakeNode(**node_kw)
        return svc

    @staticmethod
    def _run_and_flush(fn) -> None:
        """Runs a sync call that spawns a fire-and-forget task (_spawn ->
        asyncio.ensure_future) and yields once so that task actually runs
        to completion before the test asserts on it."""
        async def runner():
            fn()
            await asyncio.sleep(0)
        asyncio.run(runner())

    def test_ping_gets_a_reply(self) -> None:
        svc = self._svc()
        sent = []

        async def fake_send(dest, text):
            sent.append((dest, text))
        svc._send_talkback_reply = fake_send

        self._run_and_flush(lambda: svc._maybe_talkback("aa" * 16, ".ping"))
        self.assertEqual(sent, [("aa" * 16, "pong")])

    def test_unrecognized_text_gets_no_reply(self) -> None:
        svc = self._svc()
        sent = []
        svc._send_talkback_reply = lambda d, t: sent.append((d, t))

        self._run_and_flush(lambda: svc._maybe_talkback("aa" * 16, "just chatting"))
        self.assertEqual(sent, [])

    def test_bare_word_without_dot_gets_no_reply(self) -> None:
        # The dot prefix exists so a human typing a plain "ping"/"stats"
        # doesn't get an unexpected bot reply instead of their correspondent.
        svc = self._svc()
        sent = []
        svc._send_talkback_reply = lambda d, t: sent.append((d, t))

        self._run_and_flush(lambda: svc._maybe_talkback("aa" * 16, "ping"))
        self.assertEqual(sent, [])

    def test_disabled_service_never_calls_maybe_talkback(self) -> None:
        # _handle_inbound_message gates on self._talkback_enabled before
        # calling _maybe_talkback -- verify the flag itself is off by
        # default so a plain _make_service() never wires this up.
        svc = _make_service()
        self.assertFalse(svc._talkback_enabled)

    def test_cooldown_suppresses_a_second_reply(self) -> None:
        svc = self._svc()
        sent = []

        async def fake_send(dest, text):
            sent.append((dest, text))
        svc._send_talkback_reply = fake_send

        async def runner():
            svc._maybe_talkback("aa" * 16, ".ping")
            svc._maybe_talkback("aa" * 16, ".ping")
            await asyncio.sleep(0)
        asyncio.run(runner())
        self.assertEqual(len(sent), 1)

    def test_never_replies_to_its_own_address(self) -> None:
        svc = self._svc()
        sent = []
        svc._send_talkback_reply = lambda d, t: sent.append((d, t))
        own_hex = "aa" * 16
        with mock.patch.object(lxmf_service, "RNS") as mock_rns:
            mock_rns.hexrep.return_value = own_hex
            svc._source = mock.Mock(hash=b"\xaa" * 16)
            self._run_and_flush(lambda: svc._maybe_talkback(own_hex, ".ping"))
        self.assertEqual(sent, [])

    def test_stats_reply_uses_node_snapshot(self) -> None:
        svc = self._svc(name="TechInc Node", stats={"version": "0.8.1"})
        sent = []

        async def fake_send(dest, text):
            sent.append((dest, text))
        svc._send_talkback_reply = fake_send

        self._run_and_flush(lambda: svc._maybe_talkback("bb" * 16, ".stats"))
        self.assertEqual(len(sent), 1)
        self.assertIn("TechInc Node", sent[0][1])
        self.assertIn("0.8.1", sent[0][1])

    def test_spacestate_reply_only_fetched_when_configured(self) -> None:
        svc = self._svc(spaceapi_configured=False)
        sent = []

        async def fake_send(dest, text):
            sent.append((dest, text))
        svc._send_talkback_reply = fake_send

        self._run_and_flush(lambda: svc._maybe_talkback("cc" * 16, ".spacestate"))
        self.assertEqual(len(sent), 1)
        self.assertIn("isn't configured", sent[0][1])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
