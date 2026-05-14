# Meshpoint Onboarding Guide

Step-by-step instructions for building and deploying a Meshpoint: from an empty Raspberry Pi to a fully operational node feeding data to the Meshradar cloud platform.

---

## What You're Building

A **Meshpoint** is an edge device that:

- Listens to **Meshtastic** traffic on 8 LoRa channels simultaneously via an SX1302/SX1303 concentrator
- **Sends and receives Meshtastic messages** directly from the browser dashboard (native TX via the concentrator)
- Optionally monitors **MeshCore** traffic via a USB companion radio
- Decodes, stores, and visualizes packets on a real-time dashboard with full chat UI, node discovery, and radio configuration
- Ships data upstream to the [Meshradar](https://meshradar.io) cloud platform for regional mesh intelligence

## Hardware Requirements

You need a Raspberry Pi 4 with an SX1302 or SX1303 LoRa concentrator. The easiest paths are buying a pre-built unit (RAK Hotspot V2 or SenseCap M1) and reflashing the SD card.

| Component | Purpose | Notes |
|-----------|---------|-------|
| **Raspberry Pi 4** (1-2GB RAM) | Host computer | 1GB works, 2GB recommended for future updates |
| **SX1302/SX1303 Concentrator** | Multi-channel LoRa RX + TX | RAK2287 (SX1302) or Seeed WM1303 (SX1303) |
| **Carrier board / Pi HAT** | Mounts the concentrator to the Pi | RAK Pi HAT, SenseCap M1 carrier, or WM1302 Pi HAT |
| **microSD card** (32GB) | Boot drive | Class 10 or better |
| **USB-C power supply** (5V 3A) | Power | Official Pi PSU recommended |
| **LoRa antenna** (906 MHz) | RX + TX | 10 dBi gain recommended for US915 band |
| **Ethernet cable or WiFi** | Network connectivity | Needed for cloud uplink |
| **Optional: MeshCore USB companion** | MeshCore traffic monitor | Heltec V3/V4 or T-Beam with [USB companion firmware](https://flasher.meshcore.co.uk/) |

### Supported Pre-Built Units

| Unit | Concentrator | Price Range | Notes |
|------|-------------|-------------|-------|
| **RAK Hotspot V2** (RAK7248) | RAK2287 (SX1302) | $30-70 on eBay | Pi 4 + metal enclosure + antenna, usually 32GB SD card (more than enough for our usage) |
| **SenseCap M1** | WM1303 (SX1303) | $30-60 on eBay | Pi 4 + metal enclosure + antenna, may include 64GB SD card |

> **RAK2287 vs SenseCap M1:** The RAK2287's SPI bus can latch if power is cut while the concentrator is active. The Meshpoint service includes a GPIO reset script that holds the concentrator in reset during shutdown, making `sudo reboot` and `sudo systemctl restart meshpoint` safe. However, hard power loss (yanked cable, power outage) can still latch the SPI bus — requiring a full power unplug (10+ seconds) to clear. Repeated hard power loss can permanently damage the SX1250 radio. The SenseCap M1 does not have this issue. For deployments with unreliable power, the **SenseCap M1 is recommended**, or add a small UPS (PiSugar, USB battery with passthrough).

RAK Hotspot V2: remove 4 bottom screws to access the SD card. SenseCap M1: remove 2 screws on the back panel (opposite the Ethernet/antenna ports) -- the SD card may be held down with kapton tape.

## Prerequisites

- A computer with an SD card reader (for flashing)
- SSH client (PuTTY on Windows, or built-in terminal on Mac/Linux)
- A [Meshradar](https://meshradar.io) account (free: create one before starting)

---

## DIY Setup (Building Your Own)

### Step 1: Flash Raspberry Pi OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/) on your computer.

2. Insert the microSD card.

3. Open Raspberry Pi Imager and choose:
   - **OS**: Raspberry Pi OS Lite (64-bit) -- the headless version without a desktop
   - **Storage**: Your microSD card

4. Click the gear icon (or Ctrl+Shift+X) to open **Advanced Options**:
   - **Enable SSH**: Check the box, select "Use password authentication"
   - **Set username and password**: Choose a username (e.g. `pi`) and a strong password
   - **Configure WiFi** (if not using Ethernet): Enter your SSID and password
   - **Set locale**: Choose your timezone and keyboard layout

5. Click **Write** and wait for it to finish.

6. Insert the SD card into the Raspberry Pi. Do **not** power it on yet.

> **Enclosed units:** RAK Hotspot V2 -- remove 4 bottom screws. SenseCap M1 -- remove 2 screws on the back panel (opposite the Ethernet/antenna ports); SD card may be taped down with kapton tape. After flashing, re-insert the card and reassemble.

### Step 2: Assemble Hardware

**If using a pre-built unit (RAK Hotspot V2 or SenseCap M1):** The concentrator is already seated. Just connect the LoRa antenna to the SMA connector and insert the flashed SD card. For SenseCap M1, USB-C power plugs into the carrier board (not the Pi's own USB-C port).

**If building from parts:**

1. Seat the concentrator module (RAK2287 or WM1303) into the mPCIe slot on the carrier board.
2. Connect the LoRa antenna to the SMA port. **Never power the concentrator without an antenna connected** -- this can damage the radio.
3. If your carrier board has a GPS module and you have a GPS antenna, connect it to the u.FL connector.
4. Mount the carrier board onto the Raspberry Pi's GPIO header.
5. If using a MeshCore USB companion, connect it to one of the Pi's USB ports.
6. Connect Ethernet (if not using WiFi).
7. Connect the power supply.

### Step 3: Find the Pi on Your Network

The Pi should boot and connect to your network within 1-2 minutes.

**Option A: Check your router's DHCP client list** for a device named `raspberrypi` (or whatever hostname you set).

**Option B: Use `nmap` from your computer:**

```bash
nmap -sn 192.168.1.0/24
```

Replace `192.168.1.0/24` with your local subnet.

### Step 4: SSH into the Pi

```bash
ssh pi@<your-pi-ip-address>
```

Enter the password you set during imaging.

### Step 5: Clone and Install

```bash
sudo apt update && sudo apt install -y git
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
sudo bash /opt/meshpoint/scripts/install.sh
```

The install script handles everything: system packages, SPI/UART/GPS kernel configuration, building the LoRa concentrator driver with Meshtastic TX patches, Python virtual environment, dependencies, systemd service, and permissions setup.

This takes 5-15 minutes depending on your internet speed and Pi model.

### Step 6: Reboot

The SPI and UART kernel changes require a reboot:

```bash
sudo reboot
```

Wait 30-60 seconds, then SSH back in.

### Step 7: Get Your API Key

1. Go to [meshradar.io](https://meshradar.io) in your browser
2. Sign up and verify your email
3. Go to **Account > API Keys**
4. Click **Generate New Key**
5. **Copy the key immediately** -- it is only shown once

### Step 8: Run the Setup Wizard

```bash
sudo meshpoint setup
```

> **Note:** `sudo` is required — the wizard writes to `/opt/meshpoint/config/local.yaml` which is owned by root.

The wizard walks you through these steps:

1. **Hardware Detection** -- probes for concentrator, carrier board, GPS, serial radios, USB MeshCore devices
2. **Frequency Region** -- select your Meshtastic region (US, EU_868, ANZ, IN, KR, SG_923). The concentrator auto-tunes to the correct frequency
3. **Capture Source** -- auto-selects concentrator, serial, or mock. If a MeshCore USB companion is detected, offers to enable it and configure its radio frequency to match your region
4. **MQTT** -- optional MQTT publishing to community brokers and Home Assistant
5. **API Key** -- paste your Meshradar API key
6. **Device Name** -- give it a recognizable name (e.g. "Meshpoint Rooftop")
7. **Location** -- use GPS fix or enter lat/lng manually (right-click Google Maps to copy)
8. **Node Identity** -- a unique random Meshtastic node ID, long name, and short name are auto-generated. You can customize these later from the Radio settings page on the dashboard
9. **Device ID** -- auto-generated unique identifier for cloud registration

The wizard writes `config/local.yaml` and offers to start the service.

> **After setup:** TX is disabled by default. Enable it from the dashboard Radio settings page once you've verified RX is working.

### Step 9: Verify It's Working

```bash
meshpoint status
```

Check the local dashboard at `http://<your-pi-ip>:8080`. You should see:
- **Map** showing your device's location and discovered nodes
- **Packet feed** with live Meshtastic and MeshCore traffic (once LoRa devices are in range)
- **Messaging tab** for sending and receiving Meshtastic messages (enable TX in Radio settings first)
- **Nodes grid** with cards for every discovered node: name, signal, hardware, battery
- **Radio settings** page to configure region, modem preset, frequency, TX, and channels
- **Signal charts** and traffic analytics
- **System metrics**: CPU, RAM, disk, temperature

Check the cloud dashboard at [meshradar.io](https://meshradar.io). Your Meshpoint should appear as a green dot in the fleet view within a minute.

---

## Adding a MeshCore Companion (Optional)

A MeshCore USB companion gives your Meshpoint the ability to monitor MeshCore mesh traffic alongside Meshtastic. It's a single-channel radio that listens on one frequency -- all standard MeshCore traffic in your region uses the same frequency, so the regional preset covers everything.

### What You Need

A Heltec or T-Beam board flashed with **USB Serial Companion** firmware. Supported devices include:

| Device | Notes |
|--------|-------|
| Heltec LoRa V3 | ESP32-S3, common and inexpensive |
| Heltec LoRa V4 / V4 OLED | ESP32-S3, latest Heltec revision |
| LilyGo T-Beam | ESP32, includes GPS |
| Heltec Wireless Tracker | ESP32-S3, includes GPS and display |

### Step 1: Flash USB Companion Firmware

1. Go to [flasher.meshcore.co.uk](https://flasher.meshcore.co.uk/) in a Chrome or Edge browser
2. Select your device model
3. Choose the **`companion_radio_usb`** firmware variant (not BLE)
4. Connect the device via USB and click Flash

> **Important:** The USB companion firmware disables Bluetooth. Radio parameters (frequency, bandwidth, etc.) can only be configured over serial -- either through the Meshpoint setup wizard or manually via Python. The setup wizard handles this automatically.

### Step 2: Plug Into the Pi and Run Setup

1. Connect the flashed device to any USB port on the Raspberry Pi
2. Run the setup wizard:

```bash
sudo meshpoint setup
```

3. The wizard detects the MeshCore device and asks if you want to enable monitoring
4. The wizard auto-configures the companion's radio frequency based on your selected region:

| Region | Frequency | BW | SF | CR |
|--------|-----------|-----|-----|-----|
| US | 910.525 MHz | 62.5 kHz | 7 | 5 |
| EU | 869.618 MHz | 62.5 kHz | 8 | 8 |
| ANZ | 916.575 MHz | 62.5 kHz | 7 | 8 |

Other regions prompt for custom frequency entry. You can also change the MeshCore radio frequency anytime with `meshpoint meshcore-radio`.

5. The wizard sets the radio parameters, reboots the companion, and verifies the new settings

After setup, both capture sources start automatically on boot. You'll see them in the startup banner:

```
Source  concentrator (SX1302), MeshCore USB node
```

### Changing MeshCore Radio Frequency

To switch the MeshCore companion to a different region without re-running the full setup wizard:

```bash
meshpoint meshcore-radio         # interactive menu (US, EU, ANZ, Custom)
meshpoint meshcore-radio EU      # apply EU preset directly
meshpoint meshcore-radio custom  # enter manual frequency/BW/SF/CR
```

The command auto-detects the USB port, stops the service, configures the radio, waits for the companion to reboot, updates the config if the USB port changed, and restarts the service.

### How It Differs from the Concentrator

| | SX1302/SX1303 Concentrator | MeshCore USB Companion |
|---|---|---|
| **Protocol** | Meshtastic | MeshCore |
| **Direction** | RX + TX (native) | RX + TX (via companion) |
| **Channels** | 8 simultaneous | 1 |
| **Spreading factors** | SF7-SF12 all at once | Fixed (SF7 default) |
| **Connection** | SPI (internal HAT) | USB serial |
| **Configuration** | Dashboard Radio settings | Region preset via wizard |

---

## Pre-Provisioned Device (Received from Someone)

If you received a pre-built Meshpoint, all the software is already configured. You just need to set it up physically.

### What's in the Box

- Raspberry Pi 4 with LoRa concentrator HAT mounted (RAK2287 or WM1303)
- LoRa antenna
- USB-C power supply
- microSD card (already inserted and configured)

### Setup

1. **Connect the antenna** to the gold SMA connector on the HAT. Do this BEFORE powering on.
2. **Plug in the Ethernet cable** (if provided) or the device is pre-configured for your Wi-Fi.
3. **Plug in the USB-C power supply.**

The device will boot in about 60 seconds and start capturing LoRa packets automatically.

> **Shutting down:** If you ever need to unplug the device, **always** run `sudo poweroff` first (via SSH) and wait for the green LED to stop blinking. Never yank the power cable while the Pi is running -- this can corrupt the SD card and permanently damage the concentrator radio.

### Accessing Your Local Dashboard

Once the device is on your network, open a browser and go to:

```
http://<device-ip>:8080
```

To find the device IP, check your router's DHCP client list for the device name (e.g. "meshpoint-nyc").

### What You'll See

- **Packet Feed** -- real-time Meshtastic and MeshCore packets from your area
- **Messaging** -- send and receive messages on the mesh (if TX is enabled)
- **Node Cards** -- every discovered node with name, signal, hardware, battery
- **Node Map** -- discovered mesh nodes plotted on a map
- **Radio Settings** -- configure region, modem preset, frequency, TX, and channels
- **Signal Charts** -- RSSI distribution and traffic over time
- **Device Metrics** -- CPU, RAM, disk usage, temperature

The device also sends data to the Meshradar cloud platform. Your device operator can see your Meshpoint status and metrics from the cloud dashboard.

### Troubleshooting

- **No packets appearing**: Make sure the antenna is connected and there are Meshtastic/Meshcore devices transmitting in your area.
- **Can't find the device on your network**: Check your router for the device hostname, or try `nmap -sn 192.168.1.0/24` from your computer.
- **Dashboard not loading**: Wait 60 seconds after power-on for the service to fully start.

---

## Managing Your Meshpoint

### CLI Commands

| Command | Description |
|---------|-------------|
| `meshpoint status` | Show device health, uptime, and connection status |
| `meshpoint logs` | Tail the live service logs |
| `meshpoint report` | Full operational report: traffic, signal, system metrics |
| `meshpoint restart` | Restart the service (applies config changes) |
| `meshpoint stop` | Stop the service |
| `meshpoint meshcore-radio` | Configure MeshCore companion radio frequency |
| `sudo meshpoint setup` | Re-run the setup wizard (overwrites config) |
| `meshpoint version` | Print firmware version |
| `sudo poweroff` | Shut down safely before unplugging power |

> **Always shut down before unplugging.** Run `sudo poweroff` and wait for the green LED to stop before pulling the cable. Reboots (`sudo reboot`) are safe.

### Editing Configuration

Most settings can now be changed from the **Radio settings** page on the dashboard: region, modem preset, frequency, TX power, channels, and node identity. Changes save to `local.yaml` automatically.

For advanced settings not exposed in the UI, edit the file directly:

```bash
sudo nano /opt/meshpoint/config/local.yaml
meshpoint restart
```

Default settings are in `config/default.yaml`: do not edit that file.

### Updating

```bash
cd /opt/meshpoint
sudo git pull origin main
sudo systemctl restart meshpoint
```

The local dashboard shows an orange update indicator when a new version is available on GitHub.

### Updating to v0.6.0 (one-time steps)

v0.6.0 adds native TX support, which requires a one-time HAL recompile and two config files. Run these after `git pull`:

```bash
cd /opt/meshpoint
sudo git pull origin main
sudo bash /opt/meshpoint/scripts/patch_hal.sh
sudo cp config/sudoers-meshpoint /etc/sudoers.d/meshpoint
sudo chmod 440 /etc/sudoers.d/meshpoint
sudo cp scripts/meshpoint.service /etc/systemd/system/meshpoint.service
sudo systemctl daemon-reload
sudo systemctl restart meshpoint
```

`patch_hal.sh` patches the concentrator HAL for Meshtastic-compatible TX sync words and recompiles (about 2 minutes). The sudoers rule allows the dashboard to restart the service when you change settings. The updated service file auto-fixes config directory permissions on startup. All one-time: future updates go back to `git pull` + `restart`.

A reboot ensures all changes take effect cleanly (kernel modules, SPI state, MeshCore companion). Reboots are safe: the systemd service holds the concentrator in reset during shutdown to prevent SPI bus latch.

**If the concentrator fails to start** with `lgw_start() failed` or `Failed to set SX1250_0 in STANDBY_RC mode`, the SPI bus latched due to a hard power cut. Fix it with a full power cycle:

```bash
sudo poweroff
```

Wait for the green LED to stop blinking, then unplug for 10+ seconds and plug back in.

**Important:** Always shut down gracefully with `sudo poweroff` before unplugging. Hard power cuts (yanked cable, power outage) can corrupt the SD card and latch the RAK2287's SPI bus. Repeated hard power loss can permanently damage the SX1250 radio.

For troubleshooting, corrupted install recovery, and pip issues, see [Troubleshooting](TROUBLESHOOTING.md).

---

## Network Architecture

```
   Your Meshpoint (Raspberry Pi)
   ┌──────────────────────────────────┐
   │  SX1302/SX1303 (SPI)              │
   │    ├─ Meshtastic RX (8 ch)       │
   │    └─ Meshtastic TX (native)     │
   │  MeshCore companion (USB serial)  │
   │    └─ MeshCore RX + TX           │
   │  ZOE-M8Q GPS (UART)              │
   │    └─ Device positioning         │
   │                                  │
   │  Meshpoint Software               │
   │    ├─ Dual-protocol capture      │
   │    ├─ Protocol decoding          │
   │    ├─ Chat UI + messaging        │
   │    ├─ Radio config dashboard     │
   │    ├─ Node discovery             │
   │    ├─ Local SQLite storage       │
   │    ├─ Local web dashboard        │
   │    └─ WebSocket upstream ────────┼── meshradar.io
   └──────────────────────────────────┘       │
                                              ▼
                                       Cloud Dashboard
                                       (all Meshpoints
                                        aggregated on
                                        a shared map)
```

Each Meshpoint operates independently with its own local dashboard. When connected to the cloud, all Meshpoints contribute to a shared regional view where you can see every node and Meshpoint across the network.
