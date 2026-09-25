import queue
from unittest.mock import MagicMock

import pytest

from src.capture.meshtasticd_bridge_source import MeshtasticdBridgeSource
from src.transmit.meshtasticd_tx_client import MeshtasticdTxClient


def test_late_ipc_response_cannot_acknowledge_next_send():
    source = MeshtasticdBridgeSource()
    source._cmd_queue, source._resp_queue = MagicMock(), MagicMock()
    source._resp_queue.get.side_effect = queue.Empty()
    assert not source.request_read_radio_state()[0]
    source._resp_queue.get.side_effect = None
    source._resp_queue.get.return_value = ('ok', {'packet_id': '12345678'})
    assert not source.request_send_text('test', 0xFFFFFFFF)[0]
    assert source._cmd_queue.put.call_count == 1


@pytest.mark.asyncio
async def test_real_daemon_packet_id_reaches_message_tracking():
    source = MagicMock(is_running=True)
    source.request_send_text.return_value = (True, {'packet_id': '12345678'})
    client = MeshtasticdTxClient()
    client.set_source(source)
    result = await client.send_text('test', 'broadcast')
    assert result.success and result.packet_id == '12345678'
