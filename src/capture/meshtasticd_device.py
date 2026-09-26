"""Device-role administration through the Meshtastic SDK (no routing logic)."""

import threading

from meshtastic.protobuf import admin_pb2, config_pb2


ROLES = ("CLIENT", "CLIENT_MUTE", "CLIENT_BASE", "ROUTER", "ROUTER_LATE", "REPEATER")
REBROADCAST = ("ALL", "LOCAL_ONLY", "KNOWN_ONLY", "CORE_PORTNUMS_ONLY", "ALL_SKIP_DECODING")


def validate_device(role, rebroadcast_mode):
    if role not in ROLES or rebroadcast_mode not in REBROADCAST:
        raise ValueError("Unsupported device role or rebroadcast mode")
    if rebroadcast_mode == "ALL_SKIP_DECODING" and role != "REPEATER":
        raise ValueError("ALL_SKIP_DECODING requires the REPEATER role")


def read_device(node):
    """Request a correlated response; never confirm writes from the SDK cache."""
    received = threading.Event()
    responses = []

    def response(packet):
        raw = packet.get("decoded", {}).get("admin", {}).get("raw")
        if raw is not None and raw.HasField("get_config_response"):
            config = raw.get_config_response
            if config.HasField("device"):
                device = config_pb2.Config.DeviceConfig()
                device.CopyFrom(config.device)
                responses.append(device)
        received.set()

    request = admin_pb2.AdminMessage()
    request.get_config_request = admin_pb2.AdminMessage.DEVICE_CONFIG
    sent = node._sendAdmin(request, wantResponse=True, onResponse=response)
    try:
        if not received.wait(8) or not responses:
            raise RuntimeError("Device readback unavailable; reconnect and reload radio settings")
        # Other SDK writes copy this message (for example the node-info interval).
        # Refresh it only from the device response so later writes retain the role.
        node.localConfig.device.CopyFrom(responses[0])
        return responses[0]
    finally:
        if sent is not None:
            node.iface.responseHandlers.pop(sent.id, None)


def device_state(device):
    return {
        "role": config_pb2.Config.DeviceConfig.Role.Name(device.role),
        "rebroadcast_mode": config_pb2.Config.DeviceConfig.RebroadcastMode.Name(device.rebroadcast_mode),
        "roles": list(ROLES),
        "rebroadcast_modes": list(REBROADCAST),
    }


def write_device(node, role, rebroadcast_mode):
    validate_device(role, rebroadcast_mode)
    device = read_device(node)
    device.role = config_pb2.Config.DeviceConfig.Role.Value(role)
    device.rebroadcast_mode = config_pb2.Config.DeviceConfig.RebroadcastMode.Value(rebroadcast_mode)
    request = admin_pb2.AdminMessage()
    request.set_config.device.CopyFrom(device)
    node._sendAdmin(request, wantResponse=False)
    actual = device_state(read_device(node))
    if actual["role"] != role or actual["rebroadcast_mode"] != rebroadcast_mode:
        raise RuntimeError("Device readback differs; reload settings before retrying")
    return actual
