"""Meshtastic portnum payload decoders.

Each handler takes raw protobuf payload bytes and returns
(decoded_dict, PacketType). Imported by MeshtasticDecoder.
"""

from __future__ import annotations

from typing import Any, Optional

from src.models.packet import PacketType

PORTNUM_TEXT = 1
PORTNUM_POSITION = 3
PORTNUM_NODEINFO = 4
PORTNUM_ROUTING = 5
PORTNUM_ADMIN = 6
PORTNUM_WAYPOINT = 8
PORTNUM_DETECTION_SENSOR = 10
PORTNUM_PAXCOUNTER = 34
PORTNUM_STORE_FORWARD = 65
PORTNUM_RANGE_TEST = 66
PORTNUM_TELEMETRY = 67
PORTNUM_TRACEROUTE = 70
PORTNUM_NEIGHBORINFO = 71
PORTNUM_MAP_REPORT = 73

_Result = tuple[Optional[dict[str, Any]], PacketType]


def dispatch_portnum(portnum: int, payload: bytes) -> _Result:
    handler = _HANDLERS.get(portnum)
    if handler:
        return handler(payload)
    return {"portnum": portnum, "raw_hex": payload.hex()}, PacketType.UNKNOWN


def _decode_text(payload: bytes) -> _Result:
    return {"text": payload.decode("utf-8", errors="replace")}, PacketType.TEXT


def _decode_position(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mesh_pb2

        pos = mesh_pb2.Position()
        pos.ParseFromString(payload)
        return {
            "latitude": pos.latitude_i * 1e-7,
            "longitude": pos.longitude_i * 1e-7,
            "altitude": pos.altitude if pos.altitude else None,
            "sats_in_view": pos.sats_in_view if pos.sats_in_view else None,
            "precision_bits": pos.precision_bits if pos.precision_bits else None,
            "ground_speed": pos.ground_speed if pos.ground_speed else None,
            "ground_track": pos.ground_track if pos.ground_track else None,
        }, PacketType.POSITION
    except Exception:
        return None, PacketType.POSITION


def _decode_nodeinfo(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mesh_pb2

        user = mesh_pb2.User()
        user.ParseFromString(payload)
        return {
            "long_name": user.long_name or None,
            "short_name": user.short_name or None,
            "hw_model": str(user.hw_model) if user.hw_model else None,
            "id": user.id or None,
            "role": str(user.role) if user.role else None,
            "public_key": (
                user.public_key.hex()
                if user.public_key and len(user.public_key) == 32
                else None
            ),
        }, PacketType.NODEINFO
    except Exception:
        return None, PacketType.NODEINFO


def _decode_telemetry(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import telemetry_pb2

        telem = telemetry_pb2.Telemetry()
        telem.ParseFromString(payload)
        result: dict[str, Any] = {}
        if telem.HasField("local_stats"):
            result["telemetry_variant"] = "local_stats"
        elif telem.HasField("device_metrics"):
            result["telemetry_variant"] = "device_metrics"
        elif payload.startswith(b"\x32"):
            result["telemetry_variant"] = "local_stats"
        else:
            result["telemetry_variant"] = "device_metrics"
        if telem.HasField("device_metrics"):
            dm = telem.device_metrics
            result["battery_level"] = dm.battery_level or None
            result["voltage"] = dm.voltage or None
            result["channel_utilization"] = dm.channel_utilization or None
            result["air_util_tx"] = dm.air_util_tx or None
            result["uptime_seconds"] = dm.uptime_seconds or None
        if telem.HasField("local_stats"):
            ls = telem.local_stats
            result["local_uptime_seconds"] = ls.uptime_seconds or None
            result["local_channel_utilization"] = ls.channel_utilization or None
            result["local_air_util_tx"] = ls.air_util_tx or None
            result["num_packets_tx"] = ls.num_packets_tx or None
            result["num_packets_rx"] = ls.num_packets_rx or None
        if telem.HasField("environment_metrics"):
            em = telem.environment_metrics
            result["temperature"] = em.temperature or None
            result["humidity"] = em.relative_humidity or None
            result["barometric_pressure"] = em.barometric_pressure or None
        if telem.HasField("power_metrics"):
            pm = telem.power_metrics
            result["power_ch1_voltage"] = pm.ch1_voltage or None
            result["power_ch1_current"] = pm.ch1_current or None
            result["power_ch2_voltage"] = pm.ch2_voltage or None
            result["power_ch2_current"] = pm.ch2_current or None
        return result, PacketType.TELEMETRY
    except Exception:
        return None, PacketType.TELEMETRY


def _decode_waypoint(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mesh_pb2

        wp = mesh_pb2.Waypoint()
        wp.ParseFromString(payload)
        return {
            "id": wp.id,
            "name": wp.name or None,
            "description": wp.description or None,
            "latitude": wp.latitude_i * 1e-7 if wp.latitude_i else None,
            "longitude": wp.longitude_i * 1e-7 if wp.longitude_i else None,
            "icon": wp.icon or None,
        }, PacketType.WAYPOINT
    except Exception:
        return None, PacketType.WAYPOINT


def _decode_range_test(payload: bytes) -> _Result:
    return {"text": payload.decode("utf-8", errors="replace")}, PacketType.RANGE_TEST


def _decode_store_forward(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import storeforward_pb2

        sf = storeforward_pb2.StoreAndForward()
        sf.ParseFromString(payload)
        result: dict[str, Any] = {"rr": sf.rr}
        if sf.HasField("heartbeat"):
            result["period"] = sf.heartbeat.period
            result["secondary"] = sf.heartbeat.secondary
        if sf.HasField("stats"):
            result["messages_total"] = sf.stats.messages_total
            result["messages_saved"] = sf.stats.messages_saved
            result["messages_max"] = sf.stats.messages_max
        return result, PacketType.STORE_FORWARD
    except Exception:
        return {"raw_hex": payload.hex()}, PacketType.STORE_FORWARD


def _decode_detection_sensor(payload: bytes) -> _Result:
    return {"text": payload.decode("utf-8", errors="replace")}, PacketType.DETECTION_SENSOR


def _decode_paxcounter(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import paxcount_pb2

        pax = paxcount_pb2.Paxcount()
        pax.ParseFromString(payload)
        return {
            "wifi": pax.wifi,
            "ble": pax.ble,
            "uptime": pax.uptime,
        }, PacketType.PAXCOUNTER
    except Exception:
        return {"raw_hex": payload.hex()}, PacketType.PAXCOUNTER


def _decode_map_report(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mqtt_pb2

        report = mqtt_pb2.MapReport()
        report.ParseFromString(payload)
        result: dict[str, Any] = {
            "long_name": report.long_name or None,
            "short_name": report.short_name or None,
            "hw_model": str(report.hw_model) if report.hw_model else None,
            "firmware_version": report.firmware_version or None,
            "num_online_local_nodes": report.num_online_local_nodes or None,
            "modem_preset": str(report.modem_preset) if report.modem_preset else None,
            "region": str(report.region) if report.region else None,
            "has_default_channel": report.has_default_channel if report.has_default_channel else None,
        }
        if report.latitude_i:
            result["latitude"] = report.latitude_i * 1e-7
        if report.longitude_i:
            result["longitude"] = report.longitude_i * 1e-7
        return result, PacketType.MAP_REPORT
    except Exception:
        return {"raw_hex": payload.hex()}, PacketType.MAP_REPORT


def _decode_routing(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mesh_pb2

        routing = mesh_pb2.Routing()
        routing.ParseFromString(payload)
        result: dict[str, Any] = {}
        if routing.error_reason:
            result["error_reason"] = str(routing.error_reason)
        if routing.HasField("route_request"):
            rr = routing.route_request
            result["route_request"] = [format(n, '08x') for n in rr.route]
        if routing.HasField("route_reply"):
            rr = routing.route_reply
            result["route_reply"] = [format(n, '08x') for n in rr.route]
        return result, PacketType.ROUTING
    except Exception:
        return {"raw_hex": payload.hex()}, PacketType.ROUTING


def _decode_neighborinfo(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mesh_pb2

        ni = mesh_pb2.NeighborInfo()
        ni.ParseFromString(payload)
        neighbors = []
        for n in ni.neighbors:
            neighbors.append({
                "node_id": format(n.node_id, '08x'),
                "snr": round(n.snr, 1) if n.snr else None,
            })
        return {
            "neighbors": neighbors,
            "node_broadcast_interval_secs": ni.node_broadcast_interval_secs or None,
        }, PacketType.NEIGHBORINFO
    except Exception:
        return {"raw_hex": payload.hex()}, PacketType.NEIGHBORINFO


def _decode_traceroute(payload: bytes) -> _Result:
    try:
        from meshtastic.protobuf import mesh_pb2

        rd = mesh_pb2.RouteDiscovery()
        rd.ParseFromString(payload)
        route = [format(node_id, '08x') for node_id in rd.route]
        snr_towards = list(rd.snr_towards) if rd.snr_towards else []
        snr_back = list(rd.snr_back) if rd.snr_back else []
        return {
            "route": route,
            "snr_towards": snr_towards,
            "snr_back": snr_back,
        }, PacketType.TRACEROUTE
    except Exception:
        return {"raw_hex": payload.hex()}, PacketType.TRACEROUTE


def _passthrough(ptype: PacketType):
    def _handler(payload: bytes) -> _Result:
        return {"portnum": None}, ptype
    return _handler


_HANDLERS = {
    PORTNUM_TEXT: _decode_text,
    PORTNUM_POSITION: _decode_position,
    PORTNUM_NODEINFO: _decode_nodeinfo,
    PORTNUM_TELEMETRY: _decode_telemetry,
    PORTNUM_ROUTING: _decode_routing,
    PORTNUM_TRACEROUTE: _decode_traceroute,
    PORTNUM_NEIGHBORINFO: _decode_neighborinfo,
    PORTNUM_ADMIN: _passthrough(PacketType.ADMIN),  # remote config and admin messages
    PORTNUM_WAYPOINT: _decode_waypoint,
    PORTNUM_RANGE_TEST: _decode_range_test,
    PORTNUM_STORE_FORWARD: _decode_store_forward,
    PORTNUM_DETECTION_SENSOR: _decode_detection_sensor,
    PORTNUM_PAXCOUNTER: _decode_paxcounter,
    PORTNUM_MAP_REPORT: _decode_map_report,
}
