"""Tests for backend/spaceapi.py -- the SpaceAPI fetch + normalise.

No network: apps.reticulum.backend.http.open_request is patched with a canned response.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from apps.reticulum.backend import spaceapi

_V013 = {
    "api": "0.13",
    "space": "Technologia Incognita",
    "url": "https://www.techinc.nl",
    "state": {"open": False},
    "open": False,
    "lastchange": 1700000000,
    "location": {"address": "Louwesweg 1, Amsterdam"},
    "contact": {"irc": "#techinc @ OFTC", "email": "hack AT techinc DOT nl",
                "ml": "members@techinc.nl"},
}

_V15 = {
    "api_compatibility": ["15"],
    "space": "Nerdspace",
    "url": "https://nerd.space",
    "state": {"open": True, "message": "come on in", "lastchange": 1699999999},
    "location": {"address": "Somewhere 12"},
    "contact": {"email": "info@nerd.space"},
}


def _resp(obj):
    return mock.MagicMock(
        __enter__=lambda s: io.BytesIO(json.dumps(obj).encode()),
        __exit__=lambda *a: False,
    )


class TestFetch(unittest.TestCase):
    def _fetch(self, obj):
        with mock.patch("apps.reticulum.backend.http.open_request", return_value=_resp(obj)):
            return spaceapi.fetch("https://x/spaceapi.json")

    def test_blank_url_returns_none(self) -> None:
        self.assertIsNone(spaceapi.fetch(""))

    def test_v013_top_level_open_and_deobfuscated_email(self) -> None:
        out = self._fetch(_V013)
        self.assertIs(out["open"], False)
        self.assertEqual(out["space"], "Technologia Incognita")
        self.assertEqual(out["email"], "hack@techinc.nl")
        self.assertEqual(out["irc"], "#techinc @ OFTC")
        self.assertEqual(out["lastchange"], 1700000000)
        self.assertEqual(out["address"], "Louwesweg 1, Amsterdam")

    def test_v15_nested_state(self) -> None:
        out = self._fetch(_V15)
        self.assertIs(out["open"], True)
        self.assertEqual(out["message"], "come on in")
        self.assertEqual(out["lastchange"], 1699999999)
        self.assertEqual(out["email"], "info@nerd.space")

    def test_missing_state_gives_open_none(self) -> None:
        out = self._fetch({"space": "X", "url": "https://x"})
        self.assertIsNone(out["open"])

    def test_network_error_returns_none(self) -> None:
        with mock.patch("apps.reticulum.backend.http.open_request", side_effect=OSError("boom")):
            self.assertIsNone(spaceapi.fetch("https://x"))

    def test_garbage_body_returns_none(self) -> None:
        with mock.patch(
            "apps.reticulum.backend.http.open_request",
            return_value=mock.MagicMock(
                __enter__=lambda s: io.BytesIO(b"not json"),
                __exit__=lambda *a: False,
            ),
        ):
            self.assertIsNone(spaceapi.fetch("https://x"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
