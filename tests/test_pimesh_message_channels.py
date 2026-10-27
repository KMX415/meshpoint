from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import AppConfig
from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.models.packet import Packet, PacketType, Protocol


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol,channel', [('meshtastic', 0), ('meshtastic', 3), ('meshcore', 3)])
async def test_incoming_native_channel_uses_receiver_slot(protocol, channel):
    from src.api.server import _setup_message_interception

    cfg = AppConfig()
    coord = MagicMock()
    coord.node_repo._db = AsyncMock()
    coord.node_repo._db.fetch_one.return_value = None
    repo = SimpleNamespace(save_received=AsyncMock(return_value=(1, False)))
    resolver = SimpleNamespace(resolve=AsyncMock(return_value='Peer'))
    coroutines = []
    if protocol == 'meshtastic':
        packet = MeshtasticDecoder(CryptoService('AQ==')).decode_from_api_packet({
            'from': 0x12345678, 'to': 0xFFFFFFFF, 'id': 42, 'channel': channel,
            'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'text': 'test'},
        })
        packet.capture_source = 'meshtasticd'
    else:
        packet = Packet('42', '123456789012', 'channel:3', Protocol.MESHCORE,
                        PacketType.TEXT, channel_hash=channel, decoded_payload={'text': 'test'})
    with (
        patch('src.api.message_name_resolver.MessageNameResolver', return_value=resolver),
        patch('src.api.server.ws_manager.broadcast', new=AsyncMock()),
    ):
        _setup_message_interception(coord, repo, cfg)
        callback = coord.on_packet.call_args.args[0]
        with patch('asyncio.get_running_loop') as loop:
            loop.return_value.create_task.side_effect = coroutines.append
            callback(packet)
        for coroutine in coroutines:
            await coroutine
    values = repo.save_received.await_args.kwargs
    assert values['node_id'] == f'broadcast:{protocol}:{channel}'
    assert values['channel'] == channel


def test_phone_api_preserves_request_id_with_inner_payload():
    decoder = MeshtasticDecoder(CryptoService('AQ=='))
    packet = decoder.decode_from_api_packet({
        'from': 0x12345678, 'to': 0x87654321, 'id': 42, 'channel': 0,
        'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'payload': b'test', 'requestId': 123},
    })
    assert packet.decoded_payload['request_id'] == 123


@pytest.mark.parametrize('reason', ['NONE', 'NO_ROUTE'])
def test_phone_api_routing_response_with_empty_payload(reason):
    decoder = MeshtasticDecoder(CryptoService('AQ=='))
    packet = decoder.decode_from_api_packet({
        'from': 0x12345678, 'to': 0x87654321, 'id': 42, 'channel': 0,
        'decoded': {'portnum': 'ROUTING_APP', 'payload': b'', 'requestId': 123,
                    'routing': {'errorReason': reason}},
    })
    assert packet.packet_type == PacketType.ROUTING
    assert packet.decoded_payload['request_id'] == 123
    assert packet.decoded_payload.get('error_reason') == (None if reason == 'NONE' else reason)


@pytest.mark.asyncio
async def test_pimesh_message_picker_reads_native_slots(monkeypatch):
    from src.api.routes import messages

    cfg = AppConfig()
    cfg.device.radio_protocol = 'meshtastic'
    cfg.meshtastic.channel_keys = {'Stale': 'AQ=='}
    monkeypatch.setattr(messages, '_config', cfg)
    monkeypatch.setattr(messages, '_meshcore_tx', None)
    source = MagicMock()
    source.request_read_channels.return_value = (True, [
        {'index': 0, 'name': 'LongFast', 'enabled': True},
        {'index': 4, 'name': 'Private', 'enabled': True},
        {'index': 5, 'name': 'Disabled', 'enabled': False},
    ])
    with (
        patch('src.radio.pimesh_runtime.provisioned', return_value=True),
        patch('src.api.routes.config_routes._pimesh_meshtastic_bridge', return_value=source),
    ):
        rows = await messages.get_channels()
    assert [(row['channel'], row['name']) for row in rows] == [(0, 'LongFast'), (4, 'Private')]
    assert all('psk_b64' not in row for row in rows)
