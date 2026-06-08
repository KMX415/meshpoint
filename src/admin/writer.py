"""Remote Meshtastic ADMIN config write (limited fields, PR 16)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from meshtastic.protobuf import admin_pb2, config_pb2, module_config_pb2

from src.admin.reader import AdminConfigError, AdminConfigReader
from src.admin.write_store import WRITE_DEBOUNCE_SECONDS, WriteOperationStore
from src.relay.node_id import validate_node_ids
from src.transmit.tx_service import TxService

logger = logging.getLogger(__name__)

ROLE_CONFIRM_TOKEN = "CONFIRM"

_ALLOWED_ROLES = {
    config_pb2.Config.DeviceConfig.Role.CLIENT,
    config_pb2.Config.DeviceConfig.Role.CLIENT_MUTE,
    config_pb2.Config.DeviceConfig.Role.ROUTER,
    config_pb2.Config.DeviceConfig.Role.ROUTER_CLIENT,
    config_pb2.Config.DeviceConfig.Role.REPEATER,
    config_pb2.Config.DeviceConfig.Role.TRACKER,
    config_pb2.Config.DeviceConfig.Role.SENSOR,
}

_VERIFY_POLL_INTERVAL = 2.0
_VERIFY_TIMEOUT = 30.0
_POST_WRITE_DELAY = 2.0


class AdminConfigWriter:
    """Apply a small allow-listed set of remote config changes via ADMIN TX."""

    def __init__(
        self,
        *,
        reader: AdminConfigReader,
        tx_service: TxService | None,
        write_store: WriteOperationStore | None = None,
    ) -> None:
        self._reader = reader
        self._tx = tx_service
        self._writes = write_store or WriteOperationStore()

    @property
    def store(self) -> WriteOperationStore:
        return self._writes

    def get_status(self, node_id: str) -> dict[str, Any]:
        from src.relay.node_id import normalize_node_id

        normalized = normalize_node_id(node_id)
        state = self._writes.get(normalized)
        if state is None or state.status == "idle":
            return {
                "node_id": normalized,
                "status": "idle",
                "operation_id": "",
                "changes": None,
                "verify_result": None,
                "error": "",
                "debounce_seconds": WRITE_DEBOUNCE_SECONDS,
            }
        return {
            "node_id": state.node_id,
            "operation_id": state.operation_id,
            "status": state.status,
            "changes": state.changes,
            "packets_sent": state.packets_sent,
            "verify_sections": state.verify_sections,
            "verify_result": state.verify_result,
            "error": state.error,
            "started_at": state.started_at,
            "completed_at": state.completed_at or None,
            "debounce_seconds": WRITE_DEBOUNCE_SECONDS,
        }

    async def apply_changes(
        self,
        node_id: str,
        *,
        long_name: str | None = None,
        short_name: str | None = None,
        role: int | None = None,
        role_confirm: str | None = None,
        screen_on_secs: int | None = None,
        telemetry_interval_secs: int | None = None,
    ) -> dict[str, Any]:
        self._ensure_available()
        normalized = validate_node_ids([node_id])[0]
        dest_int = int(normalized, 16)
        if dest_int in (0, 0xFFFFFFFF):
            raise AdminConfigError(
                "Cannot write config to broadcast node",
                status_code=400,
            )

        changes, verify_sections, messages = self._validate_and_build_messages(
            long_name=long_name,
            short_name=short_name,
            role=role,
            role_confirm=role_confirm,
            screen_on_secs=screen_on_secs,
            telemetry_interval_secs=telemetry_interval_secs,
        )

        ok, reason = self._writes.can_write(normalized)
        if not ok:
            raise AdminConfigError(reason, status_code=429)

        state = self._writes.begin(
            normalized,
            changes=changes,
            verify_sections=verify_sections,
        )

        packet_ids: list[str] = []
        try:
            for label, admin_msg in messages:
                result = await self._reader.send_admin_to_node(
                    normalized, admin_msg
                )
                packet_ids.append(result.packet_id)
                logger.info(
                    "ADMIN write %s to %s packet_id=%s",
                    label,
                    normalized,
                    result.packet_id,
                )

            self._writes.mark_verifying(normalized, packet_ids)
            asyncio.create_task(
                self._verify_after_write(normalized, verify_sections)
            )
            return self.get_status(normalized)
        except AdminConfigError:
            self._writes.fail(normalized, "ADMIN write failed")
            raise
        except Exception as exc:
            self._writes.fail(normalized, str(exc))
            raise AdminConfigError(str(exc), status_code=502) from exc

    async def _verify_after_write(
        self,
        node_id: str,
        sections: list[str],
    ) -> None:
        await asyncio.sleep(_POST_WRITE_DELAY)
        combined: dict[str, Any] = {}
        try:
            for section in sections:
                await self._reader.request_config(
                    node_id, section=section, skip_debounce=True
                )
                deadline = time.monotonic() + _VERIFY_TIMEOUT
                while time.monotonic() < deadline:
                    status = self._reader.get_status(node_id)
                    if status["status"] == "complete":
                        combined[section] = status.get("config")
                        break
                    if status["status"] in ("timeout", "error"):
                        break
                    await asyncio.sleep(_VERIFY_POLL_INTERVAL)
                else:
                    self._writes.verify_timeout(node_id)
                    return
            self._writes.complete_verified(node_id, combined)
        except Exception as exc:
            logger.exception("Verify after write failed for %s", node_id)
            self._writes.fail(node_id, f"Verify failed: {exc}")

    def _ensure_available(self) -> None:
        if not self._reader.available:
            raise AdminConfigError(
                "Remote config write unavailable — set meshtastic.admin_key_b64",
                status_code=503,
            )
        if self._tx is None or not self._tx.meshtastic_enabled:
            raise AdminConfigError(
                "Meshtastic TX not available (transmit.enabled required)",
                status_code=503,
            )

    def _validate_and_build_messages(
        self,
        *,
        long_name: str | None,
        short_name: str | None,
        role: int | None,
        role_confirm: str | None,
        screen_on_secs: int | None,
        telemetry_interval_secs: int | None,
    ) -> tuple[dict[str, Any], list[str], list[tuple[str, admin_pb2.AdminMessage]]]:
        changes: dict[str, Any] = {}
        verify_sections: list[str] = []
        messages: list[tuple[str, admin_pb2.AdminMessage]] = []

        if long_name is not None:
            name = long_name.strip()
            if not name or len(name) > 40:
                raise AdminConfigError(
                    "long_name must be 1–40 characters",
                    status_code=400,
                )
            changes["long_name"] = name

        if short_name is not None:
            short = short_name.strip()
            if not short or len(short) > 4:
                raise AdminConfigError(
                    "short_name must be 1–4 characters",
                    status_code=400,
                )
            changes["short_name"] = short

        if long_name is not None or short_name is not None:
            msg = admin_pb2.AdminMessage()
            if long_name is not None:
                msg.set_owner.long_name = changes["long_name"]
            if short_name is not None:
                msg.set_owner.short_name = changes["short_name"]
            messages.append(("owner", msg))
            verify_sections.append("owner")

        if role is not None:
            if (role_confirm or "").strip() != ROLE_CONFIRM_TOKEN:
                raise AdminConfigError(
                    f'role change requires role_confirm="{ROLE_CONFIRM_TOKEN}"',
                    status_code=400,
                )
            if role not in _ALLOWED_ROLES:
                raise AdminConfigError(
                    f"role {role} is not allowed for remote write",
                    status_code=400,
                )
            changes["role"] = role
            msg = admin_pb2.AdminMessage()
            msg.set_config.device.role = role
            messages.append(("device_role", msg))
            if "device" not in verify_sections:
                verify_sections.append("device")

        if screen_on_secs is not None:
            if not 0 <= screen_on_secs <= 600:
                raise AdminConfigError(
                    "screen_on_secs must be between 0 and 600",
                    status_code=400,
                )
            changes["screen_on_secs"] = screen_on_secs
            msg = admin_pb2.AdminMessage()
            msg.set_config.display.screen_on_secs = screen_on_secs
            messages.append(("display", msg))
            if "display" not in verify_sections:
                verify_sections.append("display")

        if telemetry_interval_secs is not None:
            if not 30 <= telemetry_interval_secs <= 86400:
                raise AdminConfigError(
                    "telemetry_interval_secs must be between 30 and 86400",
                    status_code=400,
                )
            changes["telemetry_interval_secs"] = telemetry_interval_secs
            msg = admin_pb2.AdminMessage()
            msg.set_module_config.telemetry.device_update_interval = (
                telemetry_interval_secs
            )
            messages.append(("telemetry", msg))
            if "telemetry" not in verify_sections:
                verify_sections.append("telemetry")

        if not messages:
            raise AdminConfigError(
                "No writable fields provided",
                status_code=400,
            )

        return changes, verify_sections, messages
