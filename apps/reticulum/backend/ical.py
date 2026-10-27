"""Fetch an iCalendar feed for the hosted node's ``/page/events.mu``.

Lots of hackerspace wikis publish an ``.ics`` feed of upcoming events
(Semantic MediaWiki's iCal export, Google Calendar, Nextcloud, ...). This
reads one URL and parses the ``VEVENT`` blocks with the stdlib only (no
``icalendar`` package), handing back a short list of *upcoming* events
sorted soonest-first. The node layer does the caching -- this just does
one HTTP GET.

Times are read as the space's local wall clock. A ``Z`` (UTC) suffix is
converted to the node's local time; a ``TZID=`` parameter is ignored and
the value taken as already-local (good enough for the SMW export, which
emits floating times).

FastAPI-free; stdlib ``urllib`` only.
"""

from __future__ import annotations

import datetime as _dt
import logging
import urllib.request

from . import http

logger = logging.getLogger(__name__)

_TIMEOUT_S = 8
_MAX_BYTES = 512 * 1024
_MAX_EVENTS = 12

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fetch(url: str, *, now: _dt.datetime | None = None) -> list[dict] | None:
    """Upcoming events in the iCal feed at *url* -- a list of
    ``{summary, start, end, url, all_day}`` soonest-first, past events
    dropped, capped at ``_MAX_EVENTS``. ``start``/``end`` are naive local
    ``datetime`` (or ``date`` when ``all_day``; ``end`` may be ``None``).

    Returns ``None`` only on a fetch/decode failure -- an empty list is a
    valid "nothing scheduled"."""
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Meshpoint-NomadNet-node"},
        )
        with http.open_request(req, timeout=_TIMEOUT_S) as resp:
            raw = resp.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise ValueError("iCal response too large")
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 -- any failure -> None, page shows a note
        logger.debug("ical request failed")
        return None

    now = now or _dt.datetime.now()
    events: list[dict] = []
    for block in _vevents(_unfold(text)):
        ev = _parse_vevent(block)
        if ev is None:
            continue
        tail = ev["end"] or ev["start"]
        tail_dt = (
            tail if isinstance(tail, _dt.datetime)
            else _dt.datetime.combine(tail, _dt.time.max)
        )
        if tail_dt < now:
            continue
        events.append(ev)
    events.sort(key=lambda e: _sort_key(e["start"]))
    return events[:_MAX_EVENTS]


def format_when(ev: dict) -> str:
    """``Wed 10 Sep  19:30`` (or just the date for an all-day event)."""
    d = ev["start"]
    stamp = f"{_WEEKDAYS[d.weekday()]} {d.day} {_MONTHS[d.month]}"
    if ev.get("all_day") or not isinstance(d, _dt.datetime):
        return stamp
    return f"{stamp}  {d.hour:02d}:{d.minute:02d}"


# --- parsing --------------------------------------------------------------

def _unfold(text: str) -> list[str]:
    """RFC 5545 line unfolding: a line starting with a space or tab
    continues the previous one."""
    out: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _vevents(lines: list[str]):
    cur: list[str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = []
        elif line == "END:VEVENT":
            if cur is not None:
                yield cur
            cur = None
        elif cur is not None:
            cur.append(line)


def _parse_vevent(lines: list[str]) -> dict | None:
    fields: dict[str, tuple[str, str]] = {}
    for line in lines:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = name.split(";", 1)[0].upper()
        params = name[len(key):]
        fields[key] = (params, value)
    if "DTSTART" not in fields or "SUMMARY" not in fields:
        return None
    start = _parse_dt(*fields["DTSTART"])
    if start is None:
        return None
    end = _parse_dt(*fields["DTEND"]) if "DTEND" in fields else None
    return {
        "summary": _untext(fields["SUMMARY"][1]),
        "start": start,
        "end": end,
        "url": _untext(fields["URL"][1]) if "URL" in fields else "",
        "all_day": not isinstance(start, _dt.datetime),
    }


def _parse_dt(params: str, value: str):
    value = value.strip()
    if "VALUE=DATE" in params.upper() or len(value) == 8:
        try:
            return _dt.datetime.strptime(value[:8], "%Y%m%d").date()
        except ValueError:
            return None
    is_utc = value.endswith("Z")
    v = value.rstrip("Z")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            parsed = _dt.datetime.strptime(v, fmt)
        except ValueError:
            continue
        if is_utc:
            parsed = (
                parsed.replace(tzinfo=_dt.timezone.utc)
                .astimezone().replace(tzinfo=None)
            )
        return parsed
    return None


def _untext(v: str) -> str:
    return (
        v.replace("\\n", " ").replace("\\N", " ")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
        .strip()
    )


def _sort_key(d):
    return d if isinstance(d, _dt.datetime) else _dt.datetime.combine(d, _dt.time.min)
