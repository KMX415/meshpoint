# Bobcat Miner 300: Armbian and Meshpoint Install

Guide for repurposing a **Bobcat Miner 300** (Helium-era LoRa miner) as a
Meshpoint. These units use a **Rockchip RK3566** host (not a Raspberry Pi),
onboard **eMMC**, and an **SX1302-class** concentrator. Meshpoint runs after
you flash community **Armbian** and apply the SPI/GPIO configuration below.

**Status (September 2026):** Community-validated on model **G295** (2 GB RAM, 64 GB
eMMC). Meshtastic TX/RX confirmed; MeshCore companion via a **powered USB hub**
reported working. Model **G290** (also SX1302, 2 GB / 64 GB) is expected to
follow the same path, but remains unvalidated. **G285** is now
[community-reported working](https://github.com/KMX415/meshpoint/issues/137)
with a different SPI bus and power sequence. Its individual TX/RX and restart
checks have not been reported. This is **not** plug-and-play
like a RAK Hotspot V2: expect manual `local.yaml`, systemd overrides, and
kernel pin holds.

Compare with other miners in [Hardware Matrix](HARDWARE-MATRIX.md). For Pi 4 +
microSD installs see [Onboarding](ONBOARDING.md).

**Choose your model before following the steps.** Steps 2, 5 and 6 below
describe G295. For G285, replace those three steps with the
[G285-specific procedure](#g285-specific-procedure-community-report).
Do not combine GPIO 147 or the SPI5 symlinks from G295 with the G285 recipe.

---

## What you need

| Item | Notes |
|------|--------|
| Bobcat Miner 300 | G295 validated; G285 community report; G290 unvalidated |
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

Edit `/opt/meshpoint/config/local.yaml`. Set the SPI device. There is no nested
`capture.concentrator` block: chip type is detected at start, and GPIO 149/147
belong in the Step 6 drop-in, not yaml.

```yaml
capture:
  sources:
    - concentrator
  concentrator_spi_device: "/dev/spidev5.0"
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

## G285-specific procedure (community report)

Source: [issue #137, Bobcat 300 - Model G285](https://github.com/KMX415/meshpoint/issues/137).
The contributor reports that the following sequence powers up the concentrator
and makes Meshpoint work. This is a documented community recipe, not automatic
installer support or a claim of independently verified TX/RX reliability.
GPIO numbers here are the report's **Linux sysfs GPIO numbers**, not Raspberry
Pi header pins. This procedure requires the reported Armbian SPI/sysfs interfaces.

| Model | SPI overlay / device | Power enables | Reset |
|---|---|---|---|
| G295 existing guide | `spi5-m1` / `/dev/spidev5.0` | 147 | 149 |
| G285 issue #137 | `spi1` / `/dev/spidev1.0` | 125 and 122 | 149 |

Back up `config/local.yaml` and your existing service drop-ins before editing.
Stop Meshpoint before changing the hardware configuration. Inspect
`sudo systemctl cat meshpoint` for existing custom hooks; the G285 block replaces
the G295 startup/shutdown recipe, not unrelated settings or custom services.

**Replace Step 2:** use `spi1` as the concentrator overlay in
`/boot/armbianEnv.txt`, retaining unrelated overlays. Reboot and verify that
`/dev/spidev1.0` exists. Do not assume the G295 image/kernel details establish
compatibility for every G285 revision; record the image and kernel used.

**Replace Step 5:** merge these fields into your existing `capture` mapping,
preserving any other configured sources and settings:

```yaml
capture:
  sources:
    - concentrator
  concentrator_spi_device: /dev/spidev1.0
```

Keep the Step 5 `dialout` group membership command. Do not create SPI5 aliases.

**Replace Step 6:** run `sudo systemctl edit meshpoint` and replace the old
board-specific hooks with this complete block. If hooks are spread across
multiple drop-ins, consolidate them so later files do not append another reset
sequence. The empty assignments clear inherited hooks; the first three commands
restore the current Meshpoint service's sudoers and config/data preparation.
No change to `scripts/reset_concentrator.sh` is needed because both of its
default service hooks are replaced.

```ini
[Service]
ExecStartPre=
ExecStartPre=+/bin/bash -c "cp /opt/meshpoint/config/sudoers-meshpoint /etc/sudoers.d/meshpoint && chmod 440 /etc/sudoers.d/meshpoint"
ExecStartPre=+/bin/chown -R meshpoint:meshpoint /opt/meshpoint/config
ExecStartPre=+/bin/chown -R meshpoint:meshpoint /opt/meshpoint/data
ExecStartPre=+/bin/sh -c 'chown root:dialout /dev/spidev1.* && chmod 660 /dev/spidev1.* || true'

# Power enables, before reset
ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio125 ] && echo 125 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio122 ] && echo 122 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sleep 0.2
ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio125/direction'
ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio122/direction'
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio125/value'
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio122/value'
ExecStartPre=+/bin/sleep 1
ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio125/value'
ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio122/value'

# SX1302 reset, then release the GPIO to input
ExecStartPre=+/bin/sh -c '[ ! -d /sys/class/gpio/gpio149 ] && echo 149 > /sys/class/gpio/export || true'
ExecStartPre=+/bin/sleep 0.1
ExecStartPre=+/bin/sh -c 'echo out > /sys/class/gpio/gpio149/direction'
ExecStartPre=+/bin/sleep 0.1
ExecStartPre=+/bin/sh -c 'echo 1 > /sys/class/gpio/gpio149/value'
ExecStartPre=+/bin/sleep 0.1
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio149/value'
ExecStartPre=+/bin/sleep 0.1
ExecStartPre=+/bin/sh -c 'echo in > /sys/class/gpio/gpio149/direction'
ExecStartPre=+/bin/sleep 0.5

ExecStopPost=
ExecStopPost=+/bin/sh -c 'echo out > /sys/class/gpio/gpio149/direction 2>/dev/null; echo 1 > /sys/class/gpio/gpio149/value 2>/dev/null || true'
ExecStopPost=+/bin/sh -c 'echo 0 > /sys/class/gpio/gpio125/value 2>/dev/null; echo 0 > /sys/class/gpio/gpio122/value 2>/dev/null || true'
```

The `|| true` clauses preserve the contributor's best-effort handling of
existing GPIO exports, SPI permissions and shutdown. A successful service start
does not prove every one of those commands succeeded; inspect device permissions
and logs if initialization fails. Do not substitute `RESET_GPIO=149` for this
recipe: that does not perform the two power enables or the input release.

Apply and inspect the effective configuration before testing:

```bash
sudo systemctl daemon-reload
sudo systemctl cat meshpoint
sudo systemctl restart meshpoint
journalctl -u meshpoint -n 100 --no-pager
```

**Owner verification, still pending for G285:** record the board revision,
Armbian image/kernel, Meshpoint commit and supply. Verify cold boot and at least
three consecutive service restarts. Separately confirm reception from a known
node and, when TX is configured, that another node receives a transmitted
message. Test clean shutdown and subsequent power-on recovery, not forced power
cuts. Report outcomes and sanitized logs on #137; initialization alone does not
establish TX/RX or long-running reliability.

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
| Meshtastic concentrator TX/RX | G295 validated (bench / limited RF environment); G285 individual checks pending |
| Long-range / multi-hop soak | More field testing welcome |
| MeshCore on-board USB OTG | Use powered hub; native OTG not confirmed |
| G285 hardware | Community-reported working in #137; separate setup above, restart/TX/RX verification pending |
| `install.sh` without edits | Not supported (kernel upgrade risk) |
| Bluetooth / Meshtastic phone app | Not used; use the Meshpoint web dashboard |

---

## Troubleshooting

**`Ignoring unknown config key(s): capture.concentrator`:** An older version of
this guide showed a nested `concentrator:` block. Meshpoint ignores it. Use
`concentrator_spi_device` as in Step 5, keep the Step 6 drop-in, then restart.

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
