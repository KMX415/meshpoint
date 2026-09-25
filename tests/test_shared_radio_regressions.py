from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
from src.transmit.meshcore_channel_sync import MeshcoreChannelSync
from src.transmit.meshcore_tx_client import MeshCoreTxClient


@pytest.mark.asyncio
async def test_tcp_transport_does_not_probe_usb():
    source = MeshcoreUsbCaptureSource(connection_type='tcp', tcp_host='localhost', tcp_port=5000)
    with patch('src.capture.meshcore_usb_detect.detect_meshcore_port') as detect:
        assert await source._resolve_port() == 'tcp://localhost:5000'
        detect.assert_not_called()


@pytest.mark.asyncio
async def test_channel_verification_detects_failed_deletion():
    sync = MeshcoreChannelSync(None)
    slots = {i: ('', bytes(16)) for i in range(8)}
    slots[1] = ('old channel', bytes(16))
    sync._probe_slots = AsyncMock(return_value=slots)
    with pytest.raises(RuntimeError, match='deletion'):
        await sync.verify({})


@pytest.mark.asyncio
async def test_failed_refresh_does_not_report_cached_settings_as_verified():
    from meshcore import EventType
    client = MeshCoreTxClient()
    client.set_connection(SimpleNamespace(commands=SimpleNamespace(
        send_appstart=AsyncMock(return_value=SimpleNamespace(type=EventType.ERROR)))))
    client._pause_auto_fetch = AsyncMock()
    client._resume_auto_fetch = AsyncMock()
    assert await client.refresh_radio_info() is None
    client._resume_auto_fetch.assert_awaited_once()
