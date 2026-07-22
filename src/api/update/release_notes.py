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

from src.api.update.channels import normalize_channel_id

_HEADER_RE = re.compile(r"^###\s+(?P<body>.+?)\s*$")
_CATEGORY_RE = re.compile(r"^####\s+(?P<body>.+?)\s*$")
_VERSION_RE = re.compile(
    r"^v(?P<version>\d+(?:\.\d+){1,3})(?:\s+\((?P<date>[^)]+)\))?$"
)
_UNRELEASED_RE = re.compile(r"^Unreleased$", re.IGNORECASE)
_BULLET_RE = re.compile(
    r"^-\s+\*\*(?P<headline>[^*]+?)\*\*\s*(?P<detail>.*)$"
)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
# Dashboard preview: full CHANGELOG detail is for maintainers, not operators.
_PREVIEW_DETAIL_MAX = 140
_RC_CHANNEL_VERSION: dict[str, str] = {
    "rc-075": "0.7.5",
    "rc-076": "0.7.6",
    "rc-077": "0.7.7",
    "rc-078": "0.7.8",
}


@dataclass(frozen=True)
class ChangelogBullet:
    """One ``- **headline.** detail`` line in a changelog section.

    ``category`` is the nearest preceding ``#### Category`` heading
    inside the section (None for bullets above the first one).
    """

    headline: str
    detail: str
    category: str | None = None

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
        category: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.rstrip("\r")
            header_match = _HEADER_RE.match(line)
            if header_match:
                current = _section_from_header(header_match.group("body"))
                category = None
                if current is not None:
                    sections.append(current)
                continue
            if current is None:
                continue
            category_match = _CATEGORY_RE.match(line)
            if category_match:
                category = category_match.group("body").strip()
                continue
            bullet_match = _BULLET_RE.match(line)
            if bullet_match:
                headline = bullet_match.group("headline").strip().rstrip(".")
                detail = bullet_match.group("detail").strip()
                current.bullets.append(
                    ChangelogBullet(
                        headline=headline, detail=detail, category=category
                    )
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


def sanitize_detail_for_preview(detail: str, *, max_len: int = _PREVIEW_DETAIL_MAX) -> str:
    """Shorten and de-markdown detail text for the Settings preview."""
    if not detail:
        return ""
    text = _LINK_RE.sub(r"\1", detail)
    text = text.replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1].rsplit(" ", 1)[0]
    if len(cut) < max_len // 2:
        cut = text[: max_len - 1]
    return cut.rstrip(".,;") + "…"


def sanitize_detail_full(detail: str) -> str:
    """De-markdown detail text for the full-notes modal (no truncation)."""
    if not detail:
        return ""
    text = _LINK_RE.sub(r"\1", detail)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def format_bullet_for_preview(bullet: ChangelogBullet) -> dict:
    """Serialize one bullet for the dashboard (truncated detail)."""
    return {
        "headline": bullet.headline,
        "detail": sanitize_detail_for_preview(bullet.detail),
        "category": bullet.category,
    }


def format_bullet_full(bullet: ChangelogBullet) -> dict:
    """Serialize one bullet with its full (un-truncated) detail."""
    return {
        "headline": bullet.headline,
        "detail": sanitize_detail_full(bullet.detail),
        "category": bullet.category,
    }


def format_section_for_preview(section: ChangelogSection) -> dict:
    """Serialize a section with operator-friendly bullets."""
    return {
        "header": section.header,
        "version": section.version,
        "date": section.date,
        "is_unreleased": section.is_unreleased,
        "bullets": [format_bullet_for_preview(b) for b in section.bullets],
    }


def format_section_full(section: ChangelogSection) -> dict:
    """Serialize a section with full-text bullets for the modal."""
    return {
        "header": section.header,
        "version": section.version,
        "date": section.date,
        "is_unreleased": section.is_unreleased,
        "bullets": [format_bullet_full(b) for b in section.bullets],
    }


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        if piece.isdigit():
            parts.append(int(piece))
    return tuple(parts)


def _version_gt(left: str, right: str) -> bool:
    return _version_tuple(left) > _version_tuple(right)


def select_preview_section(
    sections: list[ChangelogSection],
    *,
    tier: str,
    channel_id: str | None = None,
    installed_version: str | None = None,
) -> ChangelogSection | None:
    """Pick the right section for the ``release_notes`` endpoint.

    * ``rc``     -> the version block for this RC channel (e.g.
                    ``rc-075`` -> ``v0.7.5``), else the first
                    versioned section that still has bullets.
                    Skips an empty ``Unreleased`` header.
    * ``stable`` -> the changelog section for ``installed_version``
                    when present, otherwise the newest section that
                    is not newer than the installed firmware (so an
                    in-flight ``v0.7.4`` block does not replace
                    ``v0.7.3.1`` on production gateways).
    * anything else (e.g. ``custom``) -> ``None``; the dashboard
                    renders a generic "no preview available" notice.
    """
    if tier == "rc":
        cid = channel_id or ""
        target = _RC_CHANNEL_VERSION.get(cid)
        if not target:
            target = _RC_CHANNEL_VERSION.get(normalize_channel_id(cid) or "")
        if target:
            for section in sections:
                if section.version == target and section.bullets:
                    return section
            # RC content lives under ``Unreleased`` until the version header
            # is cut; never fall back to an older shipped release (e.g. v0.7.4
            # bullets when the picker already advanced to rc-075).
            for section in sections:
                if section.is_unreleased and section.bullets:
                    return section
            return None
        for section in sections:
            if section.is_unreleased and section.bullets:
                return section
        for section in sections:
            if section.version and section.bullets:
                return section
        return None
    if tier == "stable":
        if installed_version:
            for section in sections:
                if section.version == installed_version:
                    return section
            for section in sections:
                if (
                    section.version
                    and not section.is_unreleased
                    and not _version_gt(section.version, installed_version)
                ):
                    return section
        for section in sections:
            if not section.is_unreleased:
                return section
        return None
    return None
