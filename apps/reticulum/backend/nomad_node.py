"""Host a NomadNet node -- serve Micron pages over Reticulum.

Registered on the **same RNS Identity** as ``LxmfService``'s
``lxmf.delivery`` destination, so this Meshpoint appears on the network as
both "message me" (LXMF) and "browse me" (``nomadnetwork.node``) on one
hash -- exactly how a NomadNet user with a hosted node appears.

Opt-in (``plugins.reticulum.node_enabled``, off by default). Serves:
  * ``/page/index.mu``  -- generated: a branding/landing page (a blue
    figlet ``MESHPOINT`` banner, node name, a short "what is Meshpoint"
    blurb) linking to ``info.mu``. An operator ``index.mu`` in
    ``node_pages_dir`` overrides it entirely.
  * ``/page/info.mu``   -- generated, **always served** regardless of an
    operator's ``index.mu`` -- a same-named file dropped in
    ``node_pages_dir`` is ignored, so any custom ``index.mu`` can safely
    link to ``:/page/info.mu``. Shows version/uptime/peer counts, a
    ``>Host`` block (board, CPU temp, load, memory, free disk -- all
    non-sensitive) and a ``>Mesh activity`` block (aggregate packet counts
    + a per-protocol split -- deliberately **nothing node-level**, the page
    is public on the Reticulum network). The GitHub link is derived from
    this checkout's ``git`` origin (``src.remote.repo_source``).
  * ``/page/nodes.mu``  -- generated: the other ``nomadnetwork.node``
    peers this Meshpoint has heard.
  * ``/page/spacestate.mu`` / ``/page/events.mu`` -- generated, and only
    registered when ``node_spaceapi_url`` / ``node_events_ical_url`` is set
    (hackerspace open/closed status, upcoming calendar events).
  * ``/page/<name>.mu`` -- any other ``.mu`` file the operator drops in
    ``node_pages_dir``.
  * ``/file/<path>``    -- any file under ``node_pages_dir/files/``.

RNS matches request handlers by exact path (one per file), so there's no
traversal surface -- new files need a restart to be registered.

Mechanics ported in spirit from NomadNet's own ``nomadnet/Node.py`` (Mark
Qvist, markqvist/NomadNet, MIT).
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from . import ical, spaceapi

logger = logging.getLogger(__name__)

try:
    import RNS
except ImportError:
    RNS = None

_STATS_REFRESH_S = 60  # info.mu shows CPU temp / load / 24h counts -- keep it fresh
_SPACEAPI_TTL_S = 120  # serve the cached status within this; refresh lazily when older
_EVENTS_TTL_S = 900  # events.mu -- agenda barely moves; 15 min cache, still lazy

# Token an operator can drop into any of their own .mu pages -- replaced at
# serve time with a colour-coded OPEN / CLOSED / unknown word (only when a
# SpaceAPI URL is configured). See _make_file_server / _spaceapi_word.
_SPACESTATE_TOKEN = b"{spacestate}"

# .mu names the node generates itself -- an operator file with one of these
# names is ignored (never registered, not counted as a page).
_GENERATED_PAGES = frozenset({"index.mu", "info.mu", "nodes.mu", "spacestate.mu", "events.mu"})

# figlet "standard" MESHPOINT, 53 cols, no backticks. Emitted raw (never
# through _esc -- Micron renders "\" literally, and _esc would double it).
# LEFT-ALIGNED on purpose: Micron's `c centres each line independently, so
# a `c'd multi-line block fragments (this is why the old one-line wordmark
# existed). `F38f == #3388ff, the dashboard's accent blue.
_MESHPOINT_BANNER = (
    r" __  __ _____ ____  _   _ ____   ___ ___ _   _ _____",
    r"|  \/  | ____/ ___|| | | |  _ \ / _ \_ _| \ | |_   _|",
    r"| |\/| |  _| \___ \| |_| | |_) | | | | ||  \| | | |",
    r"| |  | | |___ ___) |  _  |  __/| |_| | || |\  | | |",
    r"|_|  |_|_____|____/|_| |_|_|    \___/___|_| \_| |_|",
)


def _esc(s: str) -> str:
    """Micron has no escaping need for plain text except the backtick."""
    return str(s).replace("\\", "\\\\").replace("`", "\\`")


def _fmt_ago(seconds: int) -> str:
    seconds = max(0, seconds)
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


class NomadNode:
    def __init__(
        self,
        identity,
        name: str,
        pages_dir: str,
        announce_interval_s: int,
        stats_provider: Optional[Callable[[], Awaitable[dict]]] = None,
        hardware_description: str = "",
        project_url: str = "https://github.com/KMX415/meshpoint",
        spaceapi_url: str = "",
        events_ical_url: str = "",
    ):
        self._identity = identity
        self._name = name
        self._pages_dir = Path(pages_dir)
        self._announce_interval_s = max(600, int(announce_interval_s))
        self._stats_provider = stats_provider
        self._hardware_description = hardware_description
        self._project_url = project_url
        self._spaceapi_url = spaceapi_url
        self._events_ical_url = events_ical_url

        self._destination = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._announce_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None
        self._stats: dict = {}
        self._spaceapi: dict = {}  # last good SpaceAPI fetch, {} until one lands
        self._spaceapi_fetched_at = 0.0  # monotonic; 0 = never
        self._spaceapi_refreshing = False
        self._events: list = []  # last good iCal fetch (may legitimately be [])
        self._events_fetched_at = 0.0  # monotonic; 0 = never
        self._events_refreshing = False
        self._last_announce: Optional[float] = None
        self._requests_served = 0

    # --- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if RNS is None or self._identity is None:
            logger.warning("NomadNet node: RNS/identity not available -- not starting")
            return

        self._destination = RNS.Destination(
            self._identity, RNS.Destination.IN, RNS.Destination.SINGLE,
            "nomadnetwork", "node",
        )
        self._destination.set_link_established_callback(self._on_link)
        self._loop = asyncio.get_running_loop()
        self._register_handlers()

        if self._stats_provider is not None:
            await self._refresh_stats()
            self._stats_task = asyncio.get_running_loop().create_task(self._stats_loop())

        if self._spaceapi_url:
            # One priming fetch so the first visitor sees a real status; after
            # that it's refreshed lazily, only when a page that needs it is
            # actually requested (see _spaceapi_maybe_refresh) -- no timer.
            await self._refresh_spaceapi()
        if self._events_ical_url:
            await self._refresh_events()  # prime; then lazy, same as spacestate

        self._announce()
        self._announce_task = asyncio.get_running_loop().create_task(self._announce_loop())
        logger.info(
            "NomadNet node hosting as %r (announce every %ds)",
            self._name, self._announce_interval_s,
        )

    async def stop(self) -> None:
        for task in (self._announce_task, self._stats_task):
            if task:
                task.cancel()
        self._announce_task = self._stats_task = None
        self._destination = None
        self._loop = None

    @property
    def name(self) -> str:
        return self._name

    def status(self) -> dict:
        return {
            "hosting": self._destination is not None,
            "name": self._name,
            "pages": self._page_count(),
            "requests_served": self._requests_served,
            "last_announce_s_ago": (
                None if self._last_announce is None
                else int(time.monotonic() - self._last_announce)
            ),
        }

    # --- plain-text snapshots (talkback.py; anything wanting this data
    # without going through Micron-formatted .mu output) --------------------

    @property
    def spaceapi_configured(self) -> bool:
        return bool(self._spaceapi_url)

    @property
    def events_configured(self) -> bool:
        return bool(self._events_ical_url)

    def stats_snapshot(self) -> dict:
        """The same dict ``_serve_info``/``_serve_nodes`` read from --
        already plain data, no Micron formatting to strip."""
        return dict(self._stats or {})

    def spaceapi_snapshot(self) -> dict:
        """Triggers the same lazy refresh viewing ``spacestate.mu`` would,
        then returns the cached SpaceAPI dict."""
        self._spaceapi_maybe_refresh()
        return dict(self._spaceapi or {})

    def events_snapshot(self) -> list:
        """Triggers the same lazy refresh viewing ``events.mu`` would, then
        returns the cached event list."""
        self._events_maybe_refresh()
        return list(self._events)

    # --- RNS wiring -------------------------------------------------------

    def _on_link(self, link) -> None:
        try:
            link.set_resource_strategy(RNS.Link.ACCEPT_ALL)
        except Exception:  # noqa: BLE001 -- older RNS may not need it
            pass

    def _register_handlers(self) -> None:
        d = self._destination
        pages = self._pages_dir

        op_index = pages / "index.mu"
        d.register_request_handler(
            "/page/index.mu",
            response_generator=(
                self._make_file_server(op_index) if op_index.exists()
                else self._serve_index
            ),
            allow=RNS.Destination.ALLOW_ALL,
        )
        d.register_request_handler(
            "/page/info.mu",
            response_generator=self._serve_info,
            allow=RNS.Destination.ALLOW_ALL,
        )
        d.register_request_handler(
            "/page/nodes.mu",
            response_generator=self._serve_nodes,
            allow=RNS.Destination.ALLOW_ALL,
        )
        if self._spaceapi_url:
            d.register_request_handler(
                "/page/spacestate.mu",
                response_generator=self._serve_spacestate,
                allow=RNS.Destination.ALLOW_ALL,
            )
        if self._events_ical_url:
            d.register_request_handler(
                "/page/events.mu",
                response_generator=self._serve_events,
                allow=RNS.Destination.ALLOW_ALL,
            )

        if pages.is_dir():
            for p in sorted(pages.glob("*.mu")):
                if p.name in _GENERATED_PAGES:
                    continue
                d.register_request_handler(
                    f"/page/{p.name}",
                    response_generator=self._make_file_server(p),
                    allow=RNS.Destination.ALLOW_ALL,
                )
            files_dir = pages / "files"
            if files_dir.is_dir():
                for p in sorted(files_dir.rglob("*")):
                    if p.is_file():
                        rel = p.relative_to(files_dir).as_posix()
                        d.register_request_handler(
                            f"/file/{rel}",
                            response_generator=self._make_file_server(p, is_file=True),
                            allow=RNS.Destination.ALLOW_ALL,
                        )

    def reload_pages(self) -> None:
        """Re-scan ``node_pages_dir`` and (re-)register a request handler
        per ``.mu`` file -- so a page created or edited through the
        dashboard's Pages tab is served without a plugin restart.

        Editing an *existing* file's content is already live (each request
        re-``read_bytes()``s -- see ``_make_file_server``); this is what a
        *new* file needs. A *deleted* file's handler stays registered and
        just starts returning "Not found" (RNS has no clean unregister) --
        harmless, and a real restart clears it.
        """
        if self._destination is not None:
            self._register_handlers()

    def _page_count(self) -> int:
        n = 3  # index (generated or overridden) + info + nodes (both fixed generated)
        if self._spaceapi_url:
            n += 1  # /page/spacestate.mu
        if self._events_ical_url:
            n += 1  # /page/events.mu
        if self._pages_dir.is_dir():
            n += sum(
                1 for p in self._pages_dir.glob("*.mu")
                if p.name not in _GENERATED_PAGES
            )
        return n

    # --- announce ------------------------------------------------------

    def announce(self) -> None:
        """Re-send the ``nomadnetwork.node`` announce on demand (the
        Reticulum page's Announce button), so a browsing client learns
        our node hash without waiting for the next automatic one."""
        if self._destination is not None:
            self._announce()

    def _announce(self) -> None:
        try:
            self._destination.announce(app_data=self._name.encode("utf-8"))
            self._last_announce = time.monotonic()
        except Exception:  # noqa: BLE001
            logger.exception("NomadNet node announce failed")

    async def _announce_loop(self) -> None:
        while True:
            await asyncio.sleep(self._announce_interval_s)
            self._announce()

    async def _stats_loop(self) -> None:
        while True:
            await asyncio.sleep(_STATS_REFRESH_S)
            await self._refresh_stats()

    async def _refresh_stats(self) -> None:
        try:
            self._stats = await self._stats_provider() or {}
        except Exception:  # noqa: BLE001
            logger.debug("NomadNet node stats refresh failed", exc_info=True)

    def _spaceapi_maybe_refresh(self) -> None:
        """Called from an RNS request thread. If the cached SpaceAPI status is
        missing or older than ``_SPACEAPI_TTL_S``, kick a background refresh on
        the event loop and return immediately -- the request in hand is always
        served from cache, never blocked on the HTTP fetch. If nobody browses a
        page that needs the status, we never poll the endpoint at all."""
        if not self._spaceapi_url or self._spaceapi_refreshing or self._loop is None:
            return
        age = time.monotonic() - self._spaceapi_fetched_at
        if self._spaceapi and age < _SPACEAPI_TTL_S:
            return
        self._spaceapi_refreshing = True
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self._refresh_spaceapi())
        )

    async def _refresh_spaceapi(self) -> None:
        try:
            # spaceapi.fetch is a blocking urllib call -- off the event loop.
            result = await asyncio.to_thread(spaceapi.fetch, self._spaceapi_url)
            if result:  # keep the last good one on a failed / partial fetch
                self._spaceapi = result
        except Exception:  # noqa: BLE001
            logger.debug("SpaceAPI refresh failed", exc_info=True)
        finally:
            # Stamp even on failure so a flapping endpoint isn't hammered every
            # request -- we retry no sooner than one TTL from now.
            self._spaceapi_fetched_at = time.monotonic()
            self._spaceapi_refreshing = False

    def _events_maybe_refresh(self) -> None:
        """Lazy refresh, same contract as ``_spaceapi_maybe_refresh``: called
        from an RNS request thread, kicks a background fetch when the cached
        agenda is missing/stale and returns at once -- never blocks the page."""
        if not self._events_ical_url or self._events_refreshing or self._loop is None:
            return
        age = time.monotonic() - self._events_fetched_at
        if self._events_fetched_at and age < _EVENTS_TTL_S:
            return
        self._events_refreshing = True
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self._refresh_events())
        )

    async def _refresh_events(self) -> None:
        try:
            result = await asyncio.to_thread(ical.fetch, self._events_ical_url)
            if result is not None:  # [] is a valid "nothing scheduled"
                self._events = result
        except Exception:  # noqa: BLE001
            logger.debug("iCal refresh failed", exc_info=True)
        finally:
            self._events_fetched_at = time.monotonic()
            self._events_refreshing = False

    def _spaceapi_word(self) -> str:
        """Colour-coded OPEN / CLOSED / unknown, as a Micron fragment."""
        state = (self._spaceapi or {}).get("open")
        if state is True:
            return "`F0a0`!OPEN`!`f"
        if state is False:
            return "`Fd44`!CLOSED`!`f"
        return "`F888unknown`f"

    # --- request handlers (called on RNS's thread; return bytes) --------

    def _make_file_server(self, path: Path, is_file: bool = False):
        def _serve(request_path, data, request_id, link_id, remote_identity, requested_at):
            self._requests_served += 1
            try:
                if path.is_symlink() or self._pages_dir.resolve() not in path.resolve().parents:
                    return b"`!Not found`!"
                body = path.read_bytes()
            except OSError:
                return b"`!Not found`!"
            # Light template pass on .mu pages: {spacestate} -> live word.
            if (
                not is_file and self._spaceapi_url
                and _SPACESTATE_TOKEN in body
            ):
                self._spaceapi_maybe_refresh()
                body = body.replace(
                    _SPACESTATE_TOKEN, self._spaceapi_word().encode("utf-8"),
                )
            return body
        return _serve

    def _serve_index(self, request_path, data, request_id, link_id, remote_identity, requested_at):
        """Default landing page -- a short "what is this" plus a link to
        the always-on stats page. An operator's own ``index.mu`` in
        ``node_pages_dir`` replaces this entirely (see ``sample-pages/``)."""
        self._requests_served += 1
        on_hardware = f" on {_esc(self._hardware_description)}" if self._hardware_description else ""
        lines = [
            "`F38f",
            *_MESHPOINT_BANNER,
            "`f",
            "`F888Node`f    : `F0a0`!" + _esc(self._name) + "`!`f",
        ]
        addr = self._address_hex()
        if addr:
            # the nomadnetwork.node hash -- what a visitor pastes as
            # "<hash>:/page/x.mu" to reach us; LXMF delivery is a separate
            # aspect hash on the same identity.
            lines.append("`F888Address`f : " + addr)
        lines += [
            "-",
            "",
            "This node runs `!Meshpoint`!" + on_hardware + ". Its optional Reticulum",
            "plugin hosts this NomadNet page on the `!same identity`! as",
            "its LXMF address, announcing itself as `!nomadnetwork.node`!.",
            "",
        ]
        if addr:
            lines += [
                "The Address above is for browsing; LXMF messaging uses a",
                "separate hash on the same identity.",
                "",
            ]
        lines += [
            "You can browse this node here and message it over LXMF.",
            "",
            ">Links",
            "`[Host, mesh & Reticulum stats`:/page/info.mu]",
            f"`[Meshpoint on GitHub`{self._project_url}]",
        ]
        return ("\n".join(lines)).encode("utf-8")

    def _project_label(self) -> str:
        return self._project_url.split("://", 1)[-1].rstrip("/")

    def _address_hex(self) -> str:
        """This node's ``nomadnetwork.node`` destination hash as lowercase
        hex, or ``""`` before the destination exists (tests, pre-start)."""
        try:
            return self._destination.hash.hex()
        except (AttributeError, TypeError):
            return ""

    def _serve_info(self, request_path, data, request_id, link_id, remote_identity, requested_at):
        """Fixed stats page -- always generated, never overridable by an
        operator's ``node_pages_dir`` (a same-named file there is ignored
        by ``_register_handlers``), so any custom ``index.mu`` can safely
        link to ``:/page/info.mu`` and always get live numbers."""
        self._requests_served += 1
        s = self._stats
        host = s.get("host") or {}
        mesh = s.get("mesh") or {}

        def row(label, value):
            return f"{label:<22}: {value}"

        lines = [
            "`c`F0a0`!" + _esc(self._name) + "`!`f`a",
            "`ca Meshpoint node`a",
            "-",
            ">Meshpoint",
        ]
        if s.get("version"):
            lines.append(row("Version", _esc(s["version"])))
        if s.get("uptime"):
            lines.append(row("Uptime", _esc(s["uptime"])))
        if s.get("hardware"):
            lines.append(row("Hardware", _esc(s["hardware"])))
        if s.get("reticulum_peers") is not None:
            lines.append(row("Reticulum peers heard", s["reticulum_peers"]))
        if s.get("nomad_nodes") is not None:
            lines.append(row("NomadNet nodes heard", s["nomad_nodes"]))
        if s.get("conversations") is not None:
            lines.append(row("LXMF conversations", s["conversations"]))

        # Host health -- non-sensitive (temp / load / free space), best-effort.
        host_rows = []
        if host.get("pi_model"):
            host_rows.append(row("Board", _esc(host["pi_model"])))
        if host.get("cpu_temp_c") is not None:
            host_rows.append(row("CPU temp", f"{host['cpu_temp_c']} C"))
        if host.get("load_1m") is not None:
            host_rows.append(row("Load (1m)", host["load_1m"]))
        if host.get("mem_total_mb"):
            host_rows.append(row("Memory", f"{host['mem_used_mb']} / {host['mem_total_mb']} MB"))
        if host.get("disk_total_gb"):
            host_rows.append(row("Disk free", f"{host['disk_free_gb']} / {host['disk_total_gb']} GB"))
        if host_rows:
            lines += ["", ">Host", *host_rows]

        # Mesh activity -- aggregate counts only, deliberately nothing
        # node-level (this page is public on the Reticulum network).
        if mesh:
            lines += ["", ">Mesh activity"]
            if mesh.get("packets_total") is not None:
                lines.append(row("Packets seen", f"{mesh['packets_total']:,}"))
            if mesh.get("packets_24h") is not None:
                lines.append(row("  last 24h", f"{mesh['packets_24h']:,}"))
            for proto, cnt in sorted(
                (mesh.get("by_protocol") or {}).items(), key=lambda kv: -kv[1],
            ):
                lines.append(row(f"  {_esc(proto)}", f"{cnt:,}"))

        lines += [
            "",
            ">Pages",
            "`[Nodes this Meshpoint has heard`:/page/nodes.mu]",
            "`[Home`:/page/index.mu]",
            "",
            ">About Meshpoint",
            "A mesh gateway and dashboard for Meshtastic and MeshCore,",
            "with optional Reticulum and receiver plugins.",
            f"`[{_esc(self._project_label())}`{self._project_url}]",
        ]
        return ("\n".join(lines)).encode("utf-8")

    def _serve_spacestate(self, request_path, data, request_id, link_id, remote_identity, requested_at):
        """Hackerspace status from the configured SpaceAPI endpoint -- only
        registered when ``node_spaceapi_url`` is set. Served from the cached
        last-good fetch; viewing this page is what triggers a lazy refresh
        (``_spaceapi_maybe_refresh``), so a stale value here self-heals on the
        next load."""
        self._requests_served += 1
        self._spaceapi_maybe_refresh()
        s = self._spaceapi or {}
        name = _esc(s.get("space") or "This space")

        def row(label, value):
            return f"{label:<10}: {value}"

        lines = [
            "`c`F0a0`!" + name + "`!`f`a",
            "`ca space status`a",
            "-",
            "Status    : " + self._spaceapi_word(),
        ]
        if s.get("message"):
            lines.append(row("Note", _esc(s["message"])))
        if s.get("lastchange"):
            ago = int(time.time()) - int(s["lastchange"])
            lines.append(row("Changed", _fmt_ago(ago) + " ago"))
        if s.get("address"):
            lines.append(row("Where", _esc(s["address"])))
        contact = [
            ("Web", s.get("url"), True),
            ("IRC", s.get("irc"), False),
            ("E-mail", s.get("email"), False),
            ("List", s.get("ml"), False),
        ]
        contact_rows = [
            row(lbl, f"`[{_esc(val)}`{val}]" if is_url and val.startswith("http") else _esc(val))
            for lbl, val, is_url in contact if val
        ]
        if contact_rows:
            lines += ["", ">Contact", *contact_rows]
        if not s:
            lines.append("")
            lines.append("(status not fetched yet -- try again shortly)")
        # Cross-link to the sibling generated page only when it's actually
        # registered (node_events_ical_url set) -- never a hardcoded jump
        # into an operator's own custom pages (e.g. sample-bbs-techinc's
        # meshpoint.mu), since this handler is shared by every hosted node
        # and most won't have a page by that name.
        nav = "`[Home`:/page/index.mu]"
        if self._events_ical_url:
            nav += "     `[Upcoming events >>`:/page/events.mu]"
        lines += ["", nav]
        return ("\n".join(lines)).encode("utf-8")

    def _serve_events(self, request_path, data, request_id, link_id, remote_identity, requested_at):
        """Upcoming events from the configured iCal feed -- only registered
        when ``node_events_ical_url`` is set. Served from the cached last-good
        fetch; viewing the page is what triggers a lazy refresh, so a stale
        agenda self-heals on the next load."""
        self._requests_served += 1
        fetched = self._events_fetched_at > 0
        self._events_maybe_refresh()
        lines = [
            "`c`F0a0`!Upcoming events`!`f`a",
            "`c" + _esc(self._name) + "`a",
            "-",
        ]
        if not self._events:
            lines.append(
                "(nothing scheduled)" if fetched
                else "(not fetched yet -- try again shortly)"
            )
        for ev in self._events:
            summary = _esc(ev.get("summary") or "") or "(untitled)"
            url = ev.get("url") or ""
            lines.append("")
            lines.append("`F888" + _esc(ical.format_when(ev)) + "`f")
            lines.append(
                f"`[{summary}`{url}]" if url.startswith("http") else summary
            )
        # Same sibling-only cross-link as _serve_spacestate, mirrored.
        nav = "`[Home`:/page/index.mu]"
        if self._spaceapi_url:
            nav += "     `[Space status >>`:/page/spacestate.mu]"
        lines += ["", nav]
        return ("\n".join(lines)).encode("utf-8")

    def _serve_nodes(self, request_path, data, request_id, link_id, remote_identity, requested_at):
        self._requests_served += 1
        nodes = self._stats.get("recent_nodes") or []
        lines = [
            "`c`F0a0`!NomadNet nodes " + _esc(self._name) + " has heard`!`f`a",
            "-",
        ]
        if not nodes:
            lines.append("(none yet -- this Meshpoint hasn't heard a nomadnetwork.node announce)")
        for n in nodes[:100]:
            label = _esc(n.get("display_name") or n.get("destination_hash", ""))
            dh = n.get("destination_hash", "")
            lines.append(f"`[{label}`{dh}:/page/index.mu]")
        # info.mu already links here; close the loop back the other way.
        # Both always generated/registered unconditionally, so no config
        # gate needed (unlike the spacestate/events cross-links above).
        lines += ["", "`[Home`:/page/index.mu]     `[Live node stats >>`:/page/info.mu]"]
        return ("\n".join(lines)).encode("utf-8")
