"""Tests for backend/ical.py -- the iCalendar fetch + parse.

No network: apps.reticulum.backend.http.open_request is patched with a canned response.
"""

from __future__ import annotations

import datetime as dt
import io
import unittest
from unittest import mock

from apps.reticulum.backend import ical

# One folded SUMMARY line (RFC 5545: leading space continues), a floating
# time, a UTC time, an all-day date, and one event already in the past.
_FEED = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Social 2026-09-09\r\n"
    "URL:https://wiki.techinc.nl/Social_2026-09-09\r\n"
    "DTSTART:20260909T190000\r\n"
    "DTEND:20260909T230000\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Mesh Networking with\r\n"
    "  Reticulum\\, part 2\r\n"
    "DTSTART:20260919T130000Z\r\n"
    "URL:https://wiki.techinc.nl/Mesh\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:ALV September 2026\r\n"
    "DTSTART;VALUE=DATE:20260920\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Ancient history\r\n"
    "DTSTART:20200101T190000\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

_NOW = dt.datetime(2026, 9, 8, 12, 0, 0)


def _resp(body: bytes):
    return mock.MagicMock(
        __enter__=lambda s: io.BytesIO(body),
        __exit__=lambda *a: False,
    )


class TestFetch(unittest.TestCase):
    def _fetch(self, body: str):
        with mock.patch("apps.reticulum.backend.http.open_request", return_value=_resp(body.encode())):
            return ical.fetch("https://x/cal.ics", now=_NOW)

    def test_blank_url_returns_none(self) -> None:
        self.assertIsNone(ical.fetch(""))

    def test_parses_and_drops_past_events(self) -> None:
        out = self._fetch(_FEED)
        summaries = [e["summary"] for e in out]
        self.assertIn("Social 2026-09-09", summaries)
        self.assertNotIn("Ancient history", summaries)  # 2020 -> dropped

    def test_sorted_soonest_first(self) -> None:
        out = self._fetch(_FEED)
        starts = [ical._sort_key(e["start"]) for e in out]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(out[0]["summary"], "Social 2026-09-09")

    def test_line_unfolding_and_unescaping(self) -> None:
        out = self._fetch(_FEED)
        mesh = next(e for e in out if e["summary"].startswith("Mesh"))
        self.assertEqual(mesh["summary"], "Mesh Networking with Reticulum, part 2")

    def test_all_day_event(self) -> None:
        out = self._fetch(_FEED)
        alv = next(e for e in out if e["summary"].startswith("ALV"))
        self.assertTrue(alv["all_day"])
        self.assertIsInstance(alv["start"], dt.date)
        self.assertNotIsInstance(alv["start"], dt.datetime)
        self.assertEqual(ical.format_when(alv), "Sun 20 Sep")

    def test_utc_suffix_converted_to_local(self) -> None:
        out = self._fetch(_FEED)
        mesh = next(e for e in out if e["summary"].startswith("Mesh"))
        # 13:00 UTC -> naive local; exact hour depends on the runner's TZ, but
        # it must be a naive datetime, not left with a tzinfo or the literal Z.
        self.assertIsInstance(mesh["start"], dt.datetime)
        self.assertIsNone(mesh["start"].tzinfo)

    def test_format_when_timed(self) -> None:
        ev = {"start": dt.datetime(2026, 9, 9, 19, 0), "all_day": False}
        self.assertEqual(ical.format_when(ev), "Wed 9 Sep  19:00")

    def test_network_error_returns_none(self) -> None:
        with mock.patch("apps.reticulum.backend.http.open_request", side_effect=OSError("boom")):
            self.assertIsNone(ical.fetch("https://x", now=_NOW))

    def test_non_ical_body_is_empty_not_none(self) -> None:
        self.assertEqual(self._fetch("not a calendar at all"), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
