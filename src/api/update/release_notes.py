"""Release-notes parser for the dashboard "what's coming" preview.

Parses ``docs/CHANGELOG.md`` into structured sections so the
Settings -> Updates panel can show the operator a curated bullet
list of what landed in the recent release (for the ``stable``
channel) or what is staged for the next bump (the ``Unreleased``
section, surfaced for the ``rc`` channel).

This module deliberately stays local-file-only: the source of
truth is the CHANGELOG that ships in the working tree on the box.
We don't reach out to GitHub here -- a future enhancement could
read the same file from ``origin/<branch>`` after a ``git fetch``,
but for v0.7.4 the local file is the contract.

The parser is tolerant of CRLF line endings and stray blank lines
so checkout-time line normalisation can't break it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_HEADER_RE = re.compile(r"^###\s+(?P<body>.+?)\s*$")
_VERSION_RE = re.compile(
    r"^v(?P<version>\d+(?:\.\d+){1,3})(?:\s+\((?P<date>[^)]+)\))?$"
)
_UNRELEASED_RE = re.compile(r"^Unreleased$", re.IGNORECASE)
_BULLET_RE = re.compile(
    r"^-\s+\*\*(?P<headline>[^*]+?)\*\*\s*(?P<detail>.*)$"
)


@dataclass(frozen=True)
class ChangelogBullet:
    """One ``- **headline.** detail`` line in a changelog section."""

    headline: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChangelogSection:
    """One ``### v0.x.y`` (or ``### Unreleased``) block."""

    header: str
    version: str | None
    date: str | None
    is_unreleased: bool
    bullets: list[ChangelogBullet] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "version": self.version,
            "date": self.date,
            "is_unreleased": self.is_unreleased,
            "bullets": [b.to_dict() for b in self.bullets],
        }


class ChangelogParser:
    """Turn ``CHANGELOG.md`` text into a list of :class:`ChangelogSection`."""

    @staticmethod
    def parse_text(text: str) -> list[ChangelogSection]:
        sections: list[ChangelogSection] = []
        current: ChangelogSection | None = None
        for raw_line in text.splitlines():
            line = raw_line.rstrip("\r")
            header_match = _HEADER_RE.match(line)
            if header_match:
                current = _section_from_header(header_match.group("body"))
                if current is not None:
                    sections.append(current)
                continue
            if current is None:
                continue
            bullet_match = _BULLET_RE.match(line)
            if bullet_match:
                headline = bullet_match.group("headline").strip().rstrip(".")
                detail = bullet_match.group("detail").strip()
                current.bullets.append(
                    ChangelogBullet(headline=headline, detail=detail)
                )
        return sections

    @staticmethod
    def parse_file(path: Path) -> list[ChangelogSection]:
        text = path.read_text(encoding="utf-8")
        return ChangelogParser.parse_text(text)


def _section_from_header(body: str) -> ChangelogSection | None:
    if _UNRELEASED_RE.match(body):
        return ChangelogSection(
            header=body,
            version=None,
            date=None,
            is_unreleased=True,
        )
    version_match = _VERSION_RE.match(body)
    if version_match:
        return ChangelogSection(
            header=body,
            version=version_match.group("version"),
            date=version_match.group("date"),
            is_unreleased=False,
        )
    return None


def select_preview_section(
    sections: list[ChangelogSection], *, tier: str
) -> ChangelogSection | None:
    """Pick the right section for the ``release_notes`` endpoint.

    * ``rc``     -> the first ``Unreleased`` section, since that is
                    the staging area for whatever lands next.
    * ``stable`` -> the first non-``Unreleased`` section, i.e. the
                    most recent shipped release.
    * anything else (e.g. ``custom``) -> ``None``; the dashboard
                    renders a generic "no preview available" notice.
    """
    if tier == "rc":
        for section in sections:
            if section.is_unreleased:
                return section
        return None
    if tier == "stable":
        for section in sections:
            if not section.is_unreleased:
                return section
        return None
    return None
