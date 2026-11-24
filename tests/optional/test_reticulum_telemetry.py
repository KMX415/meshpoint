"""telemetry.build_telemetry / _info_line -- the Sideband-compatible
frame builder. Pure, no RNS/LXMF, Mac-runnable."""

from __future__ import annotations

import time
import unittest

from apps.reticulum.backend import telemetry
from apps.reticulum.backend.telemetry import (
    SID_INFORMATION,
    SID_LOCATION,
    SID_TEMPERATURE,
    SID_TIME,
)

_FULL_HOST = {
    "pi_model": "Raspberry Pi 4",
    "cpu_temp_c": 61.2,
    "load_1m": 0.42,
    "mem_used_mb": 400,
    "mem_total_mb": 1000,
    "disk_free_gb": 12.3,
    "disk_total_gb": 28.0,
}


class TestBuildTelemetry(unittest.TestCase):
    def test_time_is_always_present_and_recent(self) -> None:
        frame = telemetry.build_telemetry({}, "")
        self.assertIn(SID_TIME, frame)
        self.assertAlmostEqual(frame[SID_TIME], int(time.time()), delta=5)

    def test_temperature_included_as_float_when_available(self) -> None:
        frame = telemetry.build_telemetry(_FULL_HOST, "meshpoint")
        self.assertEqual(frame[SID_TEMPERATURE], 61.2)
        self.assertIsInstance(frame[SID_TEMPERATURE], float)

    def test_temperature_omitted_when_none(self) -> None:
        frame = telemetry.build_telemetry({"cpu_temp_c": None}, "")
        self.assertNotIn(SID_TEMPERATURE, frame)

    def test_information_line_has_the_stats(self) -> None:
        frame = telemetry.build_telemetry(_FULL_HOST, "ti-meshpoint")
        info = frame[SID_INFORMATION]
        self.assertIn("ti-meshpoint", info)
        self.assertIn("load 0.42", info)
        self.assertIn("RAM 40%", info)
        self.assertIn("disk 12.3 GB free", info)
        # temperature is its own SID_TEMPERATURE sensor -- not repeated here
        self.assertNotIn("°C", info)

    def test_information_line_degrades_gracefully(self) -> None:
        self.assertEqual(telemetry._info_line({}, ""), "meshpoint")
        self.assertEqual(telemetry._info_line({}, "node-x"), "node-x")

    def test_information_line_space_state(self) -> None:
        # None (no SpaceAPI URL configured, or nothing fetched yet) omits
        # it entirely rather than printing a meaningless "unknown".
        self.assertEqual(telemetry._info_line({}, "x", None), "x")
        self.assertEqual(telemetry._info_line({}, "x", True), "x · space OPEN")
        self.assertEqual(telemetry._info_line({}, "x", False), "x · space CLOSED")

    def test_build_telemetry_passes_through_space_open(self) -> None:
        frame = telemetry.build_telemetry({}, "x", space_open=True)
        self.assertIn("space OPEN", frame[SID_INFORMATION])
        frame = telemetry.build_telemetry({}, "x", space_open=False)
        self.assertIn("space CLOSED", frame[SID_INFORMATION])
        frame = telemetry.build_telemetry({}, "x")
        self.assertNotIn("space", frame[SID_INFORMATION])

    def test_frame_keys_are_ints(self) -> None:
        frame = telemetry.build_telemetry(_FULL_HOST, "x")
        self.assertTrue(all(isinstance(k, int) for k in frame))

    def test_all_values_are_msgpack_safe(self) -> None:
        # umsgpack.packb on the Pi must not choke -- every value must be a
        # msgpack-native type (int/float/str/bytes/list/dict), recursively.
        def _ok(v):
            if isinstance(v, (int, float, str, bytes, bool)):
                return True
            if isinstance(v, (list, tuple)):
                return all(_ok(x) for x in v)
            if isinstance(v, dict):
                return all(_ok(x) for x in v.values())
            return False

        for host in (_FULL_HOST, {}, {"cpu_temp_c": None, "load_1m": 3}):
            frame = telemetry.build_telemetry(host, "node", location=(52.37, 4.89, 3.0))
            for key, val in frame.items():
                self.assertIsInstance(key, int)
                self.assertTrue(_ok(val), f"{key}={val!r} not msgpack-safe")

    def test_location_included_only_with_real_coords(self) -> None:
        self.assertNotIn(SID_LOCATION, telemetry.build_telemetry(_FULL_HOST, "x"))
        self.assertNotIn(SID_LOCATION, telemetry.build_telemetry(_FULL_HOST, "x", location=None))
        self.assertNotIn(
            SID_LOCATION,
            telemetry.build_telemetry(_FULL_HOST, "x", location=(None, None, 0)),
        )
        frame = telemetry.build_telemetry(_FULL_HOST, "x", location=(52.370216, 4.895168, 5.0))
        self.assertIn(SID_LOCATION, frame)

    def test_decode_round_trips_build(self) -> None:
        # build_telemetry's own dict fed straight into decode_telemetry
        # (skips msgpack -- both sides use the same list/bytes structure).
        frame = telemetry.build_telemetry(
            _FULL_HOST, "ti-meshpoint", location=(52.370216, 4.895168, 5.0),
        )
        dec = telemetry.decode_telemetry(frame)
        self.assertEqual(dec["temperature_c"], 61.2)
        self.assertIn("ti-meshpoint", dec["info"])
        self.assertAlmostEqual(dec["latitude"], 52.370216, places=5)
        self.assertAlmostEqual(dec["longitude"], 4.895168, places=5)
        self.assertAlmostEqual(dec["altitude"], 5.0, places=1)
        self.assertIsInstance(dec["time"], int)

    def test_decode_tolerates_junk(self) -> None:
        self.assertEqual(telemetry.decode_telemetry(None), {})
        self.assertEqual(telemetry.decode_telemetry("nope"), {})
        self.assertEqual(telemetry.decode_telemetry({0x99: "unknown sid"}), {})
        # a location field that isn't a proper list -> just skipped
        dec = telemetry.decode_telemetry({0x01: 123, 0x02: b"bad", 0x07: 40})
        self.assertEqual(dec["time"], 123)
        self.assertEqual(dec["temperature_c"], 40.0)
        self.assertNotIn("latitude", dec)

    def test_decode_bytes_info(self) -> None:
        dec = telemetry.decode_telemetry({0x0F: b"hello \xe2\x82\xac"})
        self.assertEqual(dec["info"], "hello €")

    def test_location_pack_layout(self) -> None:
        loc = telemetry._pack_location(52.370216, 4.895168, 5.0)
        self.assertEqual(len(loc), 7)
        # lat/lon/alt are big-endian signed ints scaled 1e6 / 1e6 / 1e2
        import struct
        self.assertEqual(struct.unpack("!i", loc[0])[0], 52370216)
        self.assertEqual(struct.unpack("!i", loc[1])[0], 4895168)
        self.assertEqual(struct.unpack("!i", loc[2])[0], 500)
        self.assertEqual(struct.unpack("!I", loc[3])[0], 0)   # speed
        self.assertIsInstance(loc[6], int)                    # last_update


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
