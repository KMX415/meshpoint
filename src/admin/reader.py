"""Build ADMIN get-config requests and correlate inbound responses."""
from __future__ import annotations

import base64
import logging
import struct
from typing import Any

from meshtastic.protobuf import admin_pb2, mesh_pb2

from src.admin.config_decode import message_to_redacted_dict
from src.admin.pending_store import PendingConfigStore
from src.decode.crypto_service import CryptoService
from src.models.packet import Packet
from src.relay.node_id import normalize_node_id, validate_node_ids
from src.transmit.tx_service import SendResult, TxService

logger = logging.getLogger(__name__)

PORTNUM_ADMIN = 6
MESHTASTIC_HEADER_SIZE = 16

_SECTION_CONFIG_TYPE: dict[str, int] = {
    "device": admin_pb2.AdminMessage.DEVICE_CONFIG,
    "position": admin_pb2.AdminMessage.POSITION_CONFIG,
    "power": admin_pb2.AdminMessage.POWER_CONFIG,
    "network": admin_pb2.AdminMessage.NETWORK_CONFIG,
    "display": admin_pb2.AdminMessage.DISPLAY_CONFIG,
    "lora": admin_pb2.AdminMessage.LORA_CONFIG,
    "bluetooth": admin_pb2.AdminMessage.BLUETOOTH_CONFIG,
    "security": admin_pb2.AdminMessage.SECURITY_CONFIG,
}


class AdminConfigReader:
    """Send ADMIN read requests and capture responses from the RX pipeline."""

    def __init__(
        self,
        *,
        tx_service: TxService | None,
        crypto: CryptoService | None,
        admin_key_b64: str = "",
        admin_channel_name: str = "admin",
        local_node_id: int = 0,
    ) -> None:
        self._tx = tx_service
        self._crypto = crypto
        self._admin_key_b64 = (admin_key_b64 or "").strip()
        self._admin_channel_name = (admin_channel_name or "admin").strip() or "admin"
        self._local_node_id = local_node_id
        self._store = PendingConfigStore()
        self._admin_key: bytes | None = None
        self._refresh_admin_key()

    @property
    def available(self) -> bool:
        return bool(self._admin_key_b64 and self._admin_key)

    @property
    def store(self) -> PendingConfigStore:
        return self._store

    def update_config(
        self,
        *,
        admin_key_b64: str = "",
        admin_channel_name: str = "admin",
        local_node_id: int = 0,
    ) -> None:
        self._admin_key_b64 = (admin_key_b64 or "").strip()
        self._admin_channel_name = (admin_channel_name or "admin").strip() or "admin"
        self._local_node_id = local_node_id
        self._refresh_admin_key()

    def _refresh_admin_key(self) -> None:
        if not self._admin_key_b64:
            self._admin_key = None
            return
        try:
            raw = base64.b64decode(self._admin_key_b64)
            self._admin_key = CryptoService._expand_key(raw)
        except Exception:
            logger.warning("Invalid meshtastic.admin_key_b64", exc_info=True)
            self._admin_key = None

    async def request_config(
        self,
        node_id: str,
        section: str = "device",
    ) -> dict[str, Any]:
        if not self.available:
            raise AdminConfigError(
                "Remote config read unavailable — set meshtastic.admin_key_b64 in local.yaml",
                status_code=503,
            )
        if self._tx is None or not self._tx.meshtastic_enabled:
            raise AdminConfigError(
                "Meshtastic TX not available (transmit.enabled required)",
                status_code=503,
            )

        normalized = validate_node_ids([node_id])[0]
        section_key = (section or "device").strip().lower()
        if section_key not in _SECTION_CONFIG_TYPE and section_key != "owner":
            raise AdminConfigError(
                f"Unknown config section {section!r}",
                status_code=400,
            )

        ok, reason = self._store.can_request(normalized)
        if not ok:
            raise AdminConfigError(reason, status_code=429)

        dest_int = int(normalized, 16)
        if dest_int in (0, 0xFFFFFFFF):
            raise AdminConfigError(
                "Cannot request config from broadcast node",
                status_code=400,
            )

        admin_msg = self._build_admin_message(section_key)
        expected = (
            "get_owner_response"
            if section_key == "owner"
            else "get_config_response"
        )
        result = await self._tx.send_admin_message(
            admin_payload=admin_msg.SerializeToString(),
            destination=dest_int,
            admin_key=self._admin_key,
            admin_channel_name=self._admin_channel_name,
            want_ack=True,
        )
        if not result.success:
            raise AdminConfigError(
                result.error or "ADMIN TX failed",
                status_code=502,
            )

        state = self._store.begin(
            normalized,
            section=section_key,
            packet_id=result.packet_id,
            expected_response=expected,
        )
        return self._state_payload(state)

    def get_status(self, node_id: str) -> dict[str, Any]:
        normalized = normalize_node_id(node_id)
        state = self._store.get(normalized)
        if state is None:
            return {
                "node_id": normalized,
                "status": "idle",
                "section": None,
                "config": None,
                "error": "",
            }
        return self._state_payload(state)

    def try_consume_packet(self, packet: Packet) -> None:
        if not self.available or self._crypto is None:
            return
        if packet.protocol.value != "meshtastic":
            return

        source = normalize_node_id(packet.source_id or "")
        state = self._store.get(source)
        if state is None or state.status != "pending":
            return

        raw = packet.raw_radio_packet
        if not raw or len(raw) < MESHTASTIC_HEADER_SIZE:
            return

        header = self._parse_header(raw[:MESHTASTIC_HEADER_SIZE])
        if header is None:
            return

        if self._local_node_id and header["dest_id"] not in (
            self._local_node_id,
            0xFFFFFFFF,
        ):
            return

        encrypted = raw[MESHTASTIC_HEADER_SIZE:]
        decrypted = self._crypto.decrypt_meshtastic(
            encrypted,
            header["packet_id"],
            header["source_id"],
            key=self._admin_key,
        )
        if decrypted is None:
            return

        data = mesh_pb2.Data()
        try:
            data.ParseFromString(decrypted)
        except Exception:
            return
        if data.portnum != PORTNUM_ADMIN:
            return

        admin_msg = admin_pb2.AdminMessage()
        try:
            admin_msg.ParseFromString(data.payload)
        except Exception:
            return

        payload = self._extract_response(admin_msg, state.expected_response)
        if payload is None:
            return

        self._store.complete(source, payload)
        logger.info(
            "ADMIN config response from %s section=%s request_id=%s",
            source,
            state.section,
            state.request_id,
        )

    @staticmethod
    def _build_admin_message(section: str) -> admin_pb2.AdminMessage:
        msg = admin_pb2.AdminMessage()
        if section == "owner":
            msg.get_owner_request = True
        else:
            msg.get_config_request = _SECTION_CONFIG_TYPE[section]
        return msg

    @staticmethod
    def _extract_response(
        admin_msg: admin_pb2.AdminMessage,
        expected: str,
    ) -> dict[str, Any] | None:
        if expected == "get_owner_response":
            if not admin_msg.HasField("get_owner_response"):
                return None
            return {
                "section": "owner",
                "owner": message_to_redacted_dict(admin_msg.get_owner_response),
            }
        if not admin_msg.HasField("get_config_response"):
            return None
        cfg_dict = message_to_redacted_dict(admin_msg.get_config_response)
        populated = {
            k: v for k, v in cfg_dict.items() if v is not None and v != {}
        }
        return {"section": "config", "config": populated}

    @staticmethod
    def _parse_header(header_bytes: bytes) -> dict[str, int] | None:
        try:
            dest_id, source_id, packet_id = struct.unpack_from(
                "<III", header_bytes, 0
            )
            return {
                "dest_id": dest_id,
                "source_id": source_id,
                "packet_id": packet_id,
            }
        except struct.error:
            return None

    @staticmethod
    def _state_payload(state) -> dict[str, Any]:
        return {
            "node_id": state.node_id,
            "request_id": state.request_id,
            "status": state.status,
            "section": state.section,
            "packet_id": state.packet_id,
            "requested_at": state.requested_at,
            "completed_at": state.completed_at or None,
            "config": state.config,
            "error": state.error,
        }


class AdminConfigError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
