"""Dedicated process owning the meshtastic-python TCP phone client.

meshtasticd exposes a single-client Phone API (global read cursor). The
meshtastic-python reader thread is also a poor fit inside uvicorn's asyncio
loop. This worker keeps one TCP session in an isolated process, converts
packets to RawCapture in the reader callback, and executes TX on request.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, TypeVar

from src.capture.meshtasticd_bridge_ipc import (
    BridgeCommand,
    BridgeResponse,
    BridgeSendTextRequest,
    fatal_message,
)
from src.capture.meshtasticd_stream_client import (
    LockedTCPInterface,
    force_close_tcp_interface,
)

logger = logging.getLogger(__name__)

_READER_WATCH_INTERVAL_SECONDS = 15.0
_COMMAND_POLL_SECONDS = 0.25
_STALL_RECONNECT_SECONDS = 90.0
_IFACE_OP_TIMEOUT_SECONDS = 25.0
_RECONNECT_CLOSE_TIMEOUT_SECONDS = 5.0
_RECONNECT_TOTAL_TIMEOUT_SECONDS = 30.0

_T = TypeVar("_T")


def run_bridge_worker(
    host: str,
    port: int,
    default_frequency_mhz: float,
    pkt_queue: Any,
    cmd_queue: Any,
    resp_queue: Any,
    sync_settings_dict: dict[str, Any] | None,
) -> None:
    """Entry point for the bridge worker process."""
    logging.basicConfig(level=logging.INFO)
    try:
        _BridgeWorker(
            host=host,
            port=port,
            default_frequency_mhz=default_frequency_mhz,
            pkt_queue=pkt_queue,
            cmd_queue=cmd_queue,
            resp_queue=resp_queue,
            sync_settings_dict=sync_settings_dict,
        ).run()
    except Exception as exc:
        logger.exception("meshtasticd bridge worker failed")
        pkt_queue.put(fatal_message(str(exc)))
        raise SystemExit(1) from exc


class _BridgeWorker:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        default_frequency_mhz: float,
        pkt_queue: Any,
        cmd_queue: Any,
        resp_queue: Any,
        sync_settings_dict: dict[str, Any] | None,
    ) -> None:
        self._host = host
        self._port = port
        self._default_frequency_mhz = default_frequency_mhz
        self._pkt_queue = pkt_queue
        self._cmd_queue = cmd_queue
        self._resp_queue = resp_queue
        self._sync_settings_dict = sync_settings_dict
        self._iface: LockedTCPInterface | None = None
        self._running = True
        self._receive_handler = None
        self._last_packet_at = 0.0
        self._tcp_lock = threading.RLock()
        self._iface_op_in_progress = False

    def run(self) -> None:
        from pubsub import pub

        self._connect_locked_tcp()
        pub.subscribe(self._receive_handler, "meshtastic.receive")
        local_node_hex = self._local_node_id_hex_from_iface(self._iface)
        self._resp_queue.put((BridgeResponse.READY, local_node_hex))
        logger.info(
            "meshtasticd bridge worker connected to %s:%d (local node=%s)",
            self._host,
            self._port,
            local_node_hex or "?",
        )

        watchdog = threading.Thread(
            target=self._watch_health,
            name="meshtasticd-bridge-watchdog",
            daemon=True,
        )
        watchdog.start()

        while self._running:
            try:
                command = self._cmd_queue.get(timeout=_COMMAND_POLL_SECONDS)
            except queue.Empty:
                continue
            self._handle_command(command)

        self._shutdown()

    def _connect_locked_tcp(self) -> None:
        from src.capture.meshtasticd_config_sync import (
            MeshtasticdSyncSettings,
            sync_meshtasticd_config,
        )

        with self._tcp_lock:
            self._receive_handler = self._on_receive
            self._iface = LockedTCPInterface(
                hostname=self._host,
                portNumber=self._port,
                connectNow=True,
            )
            if self._sync_settings_dict is not None:
                settings = MeshtasticdSyncSettings(**self._sync_settings_dict)
                sync_meshtasticd_config(self._iface, settings)
            self._last_packet_at = time.monotonic()

    @staticmethod
    def _local_node_id_hex_from_iface(iface: LockedTCPInterface | None) -> str | None:
        from src.capture.meshtasticd_config_sync import read_local_node_id_hex

        return read_local_node_id_hex(iface) if iface is not None else None

    def _reconnect_tcp(self, reason: str) -> None:
        """Replace the TCP session; must not block indefinitely on close()."""
        from pubsub import pub

        logger.warning("meshtasticd TCP reconnect: %s", reason)
        old_handler = self._receive_handler
        old_iface = self._iface
        self._iface = None

        if old_handler is not None:
            try:
                pub.unsubscribe(old_handler, "meshtastic.receive")
            except Exception:
                pass

        if old_iface is not None:
            try:
                force_close_tcp_interface(
                    old_iface,
                    join_timeout=_RECONNECT_CLOSE_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.debug("meshtasticd bridge close failed", exc_info=True)

        def _connect() -> LockedTCPInterface:
            iface = LockedTCPInterface(
                hostname=self._host,
                portNumber=self._port,
                connectNow=True,
            )
            if self._sync_settings_dict is not None:
                from src.capture.meshtasticd_config_sync import (
                    MeshtasticdSyncSettings,
                    sync_meshtasticd_config,
                )

                settings = MeshtasticdSyncSettings(**self._sync_settings_dict)
                sync_meshtasticd_config(iface, settings)
            return iface

        try:
            new_iface = self._run_timed_op(
                "reconnect_connect",
                _connect,
                timeout=_RECONNECT_TOTAL_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.exception("meshtasticd TCP reconnect failed")
            return

        with self._tcp_lock:
            self._receive_handler = self._on_receive
            self._iface = new_iface
            self._last_packet_at = time.monotonic()
            pub.subscribe(self._receive_handler, "meshtastic.receive")
        logger.info(
            "meshtasticd bridge worker reconnected to %s:%d",
            self._host,
            self._port,
        )

    def _run_timed_op(
        self,
        label: str,
        fn: Callable[[], _T],
        *,
        timeout: float,
    ) -> _T:
        """Run a blocking op with timeout (used for reconnect connect path)."""
        result_box: list[_T | None] = [None]
        error_box: list[BaseException | None] = [None]

        def _target() -> None:
            try:
                result_box[0] = fn()
            except BaseException as exc:
                error_box[0] = exc

        thread = threading.Thread(target=_target, name=f"meshtasticd-{label}")
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise TimeoutError(f"{label} timed out after {timeout:.0f}s")
        if error_box[0] is not None:
            raise error_box[0]
        if result_box[0] is None:
            raise RuntimeError(f"{label} returned no result")
        return result_box[0]

    def _schedule_reconnect(self, reason: str) -> None:
        """Queue reconnect on the command thread (never from the watchdog)."""
        try:
            self._cmd_queue.put_nowait((BridgeCommand.RECONNECT, reason))
        except Exception:
            logger.warning(
                "meshtasticd reconnect not queued (%s); command queue full",
                reason,
            )

    def _run_iface_op(self, label: str, fn: Callable[[], _T]) -> _T | None:
        """Run a blocking meshtastic API call with timeout and TCP recovery."""
        result_box: list[_T | None] = [None]
        error_box: list[BaseException | None] = [None]

        def _target() -> None:
            try:
                result_box[0] = fn()
            except BaseException as exc:
                error_box[0] = exc

        self._iface_op_in_progress = True
        try:
            thread = threading.Thread(target=_target, name=f"meshtasticd-{label}")
            thread.start()
            thread.join(timeout=_IFACE_OP_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.error(
                    "meshtasticd %s timed out after %.0fs; scheduling TCP reconnect",
                    label,
                    _IFACE_OP_TIMEOUT_SECONDS,
                )
                stale = self._iface
                self._iface = None
                if stale is not None:
                    try:
                        force_close_tcp_interface(
                            stale,
                            join_timeout=_RECONNECT_CLOSE_TIMEOUT_SECONDS,
                        )
                    except Exception:
                        logger.debug(
                            "meshtasticd stale iface close failed",
                            exc_info=True,
                        )
                self._schedule_reconnect(f"{label} timed out")
                raise TimeoutError(f"{label} timed out")
            if error_box[0] is not None:
                raise error_box[0]
            return result_box[0]
        finally:
            self._iface_op_in_progress = False

    def _on_receive(self, packet, interface) -> None:
        from src.capture.meshtastic_packet_adapter import packet_dict_to_raw_capture

        if not self._running:
            return
        self._last_packet_at = time.monotonic()
        try:
            raw_capture = packet_dict_to_raw_capture(
                packet,
                capture_source="meshtasticd",
                default_frequency_mhz=self._default_frequency_mhz,
            )
            if raw_capture is not None:
                try:
                    self._pkt_queue.put_nowait(raw_capture)
                except Exception:
                    logger.warning("meshtasticd capture queue full; dropping packet")
        except Exception:
            logger.debug("Failed to convert meshtasticd packet", exc_info=True)

    def _watch_health(self) -> None:
        while self._running:
            time.sleep(_READER_WATCH_INTERVAL_SECONDS)
            iface = self._iface
            if iface is None:
                continue

            rx_thread = getattr(iface, "_rxThread", None)
            if rx_thread is not None and not rx_thread.is_alive():
                self._schedule_reconnect("reader thread exited")
                continue

            idle = time.monotonic() - self._last_packet_at
            if idle >= _STALL_RECONNECT_SECONDS and not self._iface_op_in_progress:
                self._schedule_reconnect(f"no packets for {idle:.0f}s")

    def _handle_command(self, command: tuple[str, Any]) -> None:
        op, payload = command
        if op == BridgeCommand.STOP:
            self._running = False
            return
        if op == BridgeCommand.RECONNECT:
            reason = str(payload or "scheduled")
            self._reconnect_tcp(reason)
            return
        if op == BridgeCommand.SEND_TEXT:
            self._send_text(payload)
            return
        if op in (BridgeCommand.SEND_NODEINFO, BridgeCommand.WRITE_OWNER):
            self._send_nodeinfo(payload)
            return
        if op == BridgeCommand.READ_RADIO_STATE:
            self._read_radio_state()
            return
        if op == BridgeCommand.WRITE_LORA:
            self._write_lora(payload)
            return
        logger.warning("Unknown bridge command: %s", op)

    def _send_text(self, payload: dict[str, Any]) -> None:
        request = BridgeSendTextRequest(**payload)
        iface = self._iface
        if iface is None:
            self._resp_queue.put((BridgeResponse.ERROR, "not connected"))
            return

        def _do_send() -> None:
            iface.sendText(
                request.text,
                destinationId=request.destination,
                wantAck=request.want_ack,
                channelIndex=request.channel,
            )

        try:
            self._run_iface_op("sendText", _do_send)
            logger.info(
                "meshtasticd sendText OK: dest=0x%08x channel=%d len=%d",
                request.destination,
                request.channel,
                len(request.text),
            )
            self._resp_queue.put((BridgeResponse.OK, None))
        except Exception as exc:
            logger.exception("meshtasticd sendText failed")
            self._resp_queue.put((BridgeResponse.ERROR, str(exc)))

    def _send_nodeinfo(self, payload: dict[str, Any]) -> None:
        from src.capture.meshtasticd_control import (
            apply_write_owner,
            parse_write_owner_payload,
        )

        local_node = getattr(self._iface, "localNode", None) if self._iface else None
        if local_node is None:
            self._resp_queue.put((BridgeResponse.ERROR, "not connected"))
            return
        try:
            request = parse_write_owner_payload(payload)

            def _do_owner() -> None:
                apply_write_owner(local_node, request)

            self._run_iface_op("setOwner", _do_owner)
            self._resp_queue.put((BridgeResponse.OK, None))
        except Exception as exc:
            logger.exception("meshtasticd setOwner failed")
            self._resp_queue.put((BridgeResponse.ERROR, str(exc)))

    def _read_radio_state(self) -> None:
        from src.capture.meshtasticd_control import read_radio_state_from_iface

        try:
            state = self._run_iface_op(
                "read_radio_state",
                lambda: read_radio_state_from_iface(self._iface),
            )
            self._resp_queue.put((BridgeResponse.OK, state.to_dict()))
        except Exception as exc:
            logger.exception("meshtasticd read_radio_state failed")
            self._resp_queue.put((BridgeResponse.ERROR, str(exc)))

    def _write_lora(self, payload: dict[str, Any]) -> None:
        from src.capture.meshtasticd_control import (
            apply_write_lora,
            parse_write_lora_payload,
        )

        local_node = getattr(self._iface, "localNode", None) if self._iface else None
        if local_node is None:
            self._resp_queue.put((BridgeResponse.ERROR, "not connected"))
            return
        try:
            parsed = parse_write_lora_payload(payload)

            def _do_lora() -> list[str]:
                return apply_write_lora(local_node, parsed)

            changes = self._run_iface_op("write_lora", _do_lora)
            self._resp_queue.put((BridgeResponse.OK, {"changes": changes}))
        except ValueError as exc:
            self._resp_queue.put((BridgeResponse.ERROR, str(exc)))
        except Exception as exc:
            logger.exception("meshtasticd write_lora failed")
            self._resp_queue.put((BridgeResponse.ERROR, str(exc)))

    def _shutdown(self) -> None:
        if self._receive_handler is not None:
            try:
                from pubsub import pub

                pub.unsubscribe(self._receive_handler, "meshtastic.receive")
            except Exception:
                pass
        if self._iface is not None:
            try:
                force_close_tcp_interface(self._iface)
            except Exception:
                logger.debug("meshtasticd bridge worker close failed", exc_info=True)
            self._iface = None
