"""Tests for meshtasticd_control read/write helpers."""

import unittest
from unittest.mock import MagicMock, patch

from src.capture.meshtasticd_control import (
    MeshtasticdWriteLoraRequest,
    MeshtasticdWriteOwnerRequest,
    apply_write_lora,
    apply_write_owner,
    read_radio_state_from_iface,
)


class TestReadRadioState(unittest.TestCase):
    def test_disconnected_returns_empty_state(self):
        state = read_radio_state_from_iface(None)
        self.assertFalse(state.bridge_connected)
        self.assertEqual(state.local_node_id_hex, "")

    @patch("src.capture.meshtasticd_config_sync.read_local_node_id_hex", return_value="aabbccdd")
    def test_reads_owner_and_lora(self, _mock_id):
        iface = MagicMock()
        user = MagicMock()
        user.longName = "Meshpoint Test"
        user.shortName = "MPT"
        user.hwModel = 37
        lora = MagicMock()
        lora.tx_power = 22
        lora.tx_enabled = True
        lora.region = 1
        lora.modem_preset = 0
        local_node = MagicMock()
        local_node.user = user
        local_node.localConfig.lora = lora
        local_node.getChannelByChannelIndex.return_value = None
        iface.localNode = local_node
        iface.metadata.firmwareVersion = "2.7.15"

        with patch(
            "src.capture.meshtasticd_control._region_name_from_lora",
            return_value="US",
        ):
            with patch(
                "src.capture.meshtasticd_control._modem_preset_name_from_lora",
                return_value="LONG_FAST",
            ):
                state = read_radio_state_from_iface(iface)

        self.assertTrue(state.bridge_connected)
        self.assertEqual(state.local_node_id_hex, "aabbccdd")
        self.assertEqual(state.long_name, "Meshpoint Test")
        self.assertEqual(state.short_name, "MPT")
        self.assertEqual(state.tx_power_dbm, 22)
        self.assertTrue(state.tx_enabled)


class TestApplyWrite(unittest.TestCase):
    def test_write_owner_calls_set_owner(self):
        node = MagicMock()
        apply_write_owner(
            node,
            MeshtasticdWriteOwnerRequest(long_name="Long", short_name="shrt"),
        )
        node.setOwner.assert_called_once_with(long_name="Long", short_name="shrt")

    def test_write_lora_tx_power(self):
        node = MagicMock()
        lora = MagicMock()
        node.localConfig.lora = lora
        changes = apply_write_lora(
            node,
            MeshtasticdWriteLoraRequest(tx_power_dbm=27),
        )
        node.writeConfig.assert_called_once_with("lora")
        self.assertIn("tx_power=27", changes[0])

    def test_write_lora_rejects_invalid_power(self):
        node = MagicMock()
        node.localConfig.lora = MagicMock()
        with self.assertRaises(ValueError):
            apply_write_lora(node, MeshtasticdWriteLoraRequest(tx_power_dbm=99))


if __name__ == "__main__":
    unittest.main()
