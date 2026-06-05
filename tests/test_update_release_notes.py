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
    format_section_for_preview,
    sanitize_detail_for_preview,
    select_preview_section,
)


_FIXTURE = """# Changelog

### Unreleased

Queued for the next version bump. Bullets in this section will be folded into the release header (and dated) when the version is cut.

### v0.7.4 (May 2026)

- **New sidebar IA.** Persistent nav for Dashboard, Messages, Stats, and Radio.
- **Settings > Auth.** Change admin password from the dashboard.

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

    def test_parses_unreleased_and_versioned_sections(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        self.assertEqual(len(sections), 4)

    def test_unreleased_section_flagged(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        unreleased = sections[0]
        self.assertTrue(unreleased.is_unreleased)
        self.assertIsNone(unreleased.version)
        self.assertIsNone(unreleased.date)
        self.assertEqual(unreleased.header, "Unreleased")

    def test_versioned_section_carries_version_and_date(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        v074 = sections[1]
        self.assertFalse(v074.is_unreleased)
        self.assertEqual(v074.version, "0.7.4")
        self.assertEqual(v074.date, "May 2026")

    def test_bullets_split_headline_and_detail(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        v074 = sections[1]
        self.assertEqual(len(v074.bullets), 2)
        first = v074.bullets[0]
        self.assertEqual(first.headline, "New sidebar IA")
        self.assertTrue(first.detail.startswith("Persistent nav"))

    def test_intro_paragraphs_are_ignored(self) -> None:
        sections = ChangelogParser.parse_text(_FIXTURE)
        unreleased = sections[0]
        self.assertEqual(len(unreleased.bullets), 0)

    def test_crlf_line_endings_tolerated(self) -> None:
        crlf = _FIXTURE.replace("\n", "\r\n")
        sections = ChangelogParser.parse_text(crlf)
        self.assertEqual(len(sections), 4)
        self.assertEqual(len(sections[1].bullets), 2)

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

    def test_rc_tier_does_not_surface_older_release_when_076_missing(self) -> None:
        section = select_preview_section(
            self.sections, tier="rc", channel_id="rc-077",
        )
        self.assertIsNone(section)

    def test_rc_tier_maps_075_to_shipped_release(self) -> None:
        fixture = _FIXTURE.replace(
            "### v0.7.4 (May 2026)",
            "### v0.7.5 (May 2026)\n\n- **gpsd.** Live skyplot.\n\n### v0.7.4 (May 2026)",
        )
        sections = ChangelogParser.parse_text(fixture)
        section = select_preview_section(
            sections, tier="rc", channel_id="rc-075",
        )
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.version, "0.7.5")

    def test_rc_tier_accepts_retired_channel_id(self) -> None:
        section = select_preview_section(
            self.sections, tier="rc", channel_id="rc-074",
        )
        self.assertIsNone(section)

    def test_rc_tier_prefers_unreleased_over_older_shipped_release(self) -> None:
        """Pi-shaped CHANGELOG: Unreleased holds RC bullets, no v0.7.4 header yet."""
        from src.api.update.release_notes import ChangelogBullet

        pi_sections = [
            ChangelogSection(
                header="Unreleased",
                version=None,
                date=None,
                is_unreleased=True,
                bullets=[
                    ChangelogBullet(
                        headline="New sidebar IA",
                        detail="Persistent nav for Dashboard.",
                    ),
                ],
            ),
            ChangelogSection(
                header="v0.7.3.1 (May 13, 2026)",
                version="0.7.3.1",
                date="May 13, 2026",
                is_unreleased=False,
                bullets=[
                    ChangelogBullet(
                        headline="WS auth close frame",
                        detail="accept before close.",
                    ),
                ],
            ),
        ]
        rc = select_preview_section(
            pi_sections, tier="rc", channel_id="rc-074", installed_version="0.7.3.1",
        )
        stable = select_preview_section(
            pi_sections, tier="stable", installed_version="0.7.3.1",
        )
        self.assertIsNotNone(rc)
        self.assertIsNotNone(stable)
        assert rc is not None and stable is not None
        self.assertTrue(rc.is_unreleased)
        self.assertEqual(stable.version, "0.7.3.1")
        self.assertNotEqual(rc.header, stable.header)

    def test_rc_tier_falls_back_to_unreleased_when_no_version_block(self) -> None:
        from src.api.update.release_notes import ChangelogBullet

        only_unreleased = [
            ChangelogSection(
                header="Unreleased",
                version=None,
                date=None,
                is_unreleased=True,
                bullets=[
                    ChangelogBullet(
                        headline="Only unreleased item",
                        detail="detail",
                    ),
                ],
            )
        ]
        section = select_preview_section(
            only_unreleased, tier="rc", channel_id="rc-074",
        )
        self.assertIsNotNone(section)
        assert section is not None
        self.assertTrue(section.is_unreleased)

    def test_stable_tier_returns_installed_version_section(self) -> None:
        section = select_preview_section(
            self.sections, tier="stable", installed_version="0.7.3.1",
        )
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.version, "0.7.3.1")

    def test_stable_tier_skips_newer_in_flight_release(self) -> None:
        section = select_preview_section(
            self.sections, tier="stable", installed_version="0.7.3.1",
        )
        assert section is not None
        self.assertNotEqual(section.version, "0.7.4")

    def test_custom_tier_returns_none(self) -> None:
        section = select_preview_section(self.sections, tier="custom")
        self.assertIsNone(section)

    def test_unknown_tier_returns_none(self) -> None:
        section = select_preview_section(self.sections, tier="garbage")
        self.assertIsNone(section)

    def test_rc_returns_first_versioned_when_no_unreleased_block(self) -> None:
        only_released = [s for s in self.sections if not s.is_unreleased]
        section = select_preview_section(only_released, tier="rc")
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.version, "0.7.4")

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


class TestPreviewFormatting(unittest.TestCase):
    def test_sanitize_detail_truncates_long_text(self) -> None:
        long = "x" * 200
        out = sanitize_detail_for_preview(long, max_len=50)
        self.assertLessEqual(len(out), 50)
        self.assertTrue(out.endswith("…"))

    def test_format_section_truncates_bullet_details(self) -> None:
        from src.api.update.release_notes import ChangelogBullet

        section = ChangelogSection(
            header="v0.7.3.1",
            version="0.7.3.1",
            date=None,
            is_unreleased=False,
            bullets=[
                ChangelogBullet(
                    headline="Short",
                    detail="Brief note.",
                ),
                ChangelogBullet(
                    headline="Long",
                    detail="A" * 300,
                ),
            ],
        )
        payload = format_section_for_preview(section)
        self.assertEqual(payload["bullets"][0]["detail"], "Brief note.")
        self.assertTrue(payload["bullets"][1]["detail"].endswith("…"))


if __name__ == "__main__":
    unittest.main()
