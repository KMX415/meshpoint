from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import AppConfig
from src.models.packet import Packet, PacketType, Protocol


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol,channel', [('meshcore', 0), ('meshcore', 3)])
async def test_incoming_native_channel_uses_receiver_slot(protocol, channel):
    from src.api.server import _setup_message_interception

    cfg = AppConfig()
    coord = MagicMock()
    coord.node_repo._db = AsyncMock()
    coord.node_repo._db.fetch_one.return_value = None
    repo = SimpleNamespace(save_received=AsyncMock(return_value=(1, False)))
    resolver = SimpleNamespace(resolve=AsyncMock(return_value='Peer'))
    coroutines = []
    packet = Packet('42', '123456789012', f'channel:{channel}', Protocol.MESHCORE,
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
