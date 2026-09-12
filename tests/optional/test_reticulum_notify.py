"""Tests for backend/notify.py -- the inbound-message push POST.

No network: apps.reticulum.backend.http.open_request is patched.
"""

from __future__ import annotations

import io
import unittest
import urllib.error
from unittest import mock

from apps.reticulum.backend import notify


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return io.BytesIO(b"ok")

    def __exit__(self, *a):
        return False


class TestPost(unittest.TestCase):
    def test_blank_url_is_false(self) -> None:
        self.assertFalse(notify.post("", title="x", body="y"))

    def test_success_returns_true_and_sends_body_and_title(self) -> None:
        captured = {}

        def _fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["data"] = req.data
            captured["title"] = req.get_header("Title")
            return _Resp(200)

        with mock.patch("apps.reticulum.backend.http.open_request", _fake_urlopen):
            ok = notify.post("https://ntfy.sh/topic", title="LXMF from Bob", body="hello there")
        self.assertTrue(ok)
        self.assertEqual(captured["url"], "https://ntfy.sh/topic")
        self.assertEqual(captured["data"], b"hello there")
        self.assertEqual(captured["title"], "LXMF from Bob")

    def test_http_error_returns_false(self) -> None:
        err = urllib.error.HTTPError("u", 500, "err", {}, None)
        with mock.patch("apps.reticulum.backend.http.open_request", side_effect=err):
            self.assertFalse(notify.post("https://x", title="t", body="b"))

    def test_network_error_returns_false(self) -> None:
        with mock.patch("apps.reticulum.backend.http.open_request", side_effect=OSError("boom")):
            self.assertFalse(notify.post("https://x", title="t", body="b"))

    def test_empty_body_becomes_placeholder(self) -> None:
        captured = {}

        def _fake_urlopen(req, timeout=None):
            captured["data"] = req.data
            return _Resp(200)

        with mock.patch("apps.reticulum.backend.http.open_request", _fake_urlopen):
            notify.post("https://x", title="t", body="")
        self.assertEqual(captured["data"], b"(no text)")

    def test_title_is_header_sanitised(self) -> None:
        captured = {}

        def _fake_urlopen(req, timeout=None):
            captured["title"] = req.get_header("Title")
            return _Resp(200)

        with mock.patch("apps.reticulum.backend.http.open_request", _fake_urlopen):
            notify.post("https://x", title="from \n Ünïcode 🎉 dude", body="b")
        self.assertNotIn("\n", captured["title"])
        self.assertTrue(captured["title"].isascii())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
