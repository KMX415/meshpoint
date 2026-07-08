# Bobcat Miner 300: Armbian and Meshpoint Install

Guide for repurposing a **Bobcat Miner 300** (Helium-era LoRa miner) as a
Meshpoint. These units use a **Rockchip RK3566** host (not a Raspberry Pi),
onboard **eMMC**, and an **SX1302-class** concentrator. Meshpoint runs after
you flash community **Armbian** and apply the SPI/GPIO configuration below.

**Status (July 2026):** Community-validated on model **G295** (2 GB RAM, 64 GB
eMMC). Meshtastic TX/RX confirmed; MeshCore companion via a **powered USB hub**
reported working. Model **G290** (also SX1302, 2 GB / 64 GB) is expected to
follow the same path; **G285** is untested here. This is **not** plug-and-play
like a RAK Hotspot V2: expect manual `local.yaml`, systemd overrides, and
kernel pin holds.

Compare with other miners in [Hardware Matrix](HARDWARE-MATRIX.md). For Pi 4 +
microSD installs see [Onboarding](ONBOARDING.md).

---

## What you need

| Item | Notes |
|------|--------|
| Bobcat Miner 300 | G295 validated; G290 likely compatible |
| Host | Rockchip RK3566, aarch64 |
| Storage | Onboard eMMC (typically 64 GB) |
| LoRa antenna | Connect before applying RF power |
| USB OTG / hub | Onboard micro-USB is for flashing; MeshCore USB may need a **powered hub** |
| Ethernet or Wi-Fi | For dashboard access and optional Meshradar upstream |

---

## Step 1: Flash Armbian (do not upgrade the kernel)

Use the community image and instructions:

**[sicXnull/Bobcat-Armbian](https://github.com/sicXnull/Bobcat-Armbian)**

That build targets Bobcat hardware. **Do not run a generic kernel upgrade**
after install: hold the shipped kernel packages so SPI overlays keep working.

After first boot:

```bash
sudo apt-mark hold linux-image-current-rockchip64 \
  linux-dtb-current-rockchip64 \
  linux-u-boot-bobcat-29x-current
```

---

## Step 2: Enable SPI (concentrator bus)

Edit `/boot/armbianEnv.txt` and add the SPI overlay:

```bash
sudo nano /boot/armbianEnv.txt
```

Add:

```
overlays=spi5-m1
```

Save and reboot:

```bash
sudo reboot
```

After reboot the concentrator should appear on **`/dev/spidev5.0`** (and
`/dev/spidev5.1` for the secondary chip select if present).

---

## Step 3: Clone Meshpoint and run the installer

```bash
sudo apt update
sudo apt install -y git
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
```

**Before running the installer**, edit `scripts/install.sh` and **comment out**
the `apt-get upgrade` line. On Bobcat-Armbian, a full distro upgrade can replace
the pinned kernel and break SPI.

```bash
sudo nano /opt/meshpoint/scripts/install.sh
# Comment out: apt-get upgrade -y -qq
```

Run the installer. **Do not reboot** when it finishes (you still need config):

```bash
sudo bash /opt/meshpoint/scripts/install.sh
```

---

## Step 4: Setup wizard (config file only)

Run the wizard to create `config/local.yaml`. The wizard may not detect the
concentrator yet; that is expected.

```bash
sudo meshpoint setup
```

Do **not** start the service at the end of the wizard.

---

## Step 5: Point capture at the Bobcat SPI bus

Edit `/opt/meshpoint/config/local.yaml`. Set the concentrator block:

```yaml
capture:
  sources:
    - concentrator
  concentrator:
    board: "sx1302"
    spi_path: "/dev/spidev5.0"
    reset_pin: 149
```

Save the file.

Add the service user to the `dialout` group:

```bash
sudo usermod -aG dialout meshpoint
```

---

## Step 6: Systemd overrides (SPI symlinks, GPIO, reset)

Meshpoint defaults assume `/dev/spidev0.0` and Pi-style GPIO numbering. On
Bobcat, create a **systemd drop-in** so each service start prepares the bus
before the concentrator opens.

```bash
sudo systemctl edit meshpoint
```

Paste the block below **above** the line that says discarded lines are ignored
(`### Lines below this comment will be discarded`):

```ini
[Service]
ExecStartPre=

ExecStartPre=+/bin/bash -c "cp /opt/meshpoint/config/sudoers-meshpoint /etc/sudoers.d/meshpoint && chmod 440 /etc/sudoers.d/meshpoint"
ExecStartPre=+/bin/chown -R meshpoint:meshpoint /opt/meshpoint/config

ExecStartPre=+/bin/sh -c '[ ! -e /dev/spidev0.0 ] && ln -sf /dev/spidev5.0 /dev/spidev0.0 || true'
ExecStartPre=+/bin/sh -c '[ ! -e /dev/spidev0.1 ] && ln -sf /dev/spidev5.1 /dev/spidev0.1 || true'

ExecStartPre=+/bin/sh -c 'chown root:dialout /dev/spidev5.* && chmod 660 /dev/spidev5.* || true'

ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio149 ] && echo 149 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio147 ] && echo 147 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sleep 0.2

ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio149/direction'
ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio147/direction'

ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio147/value'
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio149/value'
ExecStartPre=+/bin/sleep 0.3
ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio149/value'
ExecStartPre=+/bin/sleep 0.3
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio149/value'

ExecStartPre=+/bin/sleep 1.5
```

GPIO **147** enables the TX amplifier rail; **149** is the concentrator reset
line. Save and exit.

Reboot:

```bash
sudo reboot
```

---

## Step 7: Verify

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

Use the normal Meshpoint update flow, but **keep `apt-get upgrade` disabled**
in `install.sh` (or re-comment it after each pull) so the pinned Armbian kernel
stays in place.

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout main
sudo git pull origin main
sudo bash /opt/meshpoint/scripts/install.sh
sudo systemctl restart meshpoint
```

Community reports: v0.7.3.1 to v0.7.4 upgraded cleanly with only the
`apt-get upgrade` guard in place.

---

## MeshCore USB companion

The front **micro-USB** port is primarily for flashing. **USB OTG for a
MeshCore companion is unconfirmed** on G295 (a dedicated OTG cable did not
enumerate as host). A **powered USB hub** with a self-powered companion radio
(for example a T-Deck) has been reported working under Armbian.

Configure MeshCore in `local.yaml` or the setup wizard once the serial port
is stable. See [Hardware Matrix > MeshCore USB](HARDWARE-MATRIX.md#meshcore-usb-companion-radios).

---

## Known limits

| Area | Status |
|------|--------|
| Meshtastic concentrator TX/RX | Validated (bench / limited RF environment) |
| Long-range / multi-hop soak | More field testing welcome |
| MeshCore on-board USB OTG | Use powered hub; native OTG not confirmed |
| G285 hardware | Untested |
| `install.sh` without edits | Not supported (kernel upgrade risk) |
| Bluetooth / Meshtastic phone app | Not used; use the Meshpoint web dashboard |

---

## Troubleshooting

**Chip version 0x00:** Re-check SPI overlay, symlinks, GPIO reset sequence in
the systemd drop-in, and that kernel packages are still **held**. Power-cycle
with antenna connected.

**Permission denied on `/dev/spidev5.0`:** Confirm `meshpoint` is in `dialout`
and the `chmod 660` `ExecStartPre` lines run (see drop-in above).

**Service fails after `apt upgrade`:** Kernel drift. Reflash or restore
Bobcat-Armbian, re-apply `apt-mark hold`, and avoid uncommenting
`apt-get upgrade` in `install.sh`.

For general Meshpoint errors see [COMMON-ERRORS.md](COMMON-ERRORS.md) and
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).
