# Mesh Point

**Turn a Raspberry Pi into a gateway-grade LoRa mesh intelligence node.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Platform: Raspberry Pi](https://img.shields.io/badge/platform-Raspberry%20Pi%204-red.svg)](https://www.raspberrypi.com/)

![Mesh Point Dashboard](Meshpoint%20DB.png)

---

## What Is a Mesh Point?

A Mesh Point is not another node on the mesh -- it's a **passive intelligence layer** that sits above the network and watches everything.

While a standard Meshtastic or Meshcore node uses a single-channel SX1276/SX1262 radio, a Mesh Point uses the **SX1302 LoRa concentrator** -- the same chip found inside commercial LoRaWAN gateways. This gives it capabilities no ordinary node has:

| | Standard Node | Mesh Point |
|---|---|---|
| **Simultaneous channels** | 1 | 8 |
| **Demodulators** | 1 | 16 (multi-SF) |
| **Role** | Participant | Observer + Relay |
| **Packet visibility** | Own traffic | All traffic in range |
| **Data persistence** | None | SQLite with retention |
| **Dashboard** | None | Real-time local web UI |
| **Upstream reporting** | None | WebSocket to Mesh Radar |

Every packet that hits the antenna gets captured, decoded, stored locally, displayed on a real-time dashboard, and optionally shipped upstream to [Mesh Radar](https://meshradar.io) for city-wide mesh intelligence.

---

## Why Run One?

- **See everything.** Every text message, position report, telemetry beacon, and routing packet in range -- across all spreading factors simultaneously.
- **Map the mesh.** Discover nodes you never knew existed, track signal quality over time, find coverage dead zones.
- **Relay for the community.** Optional smart relay re-broadcasts packets via a separate SX1262 radio with built-in deduplication and rate limiting.
- **Contribute to Mesh Radar.** Feed your local data upstream to build a shared, city-wide picture of mesh network health and coverage.
- **Build real RF infrastructure.** Because running a passive LoRa intelligence node from your rooftop is the kind of project you were born to do.

---

## Architecture

```
                                    ┌─────────────────────────────────┐
                                    │        Mesh Radar Cloud         │
                                    │       (meshradar.io)            │
                                    │  Aggregated map, analytics,     │
                                    │  fleet management, alerts       │
                                    └──────────────┬──────────────────┘
                                                   │ WebSocket
                                                   │
┌──────────┐    ┌──────────┐    ┌──────────────────┴──────────────────┐
│  LoRa    │    │ RAK2287  │    │          Mesh Point (Pi 4)          │
│ Packets  │───▶│ SX1302   │───▶│                                     │
│ (OTA)    │    │ 8-ch RX  │    │  Capture ─▶ Decode ─▶ Store ─▶ API │
└──────────┘    └──────────┘    │     │                    │          │
                                │     ▼                    ▼          │
                                │  HAL/SPI            Dashboard      │
                                │  (libloragw)        (port 8080)    │
                                │                          │          │
                                │  ┌───────────┐          │          │
                                │  │ SX1262 TX │◀── Relay ─┘          │
                                │  │ (optional)│   (dedup + ratelimit)│
                                │  └───────────┘                      │
                                └─────────────────────────────────────┘
```

---

## Hardware

### Bill of Materials

| Component | Description | Approx. Price |
|-----------|-------------|---------------|
| Raspberry Pi 4 Model B | 1GB RAM is sufficient | $35 |
| RAK2287 Concentrator | SX1302 + SX1250 + ZOE-M8Q GPS | $80 |
| RAK2287 Pi HAT | Adapter board for Pi GPIO/SPI | $25 |
| LoRa Antenna | 860-930 MHz, 10dBi recommended | $15 |
| MicroSD Card | 32GB (SanDisk Extreme recommended) | $10 |
| USB-C Power Supply | 5.1V / 3A (official Pi PSU recommended) | $10 |
| **Optional:** SX1262 Radio | For relay TX (T-Beam, Heltec, RAK4631) | $25-40 |
| | **Total** | **~$175-215** |

### Assembly

1. Seat the RAK2287 module onto the Pi HAT
2. Mount the Pi HAT onto the Raspberry Pi 4 GPIO header
3. Connect the LoRa antenna to the U.FL connector on the RAK2287
4. Insert the microSD card and connect power

> **Important:** Always connect the antenna before powering on. Operating the SX1302 without an antenna can damage the RF front-end.

---

## Quick Start

### 1. Flash the Pi

Download [Raspberry Pi OS Lite (64-bit)](https://www.raspberrypi.com/software/) and flash it to your SD card. Enable SSH and configure WiFi during imaging.

### 2. Install

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/KMX415/meshpoint.git ~/meshpoint
cd ~/meshpoint
sudo bash scripts/install.sh
```

The installer handles everything:
- Enables SPI and I2C interfaces
- Builds the SX1302 HAL (`libloragw`) with Meshtastic patches
- Creates a Python virtual environment with all dependencies
- Installs the `meshpoint` CLI and systemd service

### 3. Configure

```bash
meshpoint setup
```

The interactive wizard walks you through:
- Hardware detection (SPI concentrator, serial radios)
- Capture source selection
- Upstream API key (get one free at [meshradar.io](https://meshradar.io))
- Device name and location
- Optional relay radio configuration

### 4. Verify

```bash
meshpoint status
```

```
  Mesh Point Status
  ========================================
  Service:         running
  Config:          config/local.yaml
  Device ID:       a0eefe43-9b51-4735-a0a4-47c3ca16580c
  Dashboard:       http://localhost:8080
  Relay:           disabled
  Name:            My Mesh Point
  Location:        42.3601, -71.0589
```

Open `http://<pi-ip>:8080` in your browser to see the local dashboard.

---

## How It Works

### SX1302 Multi-Channel Reception

The RAK2287 concentrator listens on 8 LoRa channels simultaneously using the SX1302's 16 multi-SF demodulators. Unlike a standard single-channel node, it can receive packets on any spreading factor (SF7-SF12) across the entire channel plan at the same time.

The HAL is patched for Meshtastic compatibility -- the core modules handle sync word configuration and hardware initialization automatically.

### Protocol Decoding

Captured packets are routed through protocol-specific decoders that handle header parsing, decryption, and payload extraction for both Meshtastic and Meshcore protocols. Decoded data is stored locally and streamed to connected dashboards.

### Smart Relay

When a separate SX1262-based radio is connected (via USB serial), the Mesh Point can intelligently re-broadcast received packets:

- **Deduplication**: Tracks recently-seen packet IDs to avoid re-relaying duplicates
- **Rate limiting**: Token bucket algorithm prevents flooding (configurable burst size and sustained rate)
- **Signal filtering**: Only relays packets within a configurable RSSI window
- **Separate TX path**: The relay radio is independent from the concentrator, so transmission never blocks reception

---

## Configuration

All settings live in `config/default.yaml`. User overrides go in `config/local.yaml` (created by the setup wizard, not tracked by git).

### Key Settings

```yaml
radio:
  frequency_mhz: 906.875      # US915 Meshtastic default
  spreading_factor: 11         # SF11 (LongFast)
  bandwidth_khz: 250.0

capture:
  sources:
    - concentrator             # Use SX1302 hardware
  concentrator_spi_device: "/dev/spidev0.0"

relay:
  enabled: false               # Enable with SX1262 radio attached
  max_relay_per_minute: 20
  burst_size: 5

upstream:
  enabled: true
  url: "wss://api.meshradar.io/ws"
  auth_token: null             # Set via meshpoint setup or local.yaml
```

### Regional Configuration

The default config targets US915. For EU868 or other regions, update `radio.frequency_mhz` and the concentrator channel plan.

---

## Local API

The Mesh Point runs a FastAPI server on port 8080 with these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/nodes` | GET | List all discovered nodes |
| `/api/nodes/map` | GET | Nodes with GPS coordinates for map display |
| `/api/nodes/count` | GET | Total discovered node count |
| `/api/packets` | GET | Recent captured packets (with pagination) |
| `/api/analytics/traffic` | GET | Traffic rates and packet counts |
| `/api/analytics/signal/rssi` | GET | RSSI distribution and signal stats |
| `/api/device/status` | GET | Device health, uptime, config summary |
| `/ws` | WebSocket | Real-time packet stream |

---

## Mesh Radar Cloud

[Mesh Radar](https://meshradar.io) is the cloud platform that aggregates data from all deployed Mesh Points into a unified picture of mesh network activity across a city or region.

**What you get:**
- Live map of all Mesh Points and discovered nodes across the network
- Connection lines showing which Mesh Points hear which nodes
- Aggregated signal analytics and network health metrics
- Fleet management with remote command capability

**Free tier** includes real-time map view and basic node discovery. Create an account at [meshradar.io](https://meshradar.io) to get your API key.

---

## Managing Your Mesh Point

```bash
meshpoint status          # Service status, config, connection info
meshpoint logs            # Tail the service journal
meshpoint restart         # Restart the service
meshpoint stop            # Stop the service
meshpoint setup           # Re-run the configuration wizard
```

### Updating

```bash
cd ~/meshpoint
git pull
sudo cp -r src/ /opt/meshpoint/src/
sudo cp -r frontend/ /opt/meshpoint/frontend/
sudo find /opt/meshpoint -name "*.pyc" -delete
sudo systemctl restart meshpoint
```

> **Note:** Updates to the open-source framework won't overwrite compiled core modules. Core updates are distributed separately when new versions are available.

---

## Project Structure

```
src/
  capture/          # Packet sources (concentrator, serial, mock)
  decode/           # Protocol decoders (stubs -- core required)
  storage/          # SQLite persistence (packets, nodes, telemetry)
  analytics/        # Signal analysis, traffic monitoring, network mapping
  api/              # FastAPI server, REST routes, WebSocket
  relay/            # Smart relay (dedup, rate limiting, SX1262 TX)
  hal/              # SX1302 hardware abstraction (stubs -- core required)
  models/           # Data models (Packet, Node, Signal, Telemetry)
  cli/              # meshpoint CLI (setup wizard, status, logs)
frontend/           # Local dashboard (Leaflet map, Chart.js, live packet feed)
config/             # YAML configuration (default + local override)
scripts/            # Installer, systemd service, core installer
tests/              # Unit tests
```

---

## Troubleshooting

### Service won't start
```bash
meshpoint logs                    # Check for errors
sudo journalctl -u meshpoint -n 50  # More context
```

### "meshpoint-core is required"
The compiled core modules are not installed. Run:
```bash
sudo bash scripts/install_core.sh /path/to/meshpoint-core.tar.gz
```

### Chip version 0x00
The concentrator isn't responding. Check:
- RAK2287 is firmly seated on the Pi HAT
- SPI is enabled (`sudo raspi-config` > Interface Options > SPI)
- Try a full power cycle (unplug, wait 10s, plug back in)

### No packets received
- Verify antenna is connected
- Confirm frequency matches your region's Meshtastic channel plan
- Check `meshpoint logs` for `lgw_receive returned N packet(s)`
- The blue RX LED on the RAK2287 blinks on packet reception

### Upstream connection fails
- Verify your API key in `config/local.yaml`
- Check `meshpoint logs` for WebSocket errors (401 = bad key, timeout = network issue)

---

## Contributing

Contributions to the open-source framework are welcome! The API server, dashboard, analytics, storage, and relay modules are fully open. Protocol decoding and hardware abstraction are distributed as compiled modules.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

For bug reports and feature requests, open an issue.

---

## License

This project is licensed under the MIT License -- see [LICENSE](LICENSE) for details.

The compiled core modules (`meshpoint-core`) are proprietary and distributed separately under a commercial license.

---

## Acknowledgments

- [Meshtastic](https://meshtastic.org) -- the open-source LoRa mesh project that makes all this possible
- [Semtech SX1302](https://www.semtech.com/products/wireless-rf/lora-core/sx1302) -- the concentrator chip
- [RAKwireless](https://www.rakwireless.com) -- RAK2287 module and Pi HAT
- [sx1302_hal](https://github.com/Lora-net/sx1302_hal) -- Semtech's open-source HAL

---

*Built by [Mesh Radar](https://meshradar.io) -- city-wide mesh intelligence.*
