"""Tests for ``src.hal.location.models`` domain dataclasses."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.hal.location.models import (
    GpsDeviceInfo,
    GpsStatus,
    LocationFix,
    Satellite,
    SatellitesView,
    classify_gnss_id,
)


class TestSatellite(unittest.TestCase):
    """``Satellite`` is the per-receiver-track record."""

    def test_to_dict_round_trip(self) -> None:
        sat = Satellite(
            prn=5,
            azimuth=150.5,
            elevation=65.0,
            snr_dbhz=42.0,
            used=True,
            gnss="GPS",
        )
        self.assertEqual(
            sat.to_dict(),
            {
                "prn": 5,
                "azimuth": 150.5,
                "elevation": 65.0,
                "snr_dbhz": 42.0,
                "used": True,
                "gnss": "GPS",
            },
        )

    def test_no_signal_satellite_round_trips(self) -> None:
        # Skyplot UI must render satellites even when SNR is 0
        # (unhealthy or just-acquired tracks). None values stay None.
        sat = Satellite(
            prn=12, azimuth=20.0, elevation=5.0,
            snr_dbhz=0.0, used=False, gnss="GLONASS",
        )
        self.assertEqual(sat.to_dict()["snr_dbhz"], 0.0)
        self.assertFalse(sat.to_dict()["used"])

    def test_satellite_is_frozen(self) -> None:
        sat = Satellite(prn=1, azimuth=0.0, elevation=0.0,
                        snr_dbhz=0.0, used=False, gnss="GPS")
        with self.assertRaises(Exception):
            sat.prn = 2  # type: ignore[misc]


class TestLocationFix(unittest.TestCase):
    """``LocationFix`` carries position + DOP + estimated error."""

    def test_no_fix_has_no_position(self) -> None:
        fix = LocationFix(mode=1, latitude=None, longitude=None, altitude_m=None)
        self.assertFalse(fix.has_position)
        self.assertEqual(fix.mode_label, "NO FIX")

    def test_2d_fix_has_position(self) -> None:
        fix = LocationFix(mode=2, latitude=40.0, longitude=-74.0, altitude_m=None)
        self.assertTrue(fix.has_position)
        self.assertEqual(fix.mode_label, "2D")

    def test_3d_fix_has_position_and_altitude(self) -> None:
        fix = LocationFix(
            mode=3, latitude=40.0, longitude=-74.0, altitude_m=12.0,
            hdop=0.9, pdop=1.4, vdop=1.1,
        )
        self.assertTrue(fix.has_position)
        self.assertEqual(fix.mode_label, "3D")

    def test_unknown_mode_label_falls_back(self) -> None:
        # gpsd guarantees mode in {0,1,2,3} but be defensive.
        fix = LocationFix(mode=99, latitude=None, longitude=None, altitude_m=None)
        self.assertEqual(fix.mode_label, "UNKNOWN")

    def test_partial_position_does_not_count_as_fixed(self) -> None:
        # mode=2 but lat=None can happen mid-fix-acquisition. Skyplot
        # should not jump the dashboard map until both are present.
        fix = LocationFix(mode=2, latitude=None, longitude=-74.0, altitude_m=None)
        self.assertFalse(fix.has_position)

    def test_to_dict_serializes_iso_time(self) -> None:
        when = datetime(2026, 5, 30, 16, 37, 1, tzinfo=timezone.utc)
        fix = LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=12.0, time=when)
        self.assertEqual(fix.to_dict()["time"], "2026-05-30T16:37:01+00:00")


class TestSatellitesView(unittest.TestCase):
    """``SatellitesView`` aggregates per-SKY-report satellite tallies."""

    def test_from_satellites_counts_used(self) -> None:
        sats = [
            Satellite(prn=1, azimuth=0.0, elevation=0.0, snr_dbhz=10.0, used=True, gnss="GPS"),
            Satellite(prn=2, azimuth=0.0, elevation=0.0, snr_dbhz=10.0, used=True, gnss="GPS"),
            Satellite(prn=3, azimuth=0.0, elevation=0.0, snr_dbhz=10.0, used=False, gnss="GPS"),
        ]
        view = SatellitesView.from_satellites(sats)
        self.assertEqual(view.in_view, 3)
        self.assertEqual(view.used, 2)

    def test_empty_view(self) -> None:
        view = SatellitesView.from_satellites([])
        self.assertEqual(view.in_view, 0)
        self.assertEqual(view.used, 0)
        self.assertEqual(view.satellites, ())

    def test_to_dict_emits_list_key(self) -> None:
        # Frontend reads ``satellites.list`` for the bullseye renderer.
        sats = [Satellite(prn=1, azimuth=0.0, elevation=0.0, snr_dbhz=10.0, used=True, gnss="GPS")]
        view = SatellitesView.from_satellites(sats)
        out = view.to_dict()
        self.assertIn("list", out)
        self.assertEqual(len(out["list"]), 1)
        self.assertEqual(out["list"][0]["prn"], 1)


class TestGpsStatus(unittest.TestCase):
    """``GpsStatus`` is the wire shape returned by ``/api/device/gps-status``."""

    def test_static_status_has_no_device_or_satellites(self) -> None:
        status = GpsStatus(
            source="static",
            available=True,
            fix=LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=10.0),
        )
        out = status.to_dict()
        self.assertEqual(out["source"], "static")
        self.assertTrue(out["available"])
        self.assertIsNone(out["satellites"])
        self.assertIsNone(out["device"])

    def test_gpsd_status_full_payload(self) -> None:
        when = datetime(2026, 5, 30, 16, 37, 2, tzinfo=timezone.utc)
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(
                mode=3, latitude=40.0, longitude=-74.0, altitude_m=12.0,
                hdop=0.9, pdop=1.4, vdop=1.1, time=when,
            ),
            satellites=SatellitesView.from_satellites([
                Satellite(prn=5, azimuth=150.5, elevation=65.0, snr_dbhz=42.0, used=True, gnss="GPS"),
            ]),
            device=GpsDeviceInfo(
                driver="u-blox", path="/dev/ttyACM0",
                model="u-blox 8", subtype="PROTVER 18.00",
            ),
            last_update=when,
        )
        out = status.to_dict()
        self.assertEqual(out["source"], "gpsd")
        self.assertEqual(out["fix"]["mode_label"], "3D")
        self.assertEqual(out["satellites"]["in_view"], 1)
        self.assertEqual(out["satellites"]["used"], 1)
        self.assertEqual(out["device"]["model"], "u-blox 8")
        self.assertEqual(out["last_update"], "2026-05-30T16:37:02+00:00")

    def test_unavailable_status_carries_error(self) -> None:
        # Frontend renders this as "GPSD UNREACHABLE" with the error
        # message under the lamp.
        status = GpsStatus(
            source="gpsd",
            available=False,
            error="Connection refused on 127.0.0.1:2947",
        )
        out = status.to_dict()
        self.assertFalse(out["available"])
        self.assertEqual(out["error"], "Connection refused on 127.0.0.1:2947")
        self.assertIsNone(out["fix"])
        self.assertIsNone(out["satellites"])


class TestGnssClassifier(unittest.TestCase):
    """``classify_gnss_id`` translates gpsd ``gnssid`` to constellation labels."""

    def test_known_constellations(self) -> None:
        cases = [
            (0, "GPS"),
            (1, "SBAS"),
            (2, "Galileo"),
            (3, "BeiDou"),
            (5, "QZSS"),
            (6, "GLONASS"),
            (7, "IRNSS"),
        ]
        for gnssid, expected in cases:
            with self.subTest(gnssid=gnssid):
                self.assertEqual(classify_gnss_id(gnssid), expected)

    def test_unknown_id_falls_back(self) -> None:
        self.assertEqual(classify_gnss_id(99), "UNKNOWN")

    def test_none_id_falls_back(self) -> None:
        # Some gpsd builds omit ``gnssid`` on legacy GPS-only sticks.
        self.assertEqual(classify_gnss_id(None), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
