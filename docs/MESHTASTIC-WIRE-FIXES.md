# Meshtastic wire-format corrections

Independent of the SX1301 adapter. This branch is based directly on the recorded upstream main revision and can be reviewed without SX1301, experiment or dashboard code. AI assistance was used; nothing has been published.

- Set radio-header byte 15 to the transmitting node's low ID byte for locally originated packets.
- Update that byte on a native relay while preserving the original source, destination, packet ID, channel and encrypted body, and decrementing the remaining hop count.
- Preserve `RouteDiscovery.route_back` when decoding a traceroute reply.

Focused tests check the originated header, relay identity/body invariants and decoded return route. There are no new radio drivers, outgoing traceroute commands, reporting-consent settings, scheduled broadcasts or GNSS features here.

Protocol references: [Meshtastic Router](https://github.com/meshtastic/firmware/blob/develop/src/mesh/Router.cpp) and [RouteDiscovery protobuf](https://github.com/meshtastic/protobufs/blob/master/meshtastic/mesh.proto). Confirm final compatibility with maintainers before submission.
