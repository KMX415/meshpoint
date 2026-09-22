# Heltec HT-M2808: Debian Bookworm and Meshpoint Install

Guide for repurposing a **Heltec HT-M2808** (Helium-era LoRa miner) as a
Meshpoint. These units use a **Rockchip RK3328** host, onboard **eMMC**, and
an **SX1302-class** concentrator. Meshpoint runs after you flash the
purpose-built Debian Bookworm image below and apply the GPIO configuration
in Step 5.

**Status:** Community-validated on the HT-M2808. Meshtastic TX/RX confirmed.
This is **not** plug-and-play like a RAK Hotspot V2: expect manual
`local.yaml` and a systemd override for GPIO reset.

Compare with other miners in [Hardware Matrix](HARDWARE-MATRIX.md). For Pi 4 +
microSD installs see [Onboarding](ONBOARDING.md).

---

## What you need

| Item | Notes |
|------|--------|
| Heltec HT-M2808 | RK3328 Helium Miner |
| Host | Rockchip RK3328, aarch64 |
| Storage | Onboard eMMC |
| LoRa antenna | Connect before applying RF power |
| USB OTG / hub | Onboard micro-USB is for flashing; MeshCore USB may need a **powered hub** |
| Ethernet or Wi-Fi | For dashboard access and optional Meshradar upstream |

---

## Step 1: Flash Debian Bookworm

Use the purpose-built Debian Bookworm image for the HT-M2808:

**Image:** [HeltecBookworm.img.xz](https://github.com/sicXnull/Debian-Helium-Miners/releases/download/1.0/HeltecBookworm.img.xz)

**Flashing instructions:** [Heltec-M2808-Flashing.md](https://github.com/sicXnull/Debian-Helium-Miners/blob/main/instructions/Heltec-M2808-Flashing.md)

Follow the linked flashing tutorial to write the image to eMMC/SD and get
the board booted. This is a purpose-built image for the board's SPI/GPIO
layout, so there's no kernel package to hold and no overlay to add before
proceeding — the concentrator bus is available out of the box.

---

## Step 2: Clone Meshpoint and run the installer

```bash
sudo apt update
sudo apt install -y git
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
```

Run the installer. **Do not reboot** when it finishes (you still need config):

```bash
sudo bash /opt/meshpoint/scripts/install.sh
```

---

## Step 3: Setup wizard (config file only)

Run the wizard to create `config/local.yaml`. The wizard may not detect the
concentrator yet; that is expected.

```bash
sudo meshpoint setup
```

Do **not** start the service at the end of the wizard.

---

## Step 4: Point capture at the SPI bus

Edit `/opt/meshpoint/config/local.yaml`. Set the SPI device. There is no
nested `capture.concentrator` block: chip type is detected at start, and the
GPIO reset lines belong in the Step 5 drop-in, not yaml.

```yaml
capture:
  sources:
    - concentrator
  concentrator_spi_device: "/dev/spidev32766.0"
```

Save the file.

Add the service user to the `dialout` group:

```bash
sudo usermod -aG dialout meshpoint
```

---

## Step 5: Systemd override (SPI symlink, GPIO, reset)

Meshpoint defaults assume `/dev/spidev0.0` and Pi-style GPIO numbering. On
the HT-M2808, create a **systemd drop-in** so each service start prepares the
bus before the concentrator opens.

```bash
sudo systemctl edit meshpoint
```

Paste the block below **above** the line that says discarded lines are
ignored (`### Lines below this comment will be discarded`):

```ini
[Service]
ExecStartPre=

ExecStartPre=+/bin/bash -c "cp /opt/meshpoint/config/sudoers-meshpoint /etc/sudoers.d/meshpoint && chmod 440 /etc/sudoers.d/meshpoint"
ExecStartPre=+/bin/chown -R meshpoint:meshpoint /opt/meshpoint/config

ExecStartPre=+/bin/sh -c '[ ! -e /dev/spidev0.0 ] && ln -sf /dev/spidev32766.0 /dev/spidev0.0 || true'

ExecStartPre=+/bin/sh -c 'chown root:dialout /dev/spidev32766.* && chmod 660 /dev/spidev32766.* || true'

ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio2 ] && echo 2 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio0 ] && echo 0 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sleep 0.2

ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio2/direction'
ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio0/direction'

ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio2/value'
ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio0/value'
ExecStartPre=+/bin/sleep 0.3
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio2/value'
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio0/value'

ExecStartPre=+/bin/sleep 1.5
```

GPIO **2** is the SX1301 concentrator reset line; **0** is the SX125x reset
line. Both are held high 0.3s then dropped low, matching the vendor reset
sequence. Save and exit.


Reboot:

```bash
sudo reboot
```

---

## Step 6: Verify

1. Open `http://<device-ip>:8080`, complete `/setup` if prompted (v0.7.3+).
2. Enable TX on the Radio tab if you plan to send traffic.
3. Check logs:

```bash
journalctl -u meshpoint -f
```

Look for chip version `0x10` (SX1302), `lgw_start()` success, and RX lines.
Send a test message to another Meshtastic node on your bench.

---

## Upgrades

Use the normal Meshpoint update flow:

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout main
sudo git pull origin main
sudo bash /opt/meshpoint/scripts/install.sh
sudo systemctl restart meshpoint
```

---

## MeshCore USB companion

The front **micro-USB** port is primarily for flashing. USB OTG for a
MeshCore companion is unconfirmed on the HT-M2808. A **powered USB hub** with
a self-powered companion radio (for example a T-Deck) is the safer bet.

Configure MeshCore in `local.yaml` or the setup wizard once the serial port
is stable. See [Hardware Matrix > MeshCore USB](HARDWARE-MATRIX.md#meshcore-usb-companion-radios).

---

## Known limits

| Area | Status |
|------|--------|
| Meshtastic concentrator TX/RX | Validated (bench / limited RF environment) |
| Long-range / multi-hop soak | More field testing welcome |
| MeshCore on-board USB OTG | Use powered hub; native OTG not confirmed |
| Bluetooth / Meshtastic phone app | Not used; use the Meshpoint web dashboard |

---

## Troubleshooting

**`Ignoring unknown config key(s): capture.concentrator`:** An older version
of this guide showed a nested `concentrator:` block. Meshpoint ignores it.
Use `concentrator_spi_device` as in Step 4, keep the Step 5 drop-in, then
restart.

**Chip version 0x00:** Re-check symlinks and the GPIO reset sequence in the
systemd drop-in. Power-cycle with antenna connected.

**Permission denied on `/dev/spidev32766.0`:** Confirm `meshpoint` is in
`dialout` and the `chmod 660` `ExecStartPre` lines run (see drop-in above).

**Board won't boot after flashing:** Re-check the flashing steps in
[Heltec-M2808-Flashing.md](https://github.com/sicXnull/Debian-Helium-Miners/blob/main/instructions/Heltec-M2808-Flashing.md),
particularly which port/mode the board needs to be in for the flash tool to
detect it.
