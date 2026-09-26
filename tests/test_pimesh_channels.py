from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from meshtastic.protobuf import channel_pb2

from src.capture.meshtasticd_channels import read_channels, write_channels


def radio():
    channels = [channel_pb2.Channel(index=i) for i in range(8)]
    channels[0].role = 1
    channels[0].settings.psk = b"\x01"
    node = SimpleNamespace(channels=channels, writeChannel=Mock())
    node.getChannelByChannelIndex = lambda index: channels[index]
    return node


def test_native_channels_edit_and_remove():
    node = radio()
    entries = read_channels(node)
    entries.append({"index": 1, "name": "private", "psk_b64": "YQ=="})
    result = write_channels(node, entries)
    assert result[0]["psk_b64"] == "AQ=="
    assert node.channels[1].role == 2
    assert node.channels[1].settings.psk == b"a"
    write_channels(node, entries[:1])
    assert node.channels[1].role == 0


@pytest.mark.parametrize(
    "entry",
    [
        {"index": 0, "name": "duplicate"},
        {"index": 9, "name": "outside"},
        {"index": 1, "name": "too-long-channel-name"},
        {"index": 1, "psk_b64": "%%%bad"},
        {"index": 1, "psk_b64": "YWI="},
    ],
)
def test_entire_update_validated_before_write(entry):
    node = radio()
    primary = read_channels(node)[0]
    primary["name"] = "new"
    with pytest.raises(ValueError):
        write_channels(node, [primary, entry])
    node.writeChannel.assert_not_called()
    assert node.channels[0].settings.name == ""
