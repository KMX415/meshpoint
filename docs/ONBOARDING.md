# Mesh Point Onboarding Guide

Step-by-step instructions for building and deploying a Mesh Point -- from an empty Raspberry Pi to a fully operational node feeding data to the Mesh Radar cloud platform.

---

## What You're Building

A **Mesh Point** is an edge device that:

- Listens to LoRa traffic from Meshtastic and Meshcore networks using an SX1302/SX1303 concentrator
- Decodes, stores, and visualizes packets on a local dashboard
- Optionally relays packets back onto the mesh via a separate SX1262 radio
- Ships data upstream to the Mesh Radar cloud platform for regional mesh intelligence

## Hardware Requirements

You need a Raspberry Pi 4 with an SX1302 or SX1303 LoRa concentrator. The easiest paths are buying a pre-built unit (RAK Hotspot V2 or SenseCap M1) and reflashing the SD card.

| Component | Purpose | Notes |
|-----------|---------|-------|
| **Raspberry Pi 4** (1-2GB RAM) | Host computer | 1GB works, 2GB recommended for future updates |
| **SX1302/SX1303 Concentrator** | Multi-channel LoRa receiver | RAK2287 (SX1302) or Seeed WM1303 (SX1303) |
| **Carrier board / Pi HAT** | Mounts the concentrator to the Pi | RAK Pi HAT, SenseCap M1 carrier, or WM1302 Pi HAT |
| **microSD card** (32GB) | Boot drive | Class 10 or better |
| **USB-C power supply** (5V 3A) | Power | Official Pi PSU recommended |
| **LoRa antenna** (906 MHz) | Reception | 10 dBi gain recommended for US915 band |
| **Ethernet cable or WiFi** | Network connectivity | Needed for cloud uplink |
| **Optional: SX1262 radio** | Relay transmitter | T-Beam, Heltec V3, or RAK4631 running Meshtastic firmware |

### Supported Pre-Built Units

| Unit | Concentrator | Price Range | Notes |
|------|-------------|-------------|-------|
| **RAK Hotspot V2** (RAK7248) | RAK2287 (SX1302) | $30-70 on eBay | Pi 4 + metal enclosure + antenna |
| **SenseCap M1** | WM1303 (SX1303) | $30-60 on eBay | Pi 4 + metal enclosure + antenna, may include 64GB SD card |

> **RAK2287 vs SenseCap M1 — important difference for remote deployments:** The RAK2287's SPI bus can latch in a stuck state after a service restart or unexpected power loss. When this happens, the concentrator will not reinitialize and **a clean `sudo reboot` will not fix it** — only a full power unplug (10+ seconds) clears the SPI bus. Repeated SPI latch events (from frequent power outages or hard shutdowns) can permanently damage the SX1250 radio front-end — the concentrator may start but silently fail to receive packets. The SenseCap M1 does not have this issue and handles service restarts and power loss cleanly. If you are deploying a Mesh Point in a location where you cannot physically access it (rooftop, remote site) or where power is unreliable, the **SenseCap M1 is strongly recommended**.

RAK Hotspot V2: remove 4 bottom screws to access the SD card. SenseCap M1: remove 2 screws on the back panel (opposite the Ethernet/antenna ports) -- the SD card may be held down with kapton tape.

## Prerequisites

- A computer with an SD card reader (for flashing)
- SSH client (PuTTY on Windows, or built-in terminal on Mac/Linux)
- A [Mesh Radar](https://meshradar.io) account (free -- create one before starting)

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
5. If using an SX1262 relay radio, connect it to one of the Pi's USB ports.
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
cd /opt/meshpoint
sudo ./scripts/install.sh
```

The install script handles everything: system packages, SPI/UART/GPS kernel configuration, building the LoRa concentrator driver, Python virtual environment, dependencies, and systemd service installation.

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

The wizard walks you through 7 steps:

1. **Hardware Detection** -- probes for concentrator, carrier board, GPS, serial radios
2. **Capture Source** -- auto-selects concentrator, serial, or mock
3. **API Key** -- paste your Mesh Radar API key
4. **Device Name** -- give it a recognizable name (e.g. "Mesh Point Rooftop")
5. **Location** -- use GPS fix or enter lat/lng manually (right-click Google Maps to copy)
6. **Relay Radio** -- configure optional SX1262 relay
7. **Device ID** -- auto-generated unique identifier

The wizard writes `config/local.yaml` and offers to start the service.

### Step 9: Verify It's Working

```bash
meshpoint status
```

Check the local dashboard at `http://<your-pi-ip>:8080`. You should see:
- A map showing your device's location
- Live packet feed (once LoRa traffic is in range)
- Signal strength charts
- CPU, RAM, disk, and temperature metrics

Check the cloud dashboard at [meshradar.io](https://meshradar.io). Your Mesh Point should appear as a green dot in the fleet view within a minute.

---

## Pre-Provisioned Device (Received from Someone)

If you received a pre-built Mesh Point, all the software is already configured. You just need to set it up physically.

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

- **Live Packet Feed** -- real-time Meshtastic and Meshcore packets from your area
- **Node Map** -- discovered mesh nodes plotted on a map
- **Signal Charts** -- RSSI distribution and traffic over time
- **Device Metrics** -- CPU, RAM, disk usage, temperature

The device also sends data to the Mesh Radar cloud platform. Your device operator can see your Mesh Point status and metrics from the cloud dashboard.

### Troubleshooting

- **No packets appearing**: Make sure the antenna is connected and there are Meshtastic/Meshcore devices transmitting in your area.
- **Can't find the device on your network**: Check your router for the device hostname, or try `nmap -sn 192.168.1.0/24` from your computer.
- **Dashboard not loading**: Wait 60 seconds after power-on for the service to fully start.

---

## Managing Your Mesh Point

### CLI Commands

| Command | Description |
|---------|-------------|
| `meshpoint status` | Show device health, uptime, and connection status |
| `meshpoint logs` | Tail the live service logs |
| `meshpoint restart` | Restart the service (applies config changes) |
| `meshpoint stop` | Stop the service |
| `sudo meshpoint setup` | Re-run the setup wizard (overwrites config) |
| `meshpoint version` | Print firmware version |
| `sudo poweroff` | **Shut down safely before unplugging power** |

> **Never yank the USB/power cable without shutting down first.** Always run `sudo poweroff` and wait for the green LED to stop blinking before unplugging. Pulling power while the Pi is running can corrupt the SD card and permanently damage the RAK2287 concentrator.

### Editing Configuration

User-specific settings live in `/opt/meshpoint/config/local.yaml`. Default settings are in `config/default.yaml` -- do not edit that file.

```bash
sudo nano /opt/meshpoint/config/local.yaml
meshpoint restart
```

### Updating

```bash
cd /opt/meshpoint
sudo git pull origin main
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
sudo systemctl restart meshpoint
```

**RAK2287 units (RAK Hotspot V2, DIY builds with 2287):** After restarting the service, the concentrator may fail to initialize with `lgw_start() failed` or `Failed to set SX1250_0 in STANDBY_RC mode`. The 2287's SPI bus latches in a stuck state and **cannot be cleared by `sudo reboot`** — only a full power unplug resets it. If you see this error:

1. Try restarting the service once more: `sudo systemctl restart meshpoint` (occasionally clears on a second GPIO reset)
2. If it still fails, do a **clean shutdown** before power cycling:
   ```bash
   sudo systemctl stop meshpoint
   sync
   sudo poweroff
   ```
3. Wait for the **green LED to stop blinking**, then unplug for 10+ seconds and plug back in.

**SenseCap M1 units:** Service restarts work cleanly without any power cycling. The M1's WM1303 concentrator handles SPI stop/start gracefully. These units are safe for remote updates.

**Important:** Never just yank the power cable while the Pi is running. Hard power cuts cause two problems: (1) the SD card has no write cache protection — pulling power during writes can corrupt files, the git repo, or the database, and (2) on RAK2287 units, killing power while the SPI bus is active can latch the bus or damage the SX1250 radio. Repeated power loss events (storms, UPS failures, tripped breakers) can permanently degrade the concentrator's receive sensitivity. Always `sudo poweroff` first and wait for the LED to go dark. Consider a small UPS (e.g. PiSugar or USB battery with passthrough) for deployments where power is unreliable.

### Recovering from a Corrupted Install

If `meshpoint logs` shows `SyntaxError: source code string cannot contain null bytes` or `git pull` fails with `error: inflate` / `fatal: loose object is corrupt`, the SD card took a bad write (usually from a hard power cut). Fix it with a clean re-clone:

```bash
cd /opt/meshpoint
sudo cp -r data/ /tmp/meshpoint-data-backup
sudo cp config/local.yaml /tmp/local-yaml-backup
cd /
sudo rm -rf /opt/meshpoint
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
sudo cp -r /tmp/meshpoint-data-backup /opt/meshpoint/data/
sudo cp /tmp/local-yaml-backup /opt/meshpoint/config/local.yaml
sudo chmod 777 /opt/meshpoint/data
sudo chmod 666 /opt/meshpoint/data/*.db
sudo python3 -m venv /opt/meshpoint/venv
sudo /opt/meshpoint/venv/bin/pip install -r /opt/meshpoint/requirements.txt
sudo systemctl restart meshpoint
```

This preserves your packet database and device config. The venv must be recreated since it is not tracked by git.

### Using pip on Raspberry Pi OS

Raspberry Pi OS (Bookworm and later) uses PEP 668 externally-managed environments. Never use the system `pip` directly — always use the venv:

```bash
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
```

Running `sudo pip install ...` without the venv path will fail with `error: externally-managed-environment`.

---

## Troubleshooting

### Service won't start

```bash
meshpoint logs
```

Common issues:
- **"No module named 'src'"**: Check that `/opt/meshpoint` contains the source code.
- **"Permission denied: /dev/spidev0.0"**: Run `sudo usermod -a -G spi meshpoint`
- **"No module named 'psutil'"**: Run `sudo /opt/meshpoint/venv/bin/pip install psutil`
- **"no GPIO tool found (pinctrl or gpioset)"**: This means the concentrator reset script can't toggle GPIO. Raspberry Pi OS Lite (64-bit) includes `pinctrl` by default. If you're on a non-standard image, install `gpiod`: `sudo apt install -y gpiod`

### Concentrator fails to start after update

If logs show `lgw_start() failed` or `Failed to set SX1250_0 in STANDBY_RC mode`:

**RAK2287 units:** The 2287's SPI bus holds state through reboots. `sudo reboot` will **not** fix it. You must do a full power cycle:

1. `sudo poweroff`
2. Wait for the green LED to stop blinking
3. Unplug power for 10+ seconds, then plug back in

**SenseCap M1 units:** Try `sudo systemctl restart meshpoint` — the M1 handles this cleanly and should not require a power cycle.

### Database errors after update

If logs show `sqlite3.OperationalError: table nodes has no column named <column>`:

The database schema is older than the current code. The service runs automatic migrations on startup. If it fails with `attempt to write a readonly database`, fix permissions:

```bash
sudo chmod 777 /opt/meshpoint/data
sudo chmod 666 /opt/meshpoint/data/*.db
sudo systemctl restart meshpoint
```

### Concentrator starts but receives no packets

If the logs show `SX1302 concentrator started` and `Sync word set to 0x2B` but the receive loop consistently reports `0 pkt this cycle`, the SX1250 radio's analog front-end may be damaged. This typically happens after:

- Repeated power loss events (storms, breaker trips, yanked cables)
- SPI bus latch events (the `lgw_start() failed` error, even if resolved by power cycling)

The SX1250's digital SPI interface can recover while the RF receive path remains non-functional. To confirm: test a known-working Meshtastic device within a few meters. If still zero packets, the RAK2287 module needs replacement (~$50-60). The Pi and carrier board are unaffected.

### No LoRa packets captured

- Verify the concentrator is detected: `ls /dev/spidev0.*`
- Verify libloragw is installed: `ls /usr/local/lib/libloragw.so`
- Check that there are Meshtastic/Meshcore devices transmitting in your area
- Verify the antenna is connected

### Not appearing on cloud dashboard

1. Check that `upstream.enabled` is `true` in your local config
2. Verify your API key is correct
3. Check logs: `meshpoint logs | grep -i upstream`
4. Make sure the Pi has internet access: `ping google.com`

### Remote commands not working

1. Check the fleet view on meshradar.io -- device should show as "Online"
2. Try a Ping command from the fleet panel
3. Check logs: `meshpoint logs | grep -i "command\|response"`

---

## Network Architecture

```
   Your Mesh Point (Raspberry Pi)
   ┌──────────────────────────────┐
   │  SX1302/SX1303 (SPI)          │
   │    └─ Multi-channel RX       │
   │  SX1262 Radio (USB serial)   │
   │    └─ Relay TX               │
   │  ZOE-M8Q GPS (UART)          │
   │    └─ Device positioning     │
   │                              │
   │  Mesh Point Software         │
   │    ├─ Packet capture         │
   │    ├─ Protocol decoding      │
   │    ├─ Local SQLite storage   │
   │    ├─ Relay decision engine  │
   │    ├─ Local web dashboard    │
   │    └─ WebSocket upstream ────┼──── meshradar.io
   └──────────────────────────────┘        │
                                           ▼
                                    Cloud Dashboard
                                    (all Mesh Points
                                     aggregated on
                                     a shared map)
```

Each Mesh Point operates independently with its own local dashboard. When connected to the cloud, all Mesh Points contribute to a shared regional view where you can see every node and Mesh Point across the network.
