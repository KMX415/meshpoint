"""Cache-busting asset URL rewriter (no FastAPI required).

Credit: javastraat/meshpoint ``52b6caf``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.api.html_assets import BOOT_TOKEN, bust_asset_urls


class BustAssetUrlsTest(unittest.TestCase):
    def test_relative_js_and_css_get_the_token(self):
        html = (
            '<script src="js/app.js"></script>'
            '<link rel="stylesheet" href="css/dashboard.css">'
        )
        out = bust_asset_urls(html, token="abc123")
        self.assertIn('src="js/app.js?v=abc123"', out)
        self.assertIn('href="css/dashboard.css?v=abc123"', out)

    def test_root_relative_vendor_paths_get_the_token(self):
        html = '<script src="/vendor/xterm/xterm.js"></script>'
        out = bust_asset_urls(html, token="abc123")
        self.assertIn('src="/vendor/xterm/xterm.js?v=abc123"', out)

    def test_external_urls_left_untouched(self):
        html = (
            '<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>'
            '<script src="//cdn.example.com/lib.js"></script>'
            '<link href="http://example.com/style.css">'
        )
        self.assertEqual(bust_asset_urls(html, token="abc123"), html)

    def test_non_asset_urls_left_untouched(self):
        html = (
            '<img src="/assets/meshpoint-logo.png">'
            '<a href="/api/device/metrics">metrics</a>'
        )
        self.assertEqual(bust_asset_urls(html, token="abc123"), html)

    def test_already_versioned_urls_not_double_tokened(self):
        html = '<script src="js/app.js?v=old"></script>'
        self.assertEqual(bust_asset_urls(html, token="new"), html)

    def test_default_token_is_the_boot_token(self):
        out = bust_asset_urls('<script src="js/a.js"></script>')
        self.assertIn(f'src="js/a.js?v={BOOT_TOKEN}"', out)
        self.assertTrue(re.fullmatch(r"[0-9a-f]+", BOOT_TOKEN))

    def test_real_index_html_rewrites_every_local_asset(self):
        html = Path("frontend/index.html").read_text(encoding="utf-8")
        out = bust_asset_urls(html, token="t0k")
        leftovers = re.findall(
            r'(?:src|href)="(?!https?://|//)[^"?]+\.(?:js|css)"',
            out,
        )
        self.assertEqual(leftovers, [])
        self.assertEqual(
            len(re.findall(r'(?:src|href)="https?://[^"]+"', out)),
            len(re.findall(r'(?:src|href)="https?://[^"]+"', html)),
        )


if __name__ == "__main__":
    unittest.main()
