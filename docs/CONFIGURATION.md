# Configuration Guide

All settings live in `config/default.yaml` with user overrides in `config/local.yaml`. The service merges both files at startup: anything in `local.yaml` overrides the default. You only need to add the settings you want to change.

Edit your local config:

```bash
sudo nano /opt/meshpoint/config/local.yaml
```

Restart after any config change: `sudo systemctl restart meshpoint`

---

## Radio

```yaml
radio:
  region: "US"                 # US, EU_868, ANZ, IN, KR, SG_923
  frequency_mhz: 906.875      # auto-configured from region
  spreading_factor: 11         # SF11 (LongFast)
  bandwidth_khz: 250.0
```

The region sets the base frequency, spreading factor, and bandwidth automatically. You only need `region` in most cases. Override `frequency_mhz`, `spreading_factor`, or `bandwidth_khz` individually to tune for non-default presets (MediumFast, ShortFast, etc.) or custom frequency slots.

### Changing Region

```yaml
radio:
  region: "EU_868"
```

To also update your MeshCore companion radio:

```bash
meshpoint meshcore-radio EU
```

Or enter a custom frequency: `meshpoint meshcore-radio custom`

See the [Onboarding Guide](ONBOARDING.md#changing-meshcore-radio-frequency) for full details.

---

## Capture Sources

```yaml
capture:
  sources:
    - concentrator             # SX1302/SX1303 LoRa concentrator
    - meshcore_usb             # optional MeshCore USB companion
  meshcore_usb:
    auto_detect: true          # scans /dev/ttyUSB* and /dev/ttyACM*
    serial_port: null           # or set explicitly: "/dev/ttyACM0"
    baud_rate: 115200
```

The setup wizard configures sources automatically. To add or remove a MeshCore companion later, edit `sources` and restart.

---

## Primary Channel Name

The primary (channel 0) name is used to compute the Meshtastic channel hash on transmitted packets. It must match the primary channel name on your mesh for outgoing messages to be heard.

```yaml
meshtastic:
  primary_channel_name: "LongFast"
```

The default is `LongFast` (Meshtastic's standard public channel). Change it only if your mesh uses a custom primary channel name. You can also edit this from the dashboard: open the **Radio** tab, edit **Channel 0**, and save. The Radio and Messages tabs reflect the same value.

---

## Private Channel Monitoring

By default, the Meshpoint decrypts traffic on the standard Meshtastic default key (`AQ==`). To also decode packets on your private channels, add the channel keys to `local.yaml`:

```yaml
meshtastic:
  channel_keys:
    MyChannel: "base64encodedPSK=="
    AnotherChannel: "anotherBase64PSK=="
```

**Finding your channel's PSK:** Open the Meshtastic app, go to the channel settings, and copy the pre-shared key (base64 format).

**Channel name must match exactly** what's configured on your Meshtastic node (case-sensitive).

The Meshpoint tries each configured key when decoding a packet. Packets matching any configured key will be fully decoded. Packets on channels with unknown keys will continue to show as ENCRYPTED.

> **MeshCore private channels:** multi-key decryption for MeshCore is on the roadmap but not yet implemented. Currently only the default MeshCore key is tried.

To change the default Meshtastic key (if your primary channel uses a non-default PSK):

```yaml
meshtastic:
  default_key_b64: "yourPrimaryKeyBase64=="
```

---

## Smart Relay

Connect a separate radio (T-Beam, Heltec, RAK4631) via USB to re-broadcast captured packets:

```yaml
relay:
  enabled: true
  serial_port: "/dev/ttyACM1"  # relay radio serial port
  serial_baud: 115200
  max_relay_per_minute: 20     # token-bucket rate limit
  burst_size: 5                # max burst before throttle
  min_relay_rssi: -110.0       # ignore weak packets
  max_relay_rssi: -50.0        # ignore local packets (too strong)
```

The relay path is independent from RX: transmission never blocks packet reception. Packets are deduplicated by ID, rate-limited, and filtered by signal strength before relay.

---

## Transmit (Native Messaging)

Enable the Meshpoint to send messages directly through the onboard SX1302 concentrator (Meshtastic) and the MeshCore USB companion (MeshCore). This powers the Messages tab on the local dashboard.

```yaml
transmit:
  enabled: false               # opt-in
  node_id: null                # auto-generated 4-byte Meshtastic node ID
  tx_power_dbm: 14             # conservative default (dBm)
  max_duty_cycle_percent: 1.0  # EU-safe default
  long_name: "Mesh Point"
  short_name: "MPNT"
  hop_limit: 3
```

**`enabled`**: must be `true` to send from the Messages tab. Disabled by default.

**`node_id`**: leave as `null` to auto-generate. Once set, do not change it: your node identity is what other nodes see and cache in their contact lists.

**`tx_power_dbm`**: 14 dBm is conservative and compliant in most regions. Raise carefully; check your regional ISM band limits before increasing.

**`max_duty_cycle_percent`**: airtime limit as a percent of wall clock. 1.0 is EU-safe (ETSI 1% duty cycle). US users with a FCC station can raise this, but sensible defaults protect the mesh from one Meshpoint hogging the channel.

**`long_name` / `short_name`**: shown to other nodes (long name in node lists, short name on compact displays). Match your naming convention.

**`hop_limit`**: initial hop count on outgoing Meshtastic messages. 3 is typical; higher values mean more relays and more airtime.

MeshCore transmission uses the USB companion node: configure its serial port under `capture.meshcore_usb` (see Capture Sources above). The companion handles encryption and RF timing; the Meshpoint sends serial commands.

---

## Upstream (Cloud)

```yaml
upstream:
  enabled: true
  url: "wss://api.meshradar.io"
  reconnect_interval_seconds: 10
  buffer_max_size: 5000        # local buffer during disconnects
  auth_token: null             # set by setup wizard
```

When enabled, the Meshpoint connects to [Meshradar](https://meshradar.io) via WebSocket and relays captured packets for aggregated mesh intelligence. The connection auto-reconnects with backoff and buffers packets locally during outages.

Disable upstream to run fully offline:

```yaml
upstream:
  enabled: false
```

---

## Storage

```yaml
storage:
  database_path: "data/concentrator.db"
  max_packets_retained: 100000
  cleanup_interval_seconds: 3600
```

Packets are stored in a local SQLite database. Old packets are pruned automatically based on `max_packets_retained`.

---

## Dashboard

```yaml
dashboard:
  host: "0.0.0.0"             # listen on all interfaces
  port: 8080
  static_dir: "frontend"
```

Access at `http://<pi-ip>:8080`. Bind to `127.0.0.1` to restrict to local access only.

---

## Device Identity

```yaml
device:
  device_name: "My Meshpoint"
  latitude: 42.3601
  longitude: -71.0589
  altitude: 25
```

Set during the setup wizard. The coordinates are used for map placement on the local dashboard and the Meshradar cloud dashboard, and as the reference point for "farthest direct node" distance.

### Updating Location

Two options:

1. Edit `local.yaml` directly (fastest):

   ```bash
   sudo nano /opt/meshpoint/config/local.yaml
   # change device.latitude / device.longitude / device.altitude
   sudo systemctl restart meshpoint
   ```

2. Re-run the setup wizard and press Enter through steps you want to keep:

   ```bash
   sudo /opt/meshpoint/venv/bin/python -m src.cli setup
   sudo systemctl restart meshpoint
   ```

**Tip**: in Google Maps, right-click any location and click the coordinates at the top of the menu to copy them in decimal format (e.g. `42.3601, -71.0589`).

---

## MQTT Feed

Publish captured packets to community MQTT brokers (meshmap.net, NHmesh.live, etc.) and Home Assistant. The Meshpoint acts as a dual-protocol MQTT gateway: both Meshtastic and MeshCore traffic can be published from a single device.

### Privacy: Two-Gate Safety Model

MQTT publishing uses two independent safety gates to prevent accidental exposure of private data:

**Gate 1: Global kill switch.** MQTT is off by default. You must explicitly set `mqtt.enabled: true` to activate publishing. Nothing is ever sent to any MQTT broker unless you opt in.

**Gate 2: Channel allowlist.** Only packets from channels listed in `publish_channels` are published. The default list contains only `LongFast` (the standard Meshtastic public channel). Private channels, custom PSK channels, and encrypted packets are never published unless you deliberately add that channel name to the list.

Both gates must pass for any packet to leave the device via MQTT. Encrypted packets (those the Meshpoint could not decrypt) are always blocked regardless of channel configuration.

This two-gate approach is informed by active community discussion around MQTT privacy, including the need for explicit opt-in controls ([meshtastic/firmware#5507](https://github.com/meshtastic/firmware/issues/5507)), concerns about private channel data leaking via MQTT gateways ([meshtastic/firmware#5404](https://github.com/meshtastic/firmware/issues/5404)), and the broader push for user-controlled MQTT publishing ([meshtastic/firmware#3549](https://github.com/meshtastic/firmware/issues/3549)).

### Basic Setup

```yaml
mqtt:
  enabled: true
  broker: "mqtt.meshtastic.org"
  port: 1883
  username: "meshdev"
  password: "large4cats"
  region: "US"
  publish_channels:
    - "LongFast"
```

This publishes standard Meshtastic and MeshCore traffic to the community broker. Your Meshpoint appears on community maps (meshmap.net, Liam Cottle, NHmesh) with a unique gateway ID that integrates natively with the Meshtastic ecosystem.

### Configuration Options

```yaml
mqtt:
  enabled: false                 # Gate 1: must be true to publish
  broker: "mqtt.meshtastic.org"  # broker hostname
  port: 1883                     # broker port
  username: "meshdev"            # broker credentials
  password: "large4cats"
  topic_root: "msh"             # MQTT topic prefix
  region: "US"                   # used in topic path
  publish_channels:              # Gate 2: only these channels are published
    - "LongFast"
  publish_json: false            # also publish JSON on /json/ topic
  location_precision: "exact"    # exact | approximate | none
  homeassistant_discovery: false # publish HA auto-discovery configs
```

### Location Precision

Control how much location detail leaves the device via MQTT:

| Value | Behavior |
|---|---|
| `exact` | Full GPS coordinates (default) |
| `approximate` | Rounded to ~1.1km precision (2 decimal places) |
| `none` | Location stripped entirely from MQTT messages |

Full-precision location data is always available on the [Meshradar](https://meshradar.io) dashboard regardless of this setting.

### Home Assistant Integration

Enable JSON publishing and HA auto-discovery to automatically create sensors in Home Assistant for battery level, temperature, and GPS position of mesh nodes:

```yaml
mqtt:
  enabled: true
  publish_json: true
  homeassistant_discovery: true
```

HA sensors appear as `sensor.meshpoint_<node_id>_battery`, `sensor.meshpoint_<node_id>_temperature`, and `device_tracker.meshpoint_<node_id>`.

### Publishing Private Channels

If you want to publish traffic from a private channel (for example, to feed it into your own HA instance on a local broker), add the channel name to `publish_channels` and point the broker to your local MQTT server:

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

Never add private channel names when publishing to a public broker.

---

## Full Default Config

See [config/default.yaml](../config/default.yaml) for all available settings and their defaults.
