"""Tests for backend/node_pages.py -- the Pages-tab file layer.

Pure filesystem + regex, no FastAPI, no RNS. A tmp dir stands in for
``node_pages_dir``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.reticulum.backend import node_pages
from apps.reticulum.backend.node_pages import PageError


class TestValidateName(unittest.TestCase):
    def test_accepts_plain_mu_names(self) -> None:
        for name in ("index.mu", "about.mu", "my-page_2.mu"):
            self.assertEqual(node_pages.validate_name(name), name)

    def test_rejects_non_mu(self) -> None:
        for name in ("index", "index.txt", "index.mu.sh", ""):
            with self.assertRaises(PageError):
                node_pages.validate_name(name)

    def test_rejects_path_separators_and_traversal(self) -> None:
        for name in ("../evil.mu", "a/b.mu", "/etc/x.mu", "..mu", "....mu"):
            with self.assertRaises(PageError):
                node_pages.validate_name(name)

    def test_rejects_reserved_generated_names(self) -> None:
        for name in ("info.mu", "nodes.mu"):
            with self.assertRaises(PageError):
                node_pages.validate_name(name)


class TestPageIO(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "pages"  # deliberately absent

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_write_creates_dir_and_read_roundtrips(self) -> None:
        meta = node_pages.write_page(self.dir, "index.mu", "`!hi`!\n")
        self.assertTrue(meta["exists"])
        self.assertEqual(node_pages.read_page(self.dir, "index.mu"), "`!hi`!\n")
        self.assertTrue((self.dir / "index.mu").is_file())

    def test_written_file_is_not_executable(self) -> None:
        node_pages.write_page(self.dir, "x.mu", "hi")
        mode = (self.dir / "x.mu").stat().st_mode
        self.assertEqual(mode & 0o111, 0, "page must never be executable")

    def test_read_missing_page_is_empty_string(self) -> None:
        self.assertEqual(node_pages.read_page(self.dir, "nope.mu"), "")

    def test_oversized_write_is_rejected(self) -> None:
        big = "a" * (node_pages.MAX_PAGE_BYTES + 1)
        with self.assertRaises(PageError):
            node_pages.write_page(self.dir, "big.mu", big)

    def test_delete_is_idempotent(self) -> None:
        node_pages.write_page(self.dir, "x.mu", "hi")
        node_pages.delete_page(self.dir, "x.mu")
        node_pages.delete_page(self.dir, "x.mu")  # no error second time
        self.assertFalse((self.dir / "x.mu").exists())

    def test_list_puts_index_first_and_always_lists_it(self) -> None:
        node_pages.write_page(self.dir, "zeta.mu", "z")
        node_pages.write_page(self.dir, "about.mu", "a")
        names = [e["name"] for e in node_pages.list_pages(self.dir)]
        self.assertEqual(names, ["index.mu", "about.mu", "zeta.mu"])
        index_entry = node_pages.list_pages(self.dir)[0]
        self.assertFalse(index_entry["exists"])  # listed but not created yet

    def test_list_ignores_reserved_and_non_mu(self) -> None:
        self.dir.mkdir(parents=True)
        (self.dir / "info.mu").write_text("x")
        (self.dir / "nodes.mu").write_text("x")
        (self.dir / "notes.txt").write_text("x")
        node_pages.write_page(self.dir, "real.mu", "x")
        names = [e["name"] for e in node_pages.list_pages(self.dir)]
        self.assertEqual(sorted(names), ["index.mu", "real.mu"])

    def test_write_rejects_reserved_name(self) -> None:
        with self.assertRaises(PageError):
            node_pages.write_page(self.dir, "info.mu", "x")


class TestSampleIndex(unittest.TestCase):
    def test_sample_index_returns_micron_text(self) -> None:
        text = node_pages.sample_index()
        self.assertIsInstance(text, str)
        self.assertTrue(text.strip())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
