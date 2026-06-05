# Hardware Matrix

A side-by-side reference for choosing concentrator hardware and MeshCore
companion radios. For high-level options see [README > Hardware](../README.md#hardware).
For build-from-parts assembly see [Onboarding > Step 2](ONBOARDING.md#step-2-assemble-hardware).

---

## Concentrator Boards

The host is a **Raspberry Pi 4** or **Compute Module 4 (CM4)** (1 GB minimum,
2 GB recommended) running **64-bit** Raspberry Pi OS or Raspbian Lite.
Pi 3 and Pi 5 are not currently supported. Pi 5 may work but is not validated.
Application code is plain Python (v0.7.0+); **aarch64** is required.

| | RAK Hotspot V2 (RAK7248) | SenseCap M1 | Syncrobit Chameleon | DIY (Pi + RAK2287 + HAT) |
|---|---|---|---|---|
| **Host** | Pi 4 (SD) | Pi 4 (SD) | CM4 (eMMC) | Pi 4 (SD) |
| **Concentrator** | RAK2287 (SX1302) | WM1303 (SX1303) | SX1302 (onboard) | RAK2287 (SX1302) |
| **TX support** | Yes (native, with HAL patch) | Yes (native, with HAL patch) | Yes (native, with HAL patch) | Yes (native, with HAL patch) |
| **RX channels** | 8 simultaneous | 8 simultaneous | 8 simultaneous | 8 simultaneous |
| **Spreading factors** | SF7-SF12 simultaneous | SF7-SF12 simultaneous | SF7-SF12 simultaneous | SF7-SF12 simultaneous |
| **Form factor** | Pre-assembled metal case | Pre-assembled metal case | Pre-assembled (PoE-capable) | Bare or 3D-printed enclosure |
| **Carrier crypto chip** | None | ATECC608 (auto-detected) | None (wizard shows generic SX1302/Pi) | None |
| **Boot storage** | microSD (usually 32 GB) | microSD (sometimes 64 GB) | Onboard eMMC (~8-32 GB) | Buy microSD separately |
| **Antenna included** | Yes | Yes | Yes | Buy separately |
| **PSU included** | Yes (USB-C) | Yes (USB-C, into carrier) | Often PoE (injector/switch separate) | Buy separately |
| **SPI bus latch on hard power loss** | Yes | No | Yes (SX1302 class) | Yes |
| **Typical price (used)** | $40-70 | $30-60 | Varies (retired LoRa miner) | $50-90 (parts) |
| **Reflash difficulty** | Easy (SD card access) | Easy (back panel + SD) | Moderate (USB boot via CM4 carrier) | Easy (SD card) |
| **Plug-and-play with `install.sh`** | Yes | Yes | Yes (after OS flash) | Yes |

### What "SPI bus latch" means

The RAK2287 module can latch its SPI bus when power is cut while the
concentrator is active. The Meshpoint service holds the concentrator in
GPIO reset during shutdown to prevent this on `sudo reboot` and
`sudo systemctl restart meshpoint`. **Hard power loss** (yanked cable,
breaker trip, outage) can still latch and require a full power-off for 10+
seconds to clear. Repeated hard power loss can permanently damage the
SX1250 RF front-end. The SenseCap M1 (SX1303 + WM1303) does not have this
issue.

If your deployment cannot guarantee clean shutdowns, either:

1. Buy a SenseCap M1 instead, or
2. Add a small UPS (PiSugar, USB battery with passthrough) to the RAK V2.

**RAK Hotspot V2 note:** Some units are particularly sensitive to reset
timing. If you see repeated `lgw_start()` failures with chip version 0x00
even after power cycles, try setting
`Environment=CONCENTRATOR_RESET_HOLD_SEC=1.0` (or `CONCENTRATOR_LATE_RESET=1`)
in the service. Also see the "RAK Hotspot V2 specific issues" section in
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Choosing between them

| If... | Buy... |
|---|---|
| You want the cheapest path | Whichever is cheaper on eBay this week |
| Power is occasionally unreliable and you have no UPS | SenseCap M1 |
| You already own a Pi 4 | DIY: RAK2287 + RAK Pi HAT |
| You want easiest reflash (back panel access) | RAK Hotspot V2 (4 bottom screws) |
| You want PoE and a sealed outdoor-style enclosure | Syncrobit Chameleon (after eMMC reflash) |
| You already have a Chameleon and a CM4 USB carrier | Repurpose with [Syncrobit Chameleon guide](SYNCROBIT-CHAMELEON.md) |
| You have a RAK WisMesh Pi Node HAT (RAK6421) | [WisMesh Node (experimental)](#wismesh-node-rak6421-hat-experimental) on branch `feat/wismesh-hat` |

### Syncrobit Chameleon notes

The Chameleon ships a **Compute Module 4 with onboard eMMC**, not a removable
microSD card. First-time Meshpoint install requires flashing new OS over USB
using a CM4 carrier board (for example the Waveshare CM4-IO-BASE-B) and the
Raspberry Pi `usbboot` tools. After that, the module stays in the Chameleon
carrier: same `install.sh` and `meshpoint setup` flow as other SX1302 units.

Validated stack (community, May 2026): CM4 eMMC, **aarch64** Raspbian 13
(Trixie) Lite, Meshpoint v0.7.4+, live Meshtastic RX/TX via onboard SX1302.
Original Chameleon miner firmware is replaced; keep a backup image if you need
to restore vendor software.

**PoE:** Many units power from Ethernet. Ensure your injector or switch can
supply enough current for CM4 + concentrator (plan for up to ~2-3 A at 5 V
equivalent). Prefer `sudo poweroff` before removing PoE to avoid SPI latch
(see below).

---

## Experimental: WisMesh Node (RAK6421 HAT)

Meshpoint **Node** platform for the [RAK Meshtastic Raspberry Pi HAT (RAK6421)](https://store.rakwireless.com/products/meshtastic-raspberry-pi-hat-rak6421): Pi 4 + **RAK6421** HAT + WisBlock **SX1262** (slot 1). RF is owned by **meshtasticd** (single-channel Meshtastic participant), not the SX1302 concentrator stack used elsewhere in this matrix.

| | RAK6421 WisMesh Pi HAT |
|---|---|
| **Platform tier** | **Experimental (Node)** — not Stable |
| **Host** | Raspberry Pi 4 (64-bit OS Lite) |
| **RF path** | **meshtasticd** (Portduino) + WisBlock LoRa module |
| **LoRa modules** | **RAK13300** (validated), **RAK13302** (when meshtasticd preset available) |
| **Concentrator** | None (single-radio via meshtasticd, not 8-channel SX1302) |
| **Meshpoint branch** | `feat/wismesh-hat` (Settings → Updates → Experimental) |
| **Install** | `./scripts/install.sh --platform node` |
| **Gateway TX/RX** | No native concentrator path; meshtasticd owns the radio |
| **Dashboard** | Same browser UI; packet source is TCP Phone API (:4403) |

Popular add-on for Pi users who want Meshtastic on a HAT without retiring a
Helium-class gateway. **Do not flash this track onto RAK V2, SenseCap M1,
Chameleon, or RAK2287 DIY units** unless you are intentionally converting
that Pi to a Node-only install.

Full runbook: **[WisMesh Node guide](WISMESH-NODE.md)**. See also [Onboarding](ONBOARDING.md) and [Migrate Gateway ↔ Node](MIGRATE-GATEWAY-TO-NODE.md).

**Do not** run Gateway `install.sh` on a Pi that only has the WisMesh HAT (no SX1302). The setup wizard and `chip_id` probe expect a concentrator on Gateway installs.

---

## What is NOT supported

| Hardware | Status | Reason |
|---|---|---|
| Raspberry Pi 3 | Not supported | Not enough RAM headroom; aarch64 userspace required |
| Raspberry Pi 5 | Not validated | May work but not regularly tested |
| Raspberry Pi Zero 2 W | Not supported | Insufficient memory and IO for concentrator + dashboard |
| 32-bit Raspberry Pi OS | Not supported | Meshpoint targets aarch64 userspace |
| x86 / x86_64 host | Not supported | aarch64 Raspberry Pi family only |
| RAK7268 / RAK7268V2 (commercial gateway) | Not supported | These are LoRaWAN gateways with different firmware path; SX1302 is similar but the platform stack does not match |
| Helium WHIP / Linxdot Indoor | Not validated | Same chip family as RAK V2 but the carrier varies; community testing welcome |
| Nebra Indoor (Rock Pi 4 + SX1301) | Not supported | Daughter board uses SX1301, not SX1302/SX1303; different HAL |
| Single-channel SX1276/SX1262 boards | Not for concentrator role | These are single-channel radios. They can run as a [MeshCore USB companion](#meshcore-usb-companion-radios), not as the main concentrator. |

---

## MeshCore USB Companion Radios

Optional. Adds MeshCore RX and TX through a single-channel USB radio
plugged into the Pi's USB port. Different protocol from Meshtastic, listens
on a different default frequency.

Flash the radio with the **`companion_radio_usb`** firmware variant from
[flasher.meshcore.co.uk](https://flasher.meshcore.co.uk/) before plugging
into the Pi. The setup wizard auto-detects the device and configures its
frequency to match your region.

### Why a USB companion instead of the SX1302 concentrator?

MeshCore on most regions uses a **62.5 kHz LoRa bandwidth**. The SX1302
concentrator inside every supported Meshpoint (RAK V2, SenseCap M1,
Chameleon, RAK2287 DIY) cannot tune below **125 kHz**. That is a hardware limitation
of the SX1302 baseband, not a software gap, so MeshCore packets at
62.5 kHz are physically invisible to the concentrator no matter how it is
configured.

The single-channel SX1262 inside a USB companion radio (Heltec V3/V4,
T-Beam, etc.) operates well below 125 kHz, so it has no problem
demodulating MeshCore at 62.5 kHz. Meshpoint then decodes those packets
natively through its MeshCore decoder. If MeshCore networks in your area
ever migrate to 125 kHz or wider, the SX1302 will be able to receive them
directly and the USB companion becomes optional. See
[ROADMAP](../ROADMAP.md) for the status of dual-protocol HAL work that
would enable that path.

| Device | Chipset | Notes |
|---|---|---|
| Heltec LoRa V3 | ESP32-S3 | Common, inexpensive, validated |
| Heltec LoRa V4 / V4 OLED | ESP32-S3 | Latest Heltec revision, validated |
| LilyGo T-Beam | ESP32 | Includes GPS |
| Heltec Wireless Tracker | ESP32-S3 | Includes GPS and display |

### Heltec V3 vs V4 USB enumeration gotcha

When two Heltec V3/V4 boards are plugged in (or one Heltec V4 with
different firmwares on different boots), USB enumeration can be
counterintuitive:

| Firmware on Heltec V4 | Enumerates as | USB ID |
|---|---|---|
| MeshCore companion | `heltec_wifi_lora_32 v4` (named device) | `303a:0002` |
| Meshtastic | USB JTAG/serial debug unit (generic device) | `303a:1001` |

Most users assume the Meshtastic firmware is the "named" one and MeshCore
is the generic one. It is the opposite. The MeshCore firmware initializes
TinyUSB so the host sees the friendly board name. The Meshtastic firmware
on this hardware does not initialize TinyUSB and falls back to the generic
JTAG/serial endpoint.

If you have both a MeshCore companion and a Meshtastic node attached over
USB at the same time, **pin the MeshCore serial port explicitly** in
`local.yaml` to avoid auto-detect grabbing the wrong device:

```yaml
capture:
  meshcore_usb:
    auto_detect: false
    serial_port: "/dev/ttyACM0"
```

---

## Antennas

Bundled antennas with RAK V2, SenseCap M1, and Chameleon units work fine for basic indoor or
window-mounted deployments. For better coverage:

| Use case | Recommended | Notes |
|---|---|---|
| Indoor / window | 3-5 dBi omni (bundled is fine) | |
| Rooftop / pole, line of sight to neighborhood | 6-8 dBi omni | Sweet spot for most urban Meshpoints |
| Rooftop / tower, distant horizon coverage | 10-12 dBi omni | Flattened radiation pattern, loses very-close low-elevation nodes |
| Long feedline run (over 30 ft) | LMR-400 cable + the same antenna | Loss in cheap RG-58 dominates the link budget |

> **Always connect the antenna BEFORE powering on.** Transmitting without
> an antenna damages the radio. RX-only without an antenna is safe but
> useless.

GPS antenna (u.FL to SMA pigtail) is optional. If your carrier board has a
u-blox GPS module, plugging in a GPS antenna gives you automatic
positioning during the setup wizard. Otherwise enter coordinates manually
(right-click any spot in Google Maps to copy in decimal format).

---

## Power and SD Cards

| Component | Recommended |
|---|---|
| PSU | Official Raspberry Pi 4 USB-C PSU (5V 3A). Cheap PSUs cause SD card corruption. |
| SD card | 32 GB minimum, Class 10 or better (Pi 4 / SD-based miners). SanDisk High Endurance or Samsung Pro Endurance for 24/7 deployments. |
| eMMC (CM4) | Chameleon and other CM4 carriers: ensure several GB free before `install.sh` (HAL build + venv). |
| UPS (optional) | PiSugar 3, USB battery with passthrough. Strongly recommended for RAK V2 and Chameleon (SX1302 latch risk) without reliable mains. |
| PoE (optional) | Pi 4 PoE+ HAT, Chameleon built-in PoE, or PoE injector + USB-C PD. Useful for rooftop installs. |

Bad PSUs and cheap SD cards are the most common silent failure mode. If
you see `SyntaxError: source code string cannot contain null bytes` or
`fatal: loose object is corrupt` in the logs after a power event, the SD
card took a bad write. See [Troubleshooting > Recovering from a corrupted install](TROUBLESHOOTING.md#recovering-from-a-corrupted-install).
