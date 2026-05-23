# MQTT and Meshradar

Meshpoint can publish captured packets to two independent destinations:

1. **Meshradar cloud** ([meshradar.io](https://meshradar.io)): the project's
   first-party platform. Aggregated multi-Meshpoint maps, fleet management,
   leaderboards, packet history, remote commands.
2. **Public MQTT brokers** (e.g. `mqtt.meshtastic.org`): the community
   Meshtastic ecosystem. Feeds tools like meshmap.net, NHmesh.live, Liam
   Cottle's map, Home Assistant integrations.

These are independent. You can run with neither, either, or both. This
document explains what each does, what data flows where, and how to choose.
For configuration syntax see [Configuration > Upstream](CONFIGURATION.md#upstream-cloud)
and [Configuration > MQTT](CONFIGURATION.md#mqtt-feed).

---

## Side-by-Side

| | Meshradar (`upstream`) | Community MQTT (`mqtt`) |
|---|---|---|
| Default | **On** (after setup) | **Off** (opt-in) |
| Transport | WebSocket to `wss://api.meshradar.io` | MQTT/TCP to broker (default `mqtt.meshtastic.org:1883`) |
| Auth | API key from your Meshradar account | Broker username/password (community defaults provided) |
| Dual protocol | Yes (Meshtastic + MeshCore) | Yes (Meshtastic protobuf, MeshCore JSON) |
| Packets sent | All decoded packets | Only packets on channels in `publish_channels` allowlist |
| Encrypted packets | Sent (with metadata, no plaintext) | **Never sent** |
| Heartbeats | Yes (5 min) for fleet status | No |
| Where it appears | Meshradar dashboard, fleet, map, leaderboard | meshmap.net, Liam Cottle, NHmesh, your HA dashboard |
| Remote commands | Yes (ping, status, restart) | No |
| Cost to operator | Free for personal use | Free (public broker) or your own broker |

---

## Meshradar Cloud Uplink

Enabled by default after you run `sudo meshpoint setup` and paste an API
key. The Meshpoint maintains a WebSocket to `wss://api.meshradar.io`,
sends a heartbeat every 5 minutes, streams decoded packets, and accepts
remote commands.

### What gets sent

- Decoded packet metadata (sender, timestamp, RSSI, SNR, hop count, packet
  type, channel name, decoded payload)
- Encrypted packet metadata (sender, timestamp, RSSI, SNR, hop count, the
  fact that it was on an unknown channel) **without** plaintext content
- Periodic heartbeat with device status, capture stats, node roster
  changes since the last heartbeat
- Responses to remote commands (status snapshots, log tails, etc.)

### Privacy posture

- All communication is TLS (WebSocket Secure).
- Your API key is the per-device credential. Treat it like a password.
- Encrypted packets that the Meshpoint could not decrypt are reported as
  `ENCRYPTED` with their sender/signal metadata, but the encrypted payload
  itself is not sent.
- Decrypted private channel traffic (using PSKs you configured in
  `meshtastic.channel_keys`) **is** sent to Meshradar. If you do not want
  your private traffic on the cloud, do not configure those keys, or run
  with `upstream.enabled: false`.

### Running offline (no Meshradar cloud)

Set `upstream.enabled: false` in `local.yaml`. The Meshpoint never opens
an upstream connection and never transmits any packet, heartbeat, or
telemetry to meshradar.io. Capture, decoding, dashboard, MQTT, and
storage all keep working.

> The service still requires a valid `auth_token` at startup as a guardrail.
> Run the setup wizard once with a Meshradar API key, then flip
> `upstream.enabled: false`.

### Why use it

- Multi-site mesh intelligence: see all your Meshpoints (and friends')
  on a shared map.
- Fleet management: remotely check status, restart the service, pull logs.
- Long-term packet history beyond what your Pi's SD card can hold.
- Public leaderboard, Meshpoint and node profile pages, range and
  coverage analytics.

---

## Community MQTT Gateway

Off by default. Set `mqtt.enabled: true` to opt in. Once enabled,
publishes captured packets to the configured broker so they appear in the
Meshtastic community ecosystem.

### Two-Gate Privacy Model

MQTT publishing is protected by two independent gates that **both** must
pass for any packet to leave the device:

**Gate 1: Global kill switch.** `mqtt.enabled: true` must be explicitly set.

**Gate 2: Channel allowlist.** Only packets on channels listed in
`mqtt.publish_channels` are published. The default list contains only
`LongFast`. Private channels, custom-PSK channels, and packets on
channels not in the list never leave the device via MQTT.

Encrypted packets (those the Meshpoint could not decrypt) are **always**
blocked from MQTT regardless of channel configuration.

This two-gate approach is informed by active community discussion around
MQTT privacy in the Meshtastic firmware:
[firmware#5507 (explicit opt-in)](https://github.com/meshtastic/firmware/issues/5507),
[firmware#5404 (private channel leakage)](https://github.com/meshtastic/firmware/issues/5404),
[firmware#3549 (user-controlled publishing)](https://github.com/meshtastic/firmware/issues/3549).

### Minimum configuration

```yaml
mqtt:
  enabled: true
```

That's it. Broker, port, username, and password all default to the public
Meshtastic server (`mqtt.meshtastic.org:1883`, `meshdev` / `large4cats`).
Your Meshpoint appears on community maps with a unique gateway ID generated
from your node identity.

**Transport TLS (mqtts):** not implemented yet. The publisher uses plain TCP;
setting port 8883 does not enable encryption. Configuration → MQTT (v0.7.4+)
covers application settings (credentials, allowlist, JSON mirror, HA) but not
TLS. Broker TLS is planned for the same release as Meshtastic PKI; see
`docs/CONFIGURATION.md` (Transport TLS) and `docs/CHANGELOG.md` (Unreleased).

### Verifying it is publishing

After enabling and restarting:

```bash
sudo journalctl -u meshpoint --since "5 min ago" | grep -i mqtt
```

You should see `MQTT publisher started as !XXXXXXXX` followed by
`MQTT pub rc=0 topic=...` lines as packets arrive. If you see nothing,
the most common cause is the missing `paho-mqtt` package after a
`git pull` that did not re-run `pip install`. See
[Common Errors > MQTT enabled but no traffic on the broker](COMMON-ERRORS.md#mqtt-enabled-but-no-traffic-on-the-broker-no-mqtt-lines-in-logs)
for the full diagnostic table.

### Publishing private channels (your own broker)

If you want to publish a private channel into your own MQTT broker
(typical: feed Home Assistant on your LAN), point the broker at your local
server and explicitly add the channel to the allowlist:

```yaml
mqtt:
  enabled: true
  broker: "192.168.1.100"        # your local broker
  username: ""
  password: ""
  publish_channels:
    - "LongFast"
    - "MyPrivateChannel"         # explicitly opted in
```

**Never add private channel names when publishing to a public broker.**
That is the entire point of Gate 2.

### Topic format

Published topics are built as:

```
<topic_root>/<region>/2/e/<channel_name>/<gateway_id>
```

The two parts you control are `mqtt.topic_root` (default `"msh"`) and
`mqtt.region` (default `"US"`). The Meshpoint concatenates them with
a slash, so a default install publishes to
`msh/US/2/e/LongFast/!XXXXXXXX`.

A common mistake when coming from the Meshtastic Android app is to
write the regional path into `topic_root` itself:

```yaml
mqtt:
  topic_root: "msh/US/FL"   # wrong: doubles the region
  region: "US"              # default
# Result: msh/US/FL/US/2/e/LongFast/!XXXXXXXX
```

The right form is to keep `topic_root` as `"msh"` and put any regional
segment in `mqtt.region`:

```yaml
mqtt:
  topic_root: "msh"
  region: "US/FL"           # state or sub-region in the right slot
# Result: msh/US/FL/2/e/LongFast/!XXXXXXXX
```

`mqtt.region` is intentionally independent of `radio.region` because
the regional MQTT prefix (e.g., `US/FL`, `EU_868/DE`) is a community
naming convention, not a regulatory band. A US Meshpoint can still
publish under `EU` if it serves an EU community broker, and vice versa.

### Location precision

Choose how much GPS detail leaves the device via MQTT:

| Value | Behavior |
|---|---|
| `exact` | Full GPS coordinates (default) |
| `approximate` | Rounded to ~1.1 km precision (2 decimal places) |
| `none` | Location stripped entirely from MQTT messages |

Full-precision location is always available on the Meshradar dashboard
(if upstream is enabled) regardless of this MQTT setting.

### Home Assistant

Enable JSON mirror and HA auto-discovery and the broker will receive
discovery configs that automatically create sensors per node:
battery, temperature, GPS position.

```yaml
mqtt:
  enabled: true
  publish_json: true
  homeassistant_discovery: true
```

Sensors appear as `sensor.meshpoint_<node_id>_battery`,
`sensor.meshpoint_<node_id>_temperature`,
`device_tracker.meshpoint_<node_id>`.

---

## Choosing One, Both, or Neither

| Goal | Configuration |
|---|---|
| Meshradar cloud only (default) | `upstream.enabled: true`, `mqtt.enabled: false` |
| Community MQTT only (no cloud) | `upstream.enabled: false`, `mqtt.enabled: true` |
| Both: cloud + community presence | `upstream.enabled: true`, `mqtt.enabled: true` |
| Fully offline / private | `upstream.enabled: false`, `mqtt.enabled: false` |
| Cloud + private HA dashboard on your LAN | `upstream.enabled: true`, `mqtt.enabled: true`, `mqtt.broker: <your-local-broker>`, your private channels in `publish_channels` |

Most operators run **both** Meshradar and the public Meshtastic MQTT
broker. The two ecosystems serve different audiences and the data flows
do not overlap meaningfully.

---

## See Also

- [Configuration > Upstream](CONFIGURATION.md#upstream-cloud)
- [Configuration > MQTT](CONFIGURATION.md#mqtt-feed)
- [Common Errors > MQTT](COMMON-ERRORS.md#mqtt)
- [Common Errors > Cloud (Meshradar)](COMMON-ERRORS.md#cloud-meshradar)
- [FAQ > Do I have to use the Meshradar cloud?](FAQ.md#do-i-have-to-use-the-meshradar-cloud)
