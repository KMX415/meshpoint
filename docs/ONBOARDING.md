# Mesh Point Onboarding Guide

Step-by-step instructions for building and deploying a Mesh Point -- from an empty Raspberry Pi to a fully operational node feeding data to the Mesh Radar cloud platform.

---

## What You're Building

A **Mesh Point** is an edge device that:

- Listens to LoRa traffic from Meshtastic and Meshcore networks using a RAK2287 concentrator
- Decodes, stores, and visualizes packets on a local dashboard
- Optionally relays packets back onto the mesh via a separate SX1262 radio
- Ships data upstream to the Mesh Radar cloud platform for regional mesh intelligence

## Hardware Requirements

| Component | Purpose | Notes |
|-----------|---------|-------|
| **Raspberry Pi 4** (1-2GB RAM) | Host computer | 1GB works, 2GB recommended for future updates |
| **RAK2287 LoRa Concentrator** | Multi-channel LoRa receiver | SX1302 chipset; some HATs include ZOE-M8Q GPS |
| **RAK Pi HAT** | Mounts the RAK2287 to the Pi | Provides SPI + UART breakout |
| **microSD card** (32GB) | Boot drive | Class 10 or better |
| **USB-C power supply** (5V 3A) | Power | Official Pi PSU recommended |
| **LoRa antenna** (906 MHz) | Reception | 10 dBi gain recommended for US915 band |
| **Ethernet cable or WiFi** | Network connectivity | Needed for cloud uplink |
| **Optional: SX1262 radio** | Relay transmitter | T-Beam, Heltec V3, or RAK4631 running Meshtastic firmware |

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

### Step 2: Assemble Hardware

1. Seat the RAK2287 module into the mPCIe slot on the RAK Pi HAT.
2. Connect the LoRa antenna to the RAK2287's antenna port. **Never power the concentrator without an antenna connected** -- this can damage the radio.
3. If your HAT has a GPS module and you have a GPS antenna, connect it to the u.FL connector.
4. Mount the HAT onto the Raspberry Pi's GPIO header.
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

### Step 5b: Install Core Modules

The concentrator capture and protocol decoding modules are distributed separately as compiled binaries. You need to install them before the Mesh Point can operate:

```bash
sudo /opt/meshpoint/scripts/install_core.sh /path/to/meshpoint-core.tar.gz
```

> **Note:** Core modules are provided when you purchase a Mesh Point or request access through [meshradar.io](https://meshradar.io). Pre-provisioned devices ship with core modules already installed.

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
meshpoint setup
```

The wizard walks you through 7 steps:

1. **Hardware Detection** -- probes for RAK2287, GPS, serial radios
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

- Raspberry Pi 4 with RAK2287 LoRa HAT mounted
- LoRa antenna
- USB-C power supply
- microSD card (already inserted and configured)

### Setup

1. **Connect the antenna** to the gold SMA connector on the HAT. Do this BEFORE powering on.
2. **Plug in the Ethernet cable** (if provided) or the device is pre-configured for your Wi-Fi.
3. **Plug in the USB-C power supply.**

The device will boot in about 60 seconds and start capturing LoRa packets automatically.

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
| `meshpoint setup` | Re-run the setup wizard (overwrites config) |
| `meshpoint version` | Print firmware version |

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

### No LoRa packets captured

- Verify the RAK2287 is detected: `ls /dev/spidev0.*`
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
   │  RAK2287 (SPI)               │
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
