"""Tests for MeshtasticTransmitter no-payload WARN dedup behavior."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from src.config import RelayConfig
from src.models.packet import Packet, PacketType, Protocol
from src.relay.meshtastic_transmitter import MeshtasticTransmitter


def _make_packet(packet_id: str = "abc123") -> Packet:
    return Packet(
        packet_id=packet_id,
        source_id="11111111",
        destination_id="ffffffff",
        protocol=Protocol.MESHTASTIC,
        packet_type=PacketType.TEXT,
        encrypted_payload=None,
        decoded_payload=None,
        # decrypted=True with raw_app_payload=None exercises the
        # "we have a real packet but somehow no inner bytes" path
        # the dedup-warning logic was written to cover.
        decrypted=True,
        raw_app_payload=None,
    )


class TestRelayPositivePath(unittest.TestCase):
    """Verifies that a normally-decoded TEXT packet produces an
    actual sendData call. This is the regression test for the
    long-standing 'relay never worked end-to-end' bug — the
    decoder now hands the inner application bytes through
    Packet.raw_app_payload and the transmitter forwards them.
    """

    def test_decoded_text_packet_calls_send_data(self):
        config = RelayConfig(enabled=True, serial_port="/dev/null")
        tx = MeshtasticTransmitter(config)
        tx._connected = True
        tx._interface = MagicMock()

        packet = Packet(
            packet_id="abc123",
            source_id="11111111",
            destination_id="ffffffff",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
            hop_limit=2,
            channel_hash=8,
            decrypted=True,
            decoded_payload={"text": "hello"},
            raw_app_payload=b"hello",
        )

        tx.transmit(packet)

        tx._interface.sendData.assert_called_once()
        kwargs = tx._interface.sendData.call_args.kwargs
        args = tx._interface.sendData.call_args.args
        self.assertEqual(args[0], b"hello")
        self.assertEqual(kwargs["portNum"], 1)
        # Hop limit decrements by 1 on relay so we don't extend mesh
        # reach beyond what the originator authorised.
        self.assertEqual(kwargs["hopLimit"], 1)
        self.assertEqual(kwargs["channelIndex"], 8)

    def test_undecrypted_packet_is_not_relayed(self):
        config = RelayConfig(enabled=True, serial_port="/dev/null")
        tx = MeshtasticTransmitter(config)
        tx._connected = True
        tx._interface = MagicMock()

        packet = Packet(
            packet_id="abc123",
            source_id="11111111",
            destination_id="ffffffff",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.ENCRYPTED,
            encrypted_payload=b"\xde\xad\xbe\xef",
            decrypted=False,
        )

        tx.transmit(packet)
        tx._interface.sendData.assert_not_called()


class TestNoPayloadWarnDedup(unittest.TestCase):
    """The 'no payload available' message should fire WARN once per
    process and DEBUG thereafter to avoid log spam."""

    def setUp(self):
        config = RelayConfig(enabled=True, serial_port="/dev/null")
        self.tx = MeshtasticTransmitter(config)
        self.tx._connected = True
        self.tx._interface = MagicMock()

    def test_first_no_payload_logs_warning(self):
        with self.assertLogs(
            "src.relay.meshtastic_transmitter", level="WARNING"
        ) as cm:
            self.tx.transmit(_make_packet("first"))
        self.assertTrue(
            any("no payload available" in msg for msg in cm.output),
            f"Expected WARN log, got: {cm.output}",
        )
        self.assertTrue(self.tx._payload_warning_logged)
        self.tx._interface.sendData.assert_not_called()

    def test_subsequent_no_payload_logs_debug_only(self):
        self.tx.transmit(_make_packet("first"))
        warn_count = 0
        debug_count = 0

        logger_name = "src.relay.meshtastic_transmitter"
        logger = logging.getLogger(logger_name)
        previous_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with self.assertLogs(logger_name, level="DEBUG") as cm:
                for i in range(5):
                    self.tx.transmit(_make_packet(f"pkt-{i}"))
            for record in cm.records:
                if "no payload available" not in record.getMessage():
                    continue
                if record.levelno == logging.WARNING:
                    warn_count += 1
                elif record.levelno == logging.DEBUG:
                    debug_count += 1
        finally:
            logger.setLevel(previous_level)

        self.assertEqual(warn_count, 0)
        self.assertEqual(debug_count, 5)

    def test_warn_flag_persists_across_calls(self):
        self.tx.transmit(_make_packet("first"))
        self.assertTrue(self.tx._payload_warning_logged)
        self.tx.transmit(_make_packet("second"))
        self.assertTrue(self.tx._payload_warning_logged)

    def test_warn_flag_starts_false(self):
        config = RelayConfig(enabled=True, serial_port="/dev/null")
        fresh_tx = MeshtasticTransmitter(config)
        self.assertFalse(fresh_tx._payload_warning_logged)


if __name__ == "__main__":
    unittest.main()
