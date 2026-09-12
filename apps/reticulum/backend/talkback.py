"""Plain-text LXMF auto-replies for a handful of commands -- the "talk-back
bot". Gated behind ``talkback_enabled`` (Settings tab), and behind
``node_enabled`` too: every command here answers with data a hosted
NomadNet node already caches for its own ``.mu`` pages (``info.mu``,
``spacestate.mu``, ``events.mu``, ``nodes.mu``), so this is a second,
DM-reachable doorway onto the same numbers rather than a second data path
that could drift from what the pages show.

Pure functions only -- no RNS/LXMF/asyncio imports, nothing here does I/O.
``lxmf_service.py`` supplies already-cached data via ``NomadNode``'s public
snapshot accessors (``stats_snapshot()`` / ``spaceapi_snapshot()`` /
``events_snapshot()``, which trigger the same lazy refresh viewing the
corresponding page would) and calls ``build_reply()`` with the result.

Commands require a leading ``.`` (``.help``, ``.ping``, ...) -- a bare
"ping" or "stats" is common enough as an ordinary word that a human typing
it conversationally shouldn't get an unexpected auto-reply instead of their
actual correspondent. The ``.`` prefix is the same convention IRC/Slack/
Discord bots use for exactly this reason.

Loop-safety note: every reply here is prose that doesn't start with ``.``
at all, so a reply from this bot can never itself be parsed as a new
command -- two Meshpoint nodes with talkback on can't ping-pong each other
indefinitely. ``lxmf_service.py`` still applies a small per-sender cooldown
as defence in depth.
"""

from __future__ import annotations

from typing import Optional

from . import ical

_COMMAND_PREFIX = "."

# Order here is also the order `.help` lists them in.
_COMMANDS = ("help", "ping", "stats", "spacestate", "events", "nodes")


def _display(command: str) -> str:
    return _COMMAND_PREFIX + command


_MAX_EVENTS_IN_REPLY = 5
_MAX_NODES_IN_REPLY = 15


def parse_command(text: str) -> Optional[str]:
    """The first whitespace-delimited word, lowercased and with the leading
    ``.`` stripped, if (and only if) it starts with ``.`` and the remainder
    is one of the recognized commands -- anything else (including a bare
    "help"/"ping" with no dot) is treated as an ordinary DM, not a bot
    query, and gets no reply at all."""
    stripped = (text or "").strip()
    if not stripped or not stripped.startswith(_COMMAND_PREFIX):
        return None
    word = stripped.split(None, 1)[0].lower()[len(_COMMAND_PREFIX):]
    return word if word in _COMMANDS else None


def build_reply(
    command: str,
    *,
    node_name: str,
    stats: dict,
    spaceapi_configured: bool,
    spaceapi: dict,
    events_configured: bool,
    events: list,
) -> str:
    """Dispatch to the one command handler. ``command`` must already be a
    value ``parse_command`` returned (an unrecognized command is the
    caller's job to have filtered out before calling this)."""
    if command == "help":
        return _reply_help(spaceapi_configured, events_configured)
    if command == "ping":
        return "pong"
    if command == "stats":
        return _reply_stats(node_name, stats)
    if command == "spacestate":
        return (
            _reply_spacestate(spaceapi)
            if spaceapi_configured
            else "Space status isn't configured on this node."
        )
    if command == "events":
        return (
            _reply_events(events)
            if events_configured
            else "No events feed is configured on this node."
        )
    if command == "nodes":
        return _reply_nodes(stats.get("recent_nodes") or [])
    raise ValueError(f"unhandled command: {command!r}")  # pragma: no cover -- guarded by parse_command


def _reply_help(spaceapi_configured: bool, events_configured: bool) -> str:
    cmds = ["help", "ping", "stats"]
    if spaceapi_configured:
        cmds.append("spacestate")
    if events_configured:
        cmds.append("events")
    cmds.append("nodes")
    return "Commands: " + ", ".join(_display(c) for c in cmds)


def _reply_stats(node_name: str, stats: dict) -> str:
    lines = [node_name or "Meshpoint"]
    if stats.get("version"):
        lines.append(f"Version: {stats['version']}")
    if stats.get("uptime"):
        lines.append(f"Uptime: {stats['uptime']}")
    if stats.get("reticulum_peers") is not None:
        lines.append(f"Reticulum peers heard: {stats['reticulum_peers']}")
    if stats.get("nomad_nodes") is not None:
        lines.append(f"NomadNet nodes heard: {stats['nomad_nodes']}")
    if stats.get("conversations") is not None:
        lines.append(f"LXMF conversations: {stats['conversations']}")
    return "\n".join(lines)


def _reply_spacestate(spaceapi: dict) -> str:
    state = spaceapi.get("open")
    word = "OPEN" if state is True else "CLOSED" if state is False else "unknown"
    lines = [f"{spaceapi.get('space') or 'Space'}: {word}"]
    if spaceapi.get("message"):
        lines.append(f"Note: {spaceapi['message']}")
    if spaceapi.get("address"):
        lines.append(f"Where: {spaceapi['address']}")
    if not spaceapi:
        lines.append("(status not fetched yet -- try again shortly)")
    return "\n".join(lines)


def _reply_events(events: list) -> str:
    if not events:
        return "No upcoming events."
    lines = ["Upcoming events:"]
    for ev in events[:_MAX_EVENTS_IN_REPLY]:
        summary = ev.get("summary") or "(untitled)"
        lines.append(f"- {ical.format_when(ev)}: {summary}")
    if len(events) > _MAX_EVENTS_IN_REPLY:
        lines.append(f"...and {len(events) - _MAX_EVENTS_IN_REPLY} more.")
    return "\n".join(lines)


def _reply_nodes(recent_nodes: list) -> str:
    if not recent_nodes:
        return "No NomadNet nodes heard yet."
    lines = ["NomadNet nodes heard:"]
    for n in recent_nodes[:_MAX_NODES_IN_REPLY]:
        label = n.get("display_name") or n.get("destination_hash", "")
        lines.append(f"- {label}")
    if len(recent_nodes) > _MAX_NODES_IN_REPLY:
        lines.append(f"...and {len(recent_nodes) - _MAX_NODES_IN_REPLY} more.")
    return "\n".join(lines)
