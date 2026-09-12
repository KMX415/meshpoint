"""MeshCore message transmission via USB or TCP companion.

Wraps the meshcore Python library for outbound messaging. Shares
the existing MeshCore connection from MeshcoreUsbCaptureSource
to avoid opening a second serial connection to the same port.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from src.transmit.meshcore_channel_sync import MeshcoreChannelSync
from src.transmit.meshcore_contacts import (
    MeshcoreContactCache,
    MeshcoreContactParser,
)

logger = logging.getLogger(__name__)

# Companion firmware caps the advert name at roughly 32 ASCII bytes; the
# exact ceiling varies with location/unicode payload per MeshCore docs.
# We enforce 32 UTF-8 bytes as a conservative upper bound that fits every
# documented variant.
MAX_COMPANION_NAME_BYTES = 32


@dataclass
class SendResult:
    """Outcome of a MeshCore send attempt.

    ``timed_out`` is distinct from a plain ``success=False``: a firmware
    ERROR means the connection is healthy and rejected the request. A
    timeout means no answer within the deadline (wedged command channel).
    Callers / TxClient use this to trigger an immediate reconnect.
    Credit: javastraat/meshpoint b04e91c
    """

    success: bool
    event_type: str = ""
    error: str = ""
    timed_out: bool = False


@dataclass
class RadioStatus:
    """MeshCore companion radio parameters."""

    frequency_mhz: float = 0.0
    bandwidth_khz: float = 0.0
    spreading_factor: int = 0
    coding_rate: int = 0
    tx_power: int = 0
    name: str = ""


class MeshCoreTxClient:
    """Sends messages through a MeshCore companion node.

    Designed to share the MeshCore connection already held by
    MeshcoreUsbCaptureSource. Use set_source() so the client always
    reads the source's *current* MeshCore instance: the capture source
    rebuilds it on every reconnect, and snapshotting the reference
    once at startup leaves the TX client stuck on a dead handle.
    """

    def __init__(self):
        self._owned_mc = None
        self._owned_connected = False
        self._source = None
        self._post_command_callback = None
        # Serialize companion commands: concurrent get_contacts + send
        # on the shared meshcore handle races into send timeouts.
        self._cmd_lock = asyncio.Lock()
        self._contact_cache = MeshcoreContactCache()

    @property
    def _mc(self):
        """Live MeshCore handle. Prefers the shared source if attached."""
        if self._source is not None:
            return getattr(self._source, "_meshcore", None)
        return self._owned_mc

    @property
    def connected(self) -> bool:
        if self._source is not None:
            return (
                bool(getattr(self._source, "_connected", False))
                and self._mc is not None
            )
        return self._owned_connected and self._owned_mc is not None

    def set_source(self, source) -> None:
        """Attach the capture source so we always see live connect state."""
        self._source = source
        bind_lock = getattr(source, "set_command_lock", None)
        if callable(bind_lock):
            bind_lock(self._cmd_lock)
        logger.info("MeshCore TX client bound to live capture source")

    def set_connection(self, mc_instance) -> None:
        """Legacy one-shot attach. Prefer set_source() for live state."""
        self._source = None
        self._owned_mc = mc_instance
        self._owned_connected = mc_instance is not None
        if self._owned_connected:
            logger.info("MeshCore TX client attached to shared connection")

    def set_post_command_callback(self, callback) -> None:
        """Register a coroutine to run after each command completes.

        Used to restart auto_message_fetching on the USB source after
        TX operations that may disrupt the event subscription loop.
        """
        self._post_command_callback = callback

    async def _run_post_command(self) -> None:
        if self._post_command_callback:
            try:
                await self._post_command_callback()
            except Exception:
                logger.debug("Post-command callback failed", exc_info=True)

    def _fail_timeout(self, reason: str) -> SendResult:
        """Mark timeout and kick MeshCore USB reconnect if bound.

        Credit: javastraat/meshpoint b04e91c
        """
        # Cooldown, do not wipe: keep stale names and stop contact
        # fetchers from immediately re-hammering a wedged companion.
        self._contact_cache.note_soft_fail()
        trigger = getattr(self._source, "_trigger_reconnect", None)
        if callable(trigger):
            trigger(reason)
        return SendResult(success=False, error=reason, timed_out=True)

    async def _run_tx_command(
        self,
        factory,
        *,
        success_log: str,
        timeout_label: str,
    ) -> SendResult:
        """Run one companion command under the serial lock.

        Pauses auto message fetching for the command window so the
        library's background poll cannot steal OK/ERROR events
        (same pattern as set_radio).
        """
        if not self.connected:
            return SendResult(success=False, error="Not connected")
        try:
            async with self._cmd_lock:
                if not self.connected or self._mc is None:
                    return SendResult(success=False, error="Not connected")
                await self._pause_auto_fetch()
                try:
                    result = await asyncio.wait_for(factory(), timeout=10.0)
                finally:
                    await self._resume_auto_fetch()
        except asyncio.TimeoutError:
            return self._fail_timeout(timeout_label)
        except Exception as exc:
            logger.exception("%s failed", timeout_label)
            await self._run_post_command()
            return SendResult(success=False, error=str(exc))

        if result is None:
            return self._fail_timeout(timeout_label)

        try:
            from meshcore import EventType
        except Exception:
            EventType = None  # type: ignore[misc, assignment]

        if (
            EventType is not None
            and hasattr(result, "type")
            and result.type == EventType.ERROR
        ):
            payload = getattr(result, "payload", None) or {}
            reason = ""
            if isinstance(payload, dict):
                reason = str(
                    payload.get("reason") or payload.get("error") or ""
                )
            soft = reason in ("no_event_received", "timeout", "")
            if soft:
                return self._fail_timeout(timeout_label)
            await self._run_post_command()
            return SendResult(
                success=False,
                event_type="ERROR",
                error=reason or "companion error",
            )

        event_type = (
            result.type.value
            if hasattr(result.type, "value")
            else str(result.type)
        )
        logger.info("%s: %s", success_log, event_type)
        await self._run_post_command()
        return SendResult(success=True, event_type=event_type)

    async def _pause_auto_fetch(self) -> None:
        mc = self._mc
        if mc is None:
            return
        stop = getattr(mc, "stop_auto_message_fetching", None)
        if not callable(stop):
            return
        try:
            await stop()
        except Exception:
            logger.debug("Could not pause MeshCore auto-fetch", exc_info=True)

    async def _resume_auto_fetch(self) -> None:
        # Prefer the capture-source restart (rebinds subscriptions) when
        # bound; otherwise poke the library directly.
        restart = getattr(self._source, "restart_auto_fetching", None)
        if callable(restart):
            try:
                await restart()
                return
            except Exception:
                logger.debug(
                    "Could not restart MeshCore auto-fetch via source",
                    exc_info=True,
                )
        mc = self._mc
        if mc is None:
            return
        start = getattr(mc, "start_auto_message_fetching", None)
        if not callable(start):
            return
        try:
            await start()
        except Exception:
            logger.debug("Could not resume MeshCore auto-fetch", exc_info=True)

    async def create_connection(
        self,
        port: str,
        baud_rate: int = 115200,
        connection_type: str = "serial",
        tcp_host: str = "",
        tcp_port: int = 0,
    ) -> bool:
        """Create a standalone connection (only if no shared one exists)."""
        if self.connected:
            return True
        try:
            from meshcore import MeshCore

            if connection_type == "tcp" and tcp_host:
                self._owned_mc = await MeshCore.create_tcp(tcp_host, tcp_port)
            else:
                self._owned_mc = await MeshCore.create_serial(port, baud_rate)
            if self._owned_mc is None:
                logger.error(
                    "MeshCore TX client handshake failed on %s "
                    "(meshcore returned None)",
                    port,
                )
                self._owned_connected = False
                return False
            self._source = None
            self._owned_connected = True
            logger.info("MeshCore TX client connected (%s)", connection_type)
            return True
        except Exception:
            logger.exception("MeshCore TX client connection failed")
            self._owned_connected = False
            return False

    async def send_channel_message(
        self, channel: int, text: str
    ) -> SendResult:
        """Send a broadcast message on a MeshCore channel."""
        return await self._run_tx_command(
            lambda: self._mc.commands.send_chan_msg(channel, text),
            success_log=f"MeshCore channel {channel} message sent",
            timeout_label="Send timed out",
        )

    async def send_direct_message(
        self, destination, text: str
    ) -> SendResult:
        """Send a direct message to a MeshCore contact."""
        return await self._run_tx_command(
            lambda: self._mc.commands.send_msg(destination, text),
            success_log="MeshCore DM sent",
            timeout_label="Send timed out",
        )

    async def send_advert(self, flood: bool = False) -> SendResult:
        """Broadcast a node advertisement."""
        return await self._run_tx_command(
            lambda: self._mc.commands.send_advert(flood=flood),
            success_log="MeshCore advert sent",
            timeout_label="Advert timed out",
        )

    async def set_companion_name(self, name: str) -> SendResult:
        """Rename the USB companion via CMD_SET_ADVERT_NAME (0x08).

        On OK we mutate the cached ``self_info["name"]`` so the
        dashboard reflects the rename without waiting for reconnect.
        """
        from src.transmit.meshcore_companion_rename import (
            MeshcoreCompanionRename,
        )

        return await MeshcoreCompanionRename().run(
            mc=self._mc,
            name=name,
            cmd_lock=self._cmd_lock,
            connected=self.connected,
            fail_timeout=self._fail_timeout,
            post_command=self._run_post_command,
        )

    async def set_radio_params(
        self,
        freq: float,
        bw: float,
        sf: int,
        cr: int,
    ) -> SendResult:
        """Set companion radio params, then recover the capture source.

        Prefer exclusive-port apply when bound to MeshCoreUsbCaptureSource
        (cold path matches CLI and works for cross-band changes). Fall
        back to live shared-handle apply only for standalone TX clients.
        Credit: javastraat/meshpoint 471d572
        """
        if self._source is not None:
            from src.transmit.meshcore_exclusive_radio import (
                MeshcoreExclusiveRadioApply,
            )

            freq = round(float(freq), 3)
            bw = round(float(bw), 1)
            return await MeshcoreExclusiveRadioApply().apply_via_source(
                self._source, freq, bw, int(sf), int(cr),
            )

        if not self.connected:
            return SendResult(success=False, error="Not connected")

        from src.transmit.meshcore_radio_apply import (
            MeshcoreRadioApply,
            MeshcoreRadioSetCoordinator,
        )

        freq = round(float(freq), 3)
        bw = round(float(bw), 1)
        sf = int(sf)
        cr = int(cr)
        applier = MeshcoreRadioApply()

        def _trigger(reason: str) -> None:
            trigger = getattr(self._source, "_trigger_reconnect", None)
            if callable(trigger):
                trigger(reason)

        return await MeshcoreRadioSetCoordinator().run(
            apply=lambda f, b, s, c: applier.apply(self._mc, f, b, s, c),
            trigger_reconnect=_trigger,
            wait_connected=self._wait_until_connected,
            get_radio_info=self.get_radio_info,
            freq=freq,
            bw=bw,
            sf=sf,
            cr=cr,
        )

    async def _wait_until_connected(self, timeout_seconds: float) -> bool:
        """Poll live source connect state after a reconnect kick."""
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            if self.connected:
                return True
            await asyncio.sleep(0.5)
        return self.connected

    @staticmethod
    def _normalize_contact_payload(payload) -> list[dict]:
        """Delegate to MeshcoreContactParser (kept for existing tests)."""
        return MeshcoreContactParser.normalize_payload(payload)

    async def get_radio_info(self) -> Optional[RadioStatus]:
        """Read companion radio parameters from the cached SELF_INFO frame.

        SELF_INFO is captured during the handshake and is the authoritative
        source for radio_freq / radio_bw / radio_sf / radio_cr / tx_power /
        name. send_device_query() does not return those fields, so reading
        from there left the dashboard stuck on Unknown / ?.
        """
        if not self.connected:
            return None
        try:
            info = self._mc.self_info or {}
            if not info:
                return None
            return RadioStatus(
                frequency_mhz=float(info.get("radio_freq", 0.0)),
                bandwidth_khz=float(info.get("radio_bw", 0.0)),
                spreading_factor=int(info.get("radio_sf", 0)),
                coding_rate=int(info.get("radio_cr", 0)),
                tx_power=int(info.get("tx_power", 0)),
                name=info.get("name", ""),
            )
        except Exception:
            logger.exception("Failed to read MeshCore radio info")
            return None

    async def get_device_info(self) -> Optional[dict]:
        """Return companion DEVICE_INFO (firmware version / model / build).

        Prefers the capture-source cache (filled on connect before
        auto-fetch starts, refreshed by health checks). Falls back to a
        live ``send_device_query`` under the command lock with auto-fetch
        paused when the cache is empty.
        """
        cached = self._cached_device_info()
        if cached and (cached.get("version") or cached.get("model")):
            return cached

        from src.transmit.meshcore_device_info import MeshcoreDeviceInfoQuery

        if not self.connected:
            return cached
        try:
            async with self._cmd_lock:
                if not self.connected or self._mc is None:
                    return cached
                await self._pause_auto_fetch()
                try:
                    live = await MeshcoreDeviceInfoQuery().run(
                        mc=self._mc,
                        cmd_lock=None,
                        connected=True,
                    )
                finally:
                    await self._resume_auto_fetch()
            if live:
                self._store_device_info_cache(live)
                return live
        except Exception:
            logger.exception("MeshCore get_device_info failed")
        finally:
            await self._run_post_command()
        return cached

    def _cached_device_info(self) -> Optional[dict]:
        source = self._source
        if source is None:
            return None
        info = getattr(source, "last_device_info", None)
        return info if isinstance(info, dict) else None

    def _store_device_info_cache(self, info: dict) -> None:
        source = self._source
        if source is None:
            return
        try:
            source._last_device_info = info
        except Exception:
            logger.debug("Could not store MeshCore DEVICE_INFO cache", exc_info=True)

    async def sync_channels(self, channel_keys: dict) -> None:
        """Sync configured channels to the companion device."""
        if not self.connected:
            logger.debug("sync_channels: not connected, skipping")
            return
        async with self._cmd_lock:
            if not self.connected or self._mc is None:
                return
            await self._pause_auto_fetch()
            try:
                await MeshcoreChannelSync(
                    self._mc,
                    post_command=None,
                ).sync(channel_keys)
            finally:
                await self._resume_auto_fetch()
            await self._run_post_command()

    async def get_contacts(self, *, force: bool = False) -> list[dict]:
        """Retrieve the companion's contact list.

        Uses a short TTL cache so Messages UI / contact picker can call
        this without saturating the serial command channel. Live fetches
        take the same lock as sends so they cannot race a channel TX.
        """
        if not force:
            cached = self._contact_cache.get_fresh()
            if cached is not None:
                return cached

        if not self.connected:
            return self._contact_cache.get_stale()

        try:
            async with self._cmd_lock:
                if not force:
                    cached = self._contact_cache.get_fresh()
                    if cached is not None:
                        return cached
                if not self.connected or self._mc is None:
                    return self._contact_cache.get_stale()
                result = await asyncio.wait_for(
                    self._mc.commands.get_contacts(),
                    timeout=10.0,
                )
        except asyncio.TimeoutError:
            logger.warning("get_contacts timed out waiting for companion")
            self._contact_cache.note_soft_fail()
            return self._contact_cache.get_stale()
        except Exception:
            logger.exception("Failed to retrieve MeshCore contacts")
            self._contact_cache.note_soft_fail()
            return self._contact_cache.get_stale()

        contacts = MeshcoreContactParser.from_command_result(result)
        soft_fail = result is None or MeshcoreContactParser._is_error_event(
            result
        )
        if soft_fail:
            # Stamp TTL even on failure so queued callers do not each
            # burn another live 5s get_contacts on a wedged companion.
            self._contact_cache.note_soft_fail()
            stale = self._contact_cache.get_stale()
            if stale:
                logger.info(
                    "get_contacts: soft fail, using stale cache (%d)",
                    len(stale),
                )
                return stale
            logger.info("get_contacts: soft fail, empty roster (cooling down)")
            return []
        self._contact_cache.store(contacts)
        logger.info("get_contacts: %d contacts parsed", len(contacts))
        return contacts
