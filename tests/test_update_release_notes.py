"""Unit tests for ``src.api.update.release_notes``.

Covers the parser shape, header dispatch (Unreleased vs released),
bullet decomposition into ``headline`` + ``detail``, CRLF tolerance,
and the channel-tier dispatch helper.
"""

from __future__ import annotations

import unittest

from src.api.update.release_notes import (
    ChangelogParser,
    ChangelogSection,
    select_preview_section,
)


_FIXTURE = """# Changelog

### Unreleased

Queued for the next version bump. Bullets in this section will be folded into the release header (and dated) when the version is cut.

- **MeshCore nodes now appear on the dashboard map.** MeshCore advertises position on the *advertisement* packet itself.
- **Live radar blips on /login and /setup.** Blips are sourced from a scrubbed packet feed.

### v0.7.3.1 (May 13, 2026)

Hotfix on top of v0.7.3 the same day.

- **WS auth close frame now actually reaches the browser.** server.py was calling close before accept.
- **Dashboard root now redirects unauthenticated requests to /login.** Static mount was leaking index.html.

### v0.7.3 (May 13, 2026)

Local-dashboard authentication, dashboard branding polish.

- **Local dashboard authentication.** First-visit redirects to /setup.
- **`meshpoint reset-password` recovery.** New CLI command for the forgotten-password path.
"""


class TestChangelogParser(unittest.TestCase):
    """Parsing shape and tolerance for malformed / mixed input."""

    def test_parses_unreleased_and_two_versioned_sections(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        self.assertEqual(len(sections), 3)

    def test_unreleased_section_flagged(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        unreleased = sections[0]
        self.assertTrue(unreleased.is_unreleased)
        self.assertIsNone(unreleased.version)
        self.assertIsNone(unreleased.date)
        self.assertEqual(unreleased.header, "Unreleased")

    def test_versioned_section_carries_version_and_date(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        v0731 = sections[1]
        self.assertFalse(v0731.is_unreleased)
        self.assertEqual(v0731.version, "0.7.3.1")
        self.assertEqual(v0731.date, "May 13, 2026")

    def test_bullets_split_headline_and_detail(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        unreleased = sections[0]
        self.assertEqual(len(unreleased.bullets), 2)
        first = unreleased.bullets[0]
        self.assertEqual(
            first.headline, "MeshCore nodes now appear on the dashboard map"
        )
        self.assertTrue(first.detail.startswith("MeshCore advertises position"))

    def test_intro_paragraphs_are_ignored(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        unreleased = sections[0]
        self.assertEqual(len(unreleased.bullets), 2)

    def test_crlf_line_endings_tolerated(self) -> None:
        crlf = _FIXTURE.replace("\n", "\r\n")
        sections = ChangelogParser.parse_text(crlf)
        self.assertEqual(len(sections), 3)
        self.assertEqual(len(sections[0].bullets), 2)

    def test_empty_input_yields_empty_list(self) -> None:
        self.assertEqual(ChangelogParser.parse_text(""), [])

    def test_unrecognised_header_skipped(self) -> None:
        text = "### Older versions\n\nSome prose.\n\n### v0.6.0 (Jan 1, 2025)\n\n- **Initial release.** First cut.\n"
        sections = ChangelogParser.parse_text(text)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].version, "0.6.0")


class TestSelectPreviewSection(unittest.TestCase):
    """Channel-tier -> changelog-section dispatch."""

    def setUp(self) -> None:
        self.sections = ChangelogParser.parse_text(_FIXTURE)

    def test_rc_tier_returns_unreleased(self) -> None:
        section = select_preview_section(self.sections, tier="rc")
        self.assertIsNotNone(section)
        assert section is not None
        self.assertTrue(section.is_unreleased)

    def test_stable_tier_returns_first_released(self) -> None:
        section = select_preview_section(self.sections, tier="stable")
        self.assertIsNotNone(section)
        assert section is not None
        self.assertFalse(section.is_unreleased)
        self.assertEqual(section.version, "0.7.3.1")

    def test_custom_tier_returns_none(self) -> None:
        section = select_preview_section(self.sections, tier="custom")
        self.assertIsNone(section)

    def test_unknown_tier_returns_none(self) -> None:
        section = select_preview_section(self.sections, tier="garbage")
        self.assertIsNone(section)

    def test_rc_returns_none_when_no_unreleased_block(self) -> None:
        only_released = [s for s in self.sections if not s.is_unreleased]
        self.assertIsNone(select_preview_section(only_released, tier="rc"))

    def test_stable_returns_none_when_only_unreleased_exists(self) -> None:
        only_unreleased = [
            ChangelogSection(
                header="Unreleased",
                version=None,
                date=None,
                is_unreleased=True,
            )
        ]
        self.assertIsNone(select_preview_section(only_unreleased, tier="stable"))


if __name__ == "__main__":
    unittest.main()
