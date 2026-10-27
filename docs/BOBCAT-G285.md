# Bobcat Miner 300 G285: Armbian and Meshpoint Install

Guide for repurposing a **Bobcat Miner 300 G285** as a Meshpoint. This follows
the same install as [BOBCAT-300.md](BOBCAT-300.md)
and replaces the steps that are specific to the **G295**.

**Status (October 2026):** one EU868 unit, serial prefix `285EU`, running
`BobcatArmbian285.img.xz` release 1.0 (kernel `6.18.4-current-rockchip64`) and
Meshpoint 0.7.9. After reboot the service comes up on its own. The concentrator
reports chip version `0x10` and transmits a Meshtastic NodeInfo at 14 dBm on
EU868. This is **not** plug-and-play. Do not copy the G295 SPI overlay or the
G295 GPIO numbers onto this board.

The G285 boots the community image from a **microSD card**. Leave the onboard
eMMC alone: that is the original Helium firmware, and it is the copy you still
have if the card is removed.

---

## What is different from the G295 guide

| | G295 (upstream guide) | G285 (this guide) |
|---|---|---|
| Boot | Community Armbian, often written toward eMMC | microSD only. Do not run `Bobcat29X_EMMC_Flasher` |
| Device tree | `overlays=spi5-m1` in `armbianEnv.txt` | Do **not** add that overlay. `/boot/boot.cmd` ignores `fdtfile` and always loads `rk3566-bobcat.dtb` |
| SPI | `/dev/spidev5.0` | Hardware SPI `/dev/spidev1.0` (`fe620000.spi`, mux `spi1m1`) |
| Power / PA | GPIO **147** | GPIO **125** and **122**. GPIO 147 is not the enable on this board |
| Reset | GPIO **149** | GPIO **149**, same pin, different pulse (high, then low, then input) |
| Extra node in the DTB | Not the problem described here | `spi-gpio` claims the same pins as SPI1 and must be `disabled` |

Do not boot `rk3566-bobcat-29x.dtb`. Its model is `Bobcat 29x`. The file that
this board actually loads says `Bobcat 285`.

---

## What you need

| Item | Notes |
|------|--------|
| Bobcat Miner 300 | Serial starts with `285EU` (G285, EU868 radio). Another region prefix needs the same SPI/GPIO steps and the matching region in the wizard |
| microSD | 16 GB or larger. 8 GB is too small for this image |
| LoRa antenna | Connect it before enabling transmit |
| Ethernet | Dashboard and the first SSH session. Wi-Fi is optional |
| PC | To write the SD card. The miner itself is not a native Meshtastic node and has no phone-app BLE setup |

---

## Step 1: Flash Armbian to the microSD

Use the G285 image from
**[sicXnull/Bobcat-Armbian](https://github.com/sicXnull/Bobcat-Armbian)** release
1.0:

- file: `BobcatArmbian285.img.xz`
- sha256: `a75f1ca460f982ad435aa7fd8d94cb24192a64bdf855fc5610a0eb9f82195270`

Check the checksum before writing. Do **not** flash `Bobcat29X_EMMC_Flasher`
or any image whose name says it writes the eMMC.

Write the decompressed image to the SD card (the example device is `sdX`;
replace it with the card, not your system disk):

```bash
xz -dc BobcatArmbian285.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
```

Power the miner off, insert the card, and power it on. Root is on the SD
(`/dev/mmcblk0p3`). The eMMC (`mmcblk1`) stays unmounted. If the Helium web UI
appears, the board did not boot the card.

First login is the Armbian default, `root` / `1234`. Change that password when
asked.

---

## Step 2: Hold the kernel

A generic kernel bump on this image (seen from 6.18.4 to 6.18.10) stops the
board from booting. Hold the three packages that the G295 guide names, then
update userspace only:

```bash
sudo apt-mark hold linux-image-current-rockchip64 \
  linux-dtb-current-rockchip64 \
  linux-u-boot-bobcat-29x-current

sudo apt update
sudo apt upgrade
```

Do not run `apt full-upgrade`. The `29x` name on the U-Boot package is only
the package name shipped in this image. Do not switch the board to the 29x
device tree because of it.

`uname -r` must still show `6.18.4-current-rockchip64` after the upgrade.

---

## Step 3: Leave the concentrator on hardware SPI

`/boot/armbianEnv.txt` may contain `fdtfile=rockchip/rk3566-bobcat-29x.dtb`.
Ignore it. The boot script loads `dtb/rockchip/rk3566-bobcat.dtb`.

That blob describes the concentrator twice, on the same pins (GPIO3 clock 19,
MISO 18, MOSI 17, chip select 1): once as hardware `spi@fe620000`, and once as
a bit-bang `spi-gpio`. If `spi-gpio` stays enabled, the kernel creates
`/dev/spidev4.0` as well as `/dev/spidev1.0`, the two controllers fight, and
the chip version reads `0x00`.

There is also a `lora-3v3-regulator` node on GPIO 121. The factory power pins
are 125 and 122, driven later from userspace. Leave that regulator disabled.

Install the device-tree tools, back the blob up, and disable both nodes:

```bash
sudo apt install -y device-tree-compiler

sudo cp -a /boot/dtb/rockchip/rk3566-bobcat.dtb \
  /boot/dtb/rockchip/rk3566-bobcat.dtb.bak

sudo fdtput -t s /boot/dtb/rockchip/rk3566-bobcat.dtb /spi-gpio status disabled
sudo fdtput -t s /boot/dtb/rockchip/rk3566-bobcat.dtb /lora-3v3-regulator status disabled
sync
sudo reboot
```

Do not add `overlays=spi5-m1`.

After reboot:

```bash
cat /proc/device-tree/model
cat /proc/device-tree/spi-gpio/status
ls -l /dev/spidev*
```

Expect `Bobcat 285`, status `disabled`, and only `/dev/spidev1.0`.

If the miner does not come back, power it off, mount the SD boot partition on
a PC, and restore `rk3566-bobcat.dtb.bak` over `rk3566-bobcat.dtb`.

---

## Step 4: Clone Meshpoint and run the installer

Same as the G295 guide. Comment out the upgrade inside the installer so a
later re-run cannot move the kernel:

```bash
sudo apt install -y git
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
sudo nano /opt/meshpoint/scripts/install.sh
# Comment out: apt-get upgrade -y -qq
```

Run the installer and do **not** reboot when it finishes:

```bash
sudo bash /opt/meshpoint/scripts/install.sh
```

The installer warns about `raspi-config` and looks for a Raspberry Pi
`config.txt`. Both are expected. It also enables `network-watchdog.service`.
On current Meshpoint that watchdog does not reboot the machine
(`REBOOT_THRESHOLD` is 0); it only restarts `wlan0` after failed pings.

---

## Step 5: Setup wizard

Get a free Meshradar key (`mr1_...`) from <https://meshradar.io> before this
step. Without it, `meshpoint` exits in `validate_activation`.

```bash
sudo meshpoint setup
```

Use region `EU_868` on a `285EU` radio. The default frequency is then
869.525 MHz, LongFast, SF11, BW250. Leave transmit **off** until the antenna
is on the connector. When the wizard offers to reboot or start the service,
decline. The SPI path it detects will be wrong or empty: it only looks at
`/dev/spidev0.*`, and this board's concentrator is `/dev/spidev1.0`.

Stop the service if the installer enabled it. The drop-in in the next step
has to be in place before the next start:

```bash
sudo systemctl disable --now meshpoint
```

---

## Step 6: SPI symlink, power, and reset

Edit `/opt/meshpoint/config/local.yaml` so capture points at the symlink the
drop-in creates. GPIO does not belong in this file.

```yaml
capture:
  sources:
    - concentrator
  concentrator_spi_device: "/dev/spidev0.0"
radio:
  region: EU_868
transmit:
  enabled: false
```

Keep `transmit.enabled` false until Step 7 has shown chip version `0x10` and
the antenna is connected.

```bash
sudo usermod -aG dialout meshpoint
```

Save the power script as `/usr/local/sbin/g285-lgw-power.sh`. GPIO 125 and 122
are the load switches (off for one second, then on). GPIO 149 is reset,
active high; after the pulse it returns to an input, which is what the
factory Helium script does.

```bash
sudo tee /usr/local/sbin/g285-lgw-power.sh >/dev/null << 'EOF'
#!/bin/sh
# Power and reset the SX1302 on a Bobcat 300 G285.
# GPIO 125 and 122 are the load switches. GPIO 149 is reset, active high.
# The concentrator is /dev/spidev1.0. Leave the spi-gpio node disabled.
set -eu

action=${1:-start}

export_out() {
    n=$1
    if [ ! -d "/sys/class/gpio/gpio${n}" ]; then
        echo "$n" > /sys/class/gpio/export
        sleep 0.1
    fi
    echo out > "/sys/class/gpio/gpio${n}/direction"
}

case "$action" in
    start)
        export_out 125
        export_out 122
        export_out 149
        echo 0 > /sys/class/gpio/gpio125/value
        echo 0 > /sys/class/gpio/gpio122/value
        sleep 1
        echo 1 > /sys/class/gpio/gpio125/value
        echo 1 > /sys/class/gpio/gpio122/value
        sleep 0.2
        echo 1 > /sys/class/gpio/gpio149/value
        sleep 0.1
        echo 0 > /sys/class/gpio/gpio149/value
        sleep 0.1
        echo in > /sys/class/gpio/gpio149/direction
        ;;
    stop)
        export_out 125
        export_out 122
        echo 0 > /sys/class/gpio/gpio125/value
        echo 0 > /sys/class/gpio/gpio122/value
        ;;
    *)
        echo "usage: $0 {start|stop}" >&2
        exit 1
        ;;
esac
EOF
sudo chmod 755 /usr/local/sbin/g285-lgw-power.sh
```

Meshpoint's own reset toggles Raspberry Pi GPIO 17 and 25 through `pinctrl`.
Do not install `pinctrl` to satisfy that. On this SoC, GPIO 25 is the console
UART. The drop-in clears the stock `ExecStartPre` / `ExecStopPost` lines, so
the Pi script does not run, and the in-app reset fails with a warning. That
warning is the correct outcome.

```bash
sudo mkdir -p /etc/systemd/system/meshpoint.service.d
sudo tee /etc/systemd/system/meshpoint.service.d/g285.conf >/dev/null << 'EOF'
[Service]
ExecStartPre=
ExecStopPost=

ExecStartPre=+/bin/bash -c "cp /opt/meshpoint/config/sudoers-meshpoint /etc/sudoers.d/meshpoint && chmod 440 /etc/sudoers.d/meshpoint"
ExecStartPre=+/bin/chown -R meshpoint:meshpoint /opt/meshpoint/config
ExecStartPre=+/bin/chown -R meshpoint:meshpoint /opt/meshpoint/data

ExecStartPre=+/bin/ln -sfn /dev/spidev1.0 /dev/spidev0.0
ExecStartPre=+/bin/sh -c 'chown root:dialout /dev/spidev1.0 && chmod 660 /dev/spidev1.0'

ExecStartPre=+/usr/local/sbin/g285-lgw-power.sh start
ExecStopPost=+/usr/local/sbin/g285-lgw-power.sh stop
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now meshpoint
```

The empty `ExecStartPre=` and `ExecStopPost=` are required. They drop the Pi
reset script that the main unit file still contains.

---

## Step 7: Verify, then enable transmit

Reboot once and let systemd start Meshpoint. Do not start it by hand first.

```bash
sudo reboot
```

After a minute:

```bash
systemctl is-active meshpoint
ls -l /dev/spidev0.0 /dev/spidev1.0
cat /sys/class/gpio/gpio125/value /sys/class/gpio/gpio122/value
journalctl -u meshpoint -b | grep -E "chip version|concentrator started|ERROR|Failed"
```

Expect:

- `meshpoint` is `active`
- `/dev/spidev0.0` points at `/dev/spidev1.0`
- GPIO 125 and 122 read `1`
- `Note: chip version is 0x10 (v1.0)`
- `SX1302 concentrator started`
- frequency `869.525 MHz / SF11 / BW250 (EU_868)`

These lines are normal and are not a failed radio:

- `In-app GPIO reset failed (pins [17, 25])`
- `could not open I2C` on `0x39`, `0x3B`, `0x38` (this board has no temperature sensors on those addresses)
- `No MeshCore USB device detected -- source idle`

The MeshCore USB source is always added, because `auto_detect` defaults to
true. It is a second protocol (62.5 kHz, which this SX1302 cannot demodulate).
It is not a fallback for a dead concentrator. Meshtastic EU868 uses the
onboard radio.

Open `http://<device-ip>:8080`. The first visit asks for an admin password.
That password is not the Meshradar key.

With the antenna connected, turn transmit on and restart:

```bash
sudo nano /opt/meshpoint/config/local.yaml
# transmit.enabled: true
sudo systemctl restart meshpoint
```

Leave power at the default 14 dBm. EU868 duty cycle stays at the automatic 1%
unless `transmit.max_duty_cycle_percent` is set. About a minute after restart
the log should contain `NodeInfo broadcast OK`. The node name is whatever the
wizard stored.

---

## Upgrades

Same rule as the G295 guide: keep the three kernel packages on hold, and keep
`apt-get upgrade` commented out in `scripts/install.sh` after every pull.

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout main
sudo git pull origin main
# comment apt-get upgrade in scripts/install.sh again if the pull restored it
sudo bash /opt/meshpoint/scripts/install.sh
sudo systemctl restart meshpoint
```

The device-tree edit lives on the SD boot partition, outside the git tree.
A Meshpoint upgrade does not put `spi-gpio` back. A new Armbian image does.
Re-check Step 3 after any reflash.

---

## Known limits

| Area | Status |
|------|--------|
| Meshtastic concentrator TX/RX on G285 EU868 | Working on one board, October 2026 |
| G295 steps (`spi5-m1`, GPIO 147, `/dev/spidev5.0`) | Do not use them on a G285 |
| eMMC | Do not write it |
| Kernel upgrade | Holds required. `apt full-upgrade` is not safe |
| MeshCore on USB | Optional and idle unless a companion radio is plugged in. Not required for Meshtastic |
| Bluetooth / Meshtastic phone app | Not used. The dashboard is the UI |

---

## Troubleshooting

**Chip version `0x00` or `Failed to set SX1250_0 in STANDBY_RC mode`.**
Check, in this order:

1. `spi-gpio` status is `disabled` and only `/dev/spidev1.0` exists. Unbinding the bit-bang driver at runtime is not enough; reboot after the `fdtput` change.
2. The drop-in ran: GPIO 125 and 122 are `1` before Meshpoint opens the SPI device.
3. The kernel packages are still held and `uname -r` is still `6.18.4-current-rockchip64`.
4. You did not apply the G295 overlay or point `local.yaml` at `/dev/spidev5.0`.

**`validate_activation` / the service restart loop.** The Meshradar key is
missing or not an `mr1_...` token. `sudo meshpoint setup` again. Enter keeps
the answers already stored.

**Permission denied on the SPI device.** `meshpoint` must be in `dialout`, and
the drop-in `chmod 660` must apply to `/dev/spidev1.0`.

**The board never returns after Step 3.** Restore
`/boot/dtb/rockchip/rk3566-bobcat.dtb.bak` from another computer. Do not
replace the blob with `rk3566-bobcat-29x.dtb`.

**Service fails after `apt upgrade`.** If a kernel package moved despite the
hold, reflash the SD from the same image and repeat from Step 2. Do not repair
it by writing the eMMC.
