# USB nodes

How to attach extra radios to a Meshpoint over USB.

The **concentrator** (SX1302 or SX1303 on the HAT) stays on one Meshtastic
plan in **Configuration → Radio**. USB nodes are separate radios. They do
not add a second preset to the concentrator.

Need **v0.7.8 or later** for the Serial card, live modem chips, and more
than one Meshtastic USB node. **v0.7.9** is better: a busy serial port no
longer takes down the whole service. The v0.8.0 RC reconnects USB after
Set Preset / region writes (the node reboots; Meshpoint does not need a
service restart).

---

## Two kinds of USB radio

| Kind | Firmware on the node | Dashboard | What it does |
|---|---|---|---|
| Meshtastic USB | Meshtastic | **Configuration → Serial** | Extra Meshtastic RX. Own region / modem preset. Replies can go out the node that heard the contact. |
| MeshCore USB | MeshCore `companion_radio_usb` | **Configuration → MeshCore** | MeshCore RX and TX. Different protocol from Meshtastic. |

A Seeed Xiao S3, Heltec, T-Beam, or similar board running **Meshtastic**
belongs on the Serial card. A MeshCore companion belongs on the MeshCore
card. Do not flash MeshCore onto the Meshtastic node unless you mean to
replace that role.

---

## When you need a Meshtastic USB node

**Configuration → Radio** sets one frequency and bandwidth for the
concentrator. The chip still demodulates **SF7 through SF12 in parallel**
on that plan.

LongFast and MediumFast are both typically **BW 250 kHz**. If your local
MediumFast mesh uses the **same frequency / slot** as LongFast, the
concentrator already hears MediumFast (SF9) and you may not need a second
radio.

Add a USB node when:

- MediumFast (or another preset) is on a **different slot or MHz**
- you want TX / replies on that second plan from the USB node
- you have no concentrator and the USB node is the only Meshtastic source

Native concentrator TX (NodeInfo, dashboard messages on the Radio plan)
stays on **Configuration → Radio**. USB-node modem writes go to that
node's own NVS, not `radio:` in `local.yaml`.

---

## Add a Meshtastic USB node

1. Flash **Meshtastic** firmware if the board is blank.
   **Configuration → Firmware** can do that for catalog boards (ESP32
   family via esptool, nRF via DFU). Or use the Meshtastic web flasher.
2. Connect an antenna to the node. Do not let it TX with no antenna.
3. Plug the node into a USB port on the Pi.
4. Open the dashboard → **Configuration → Serial** ("USB capture sources").
5. Enable **Include serial capture source**.
6. **+ Add device** if you need a row. Pick the node's port. Prefer a
   `/dev/serial/by-path/…` entry so the path survives USB reorder after
   reboot. Skip anything tagged **[GPS]**.
7. Set a short **Label** (max 16 characters), for example `mf`. Packets
   from that node tag as capture source `serial_mf`. Leave the label
   blank only if this is the single serial source (`serial`).
8. **Save USB sources**. Restart Meshpoint when the dashboard asks.
9. After the row shows connected: **Modem settings** on that same card.
   Set **Region** if it is `UNSET` (the node will not TX until region is
   set). Pick the preset chip (for example MediumFast) → **Set Preset**.
   The node reboots onto the new modem. The Serial row and top-bar
   Meshtastic USB pill show **REBOOTING** plus a countdown, then go
   green when USB comes back. No Meshpoint service restart for that
   step.

Leave **Configuration → Radio** on LongFast (or whatever the concentrator
should stay on). The USB node's preset does not move the concentrator.

**Rescan USB** refreshes the port list without a reboot. Baud default is
115200.

---

## Multiple Meshtastic USB nodes

Up to **four** Meshtastic USB devices. Each row needs its own pinned port
and a distinct label.

Typical split: concentrator on LongFast, node A on MediumFast (`label: mf`),
node B on another band or slot (`label: 433`).

Blank port rows are ignored on save so an empty extra row cannot
double-open a port.

---

## Add a MeshCore companion

On CP210x USB bridges, an asserted serial DTR line can act like a held boot
button and put the companion into CLI Rescue mode shortly after startup.
Symptoms include a brief successful connection followed by repeated query
timeouts. Meshpoint releases DTR on identified CP210x bridges; native USB
devices retain their existing behavior. This uses USB hardware identifiers,
so it does not depend on the node label or a particular USB port number.

MeshCore is a different USB device and a different firmware. Walkthrough:
[Onboarding > Adding a MeshCore Companion](ONBOARDING.md#adding-a-meshcore-companion-optional).

When a MeshCore board arrives, keep the Meshtastic node on Serial. Enable
MeshCore on **Configuration → MeshCore**. Pin **both** serial ports
(Serial card and MeshCore card). Auto-detect can grab the wrong Espressif
board when two are plugged in. See
[Hardware Matrix > Heltec USB enumeration](HARDWARE-MATRIX.md#heltec-v3-vs-v4-usb-enumeration-gotcha).

---

## YAML (optional)

The dashboard writes this. Headless equivalent:

```
capture:
  sources:
    - concentrator
    - serial
    - meshcore_usb
  serial:
    - serial_port: "/dev/serial/by-path/..."
      serial_baud: 115200
      label: "mf"
  meshcore_usb:
    auto_detect: false
    serial_port: "/dev/serial/by-path/..."
    baud_rate: 115200
```

Your `by-path` strings will differ. Copy them from the Serial / MeshCore
port pickers. Restart after yaml edits: `sudo systemctl restart meshpoint`.

Legacy single-device keys `capture.serial_port` and `capture.serial_baud`
still work. Prefer the `capture.serial` list.

---

## Troubleshooting

### RNode is a separate optional radio

In v0.8.0 development, Reticulum can use a dedicated RNode. It does not replace
the existing Meshtastic or MeshCore USB node. Never assign the same serial port
to two owners. If identical boards share a by-id identifier, verify the physical
`/dev/serial/by-path/` path, and recheck it after moving USB sockets. See the
[Reticulum setup guide](../apps/reticulum/README.md).

### Serial permissions after an update

The reliability update changes the bundled Espressif rule from world-writable
access to mode `0660`, group `dialout`. The installer ensures the service user's
group membership before migrating the exact old bundled rule. Customized rules
are retained. This does not grant access to all SDR devices or resolve a busy port.

Check the service account and the actual port permissions:

```sh
systemctl show meshpoint -p User -p Group
id meshpoint
ls -l /dev/serial/by-id/ /dev/serial/by-path/
```

Check the resolved device's owner/group too. Group changes require a fresh
service process. Use the normal installer/update path for bundled-rule repair;
do not work around errors with world-writable permissions. Close flashers and
serial monitors before Meshpoint opens the device.

- [Common Errors > Meshtastic USB serial](COMMON-ERRORS.md#meshtastic-usb-serial):
  port open failed, GPS picked as a radio
- [Common Errors > MeshCore companion grabs the wrong serial port](COMMON-ERRORS.md#meshcore-companion-grabs-the-wrong-serial-port)

Confirm the source is up:

```
meshpoint logs | grep -iE 'serial|meshcore|Failed to open'
```

---

## See also

- [FAQ: multiple modem presets](FAQ.md#can-i-listen-to-multiple-modem-presets-longfast-mediumfast-etc-at-once)
- [Configuration > Capture Sources](CONFIGURATION.md#capture-sources)
- [Radio Config Explained](RADIO-CONFIG-EXPLAINED.md#standard-meshtastic-presets)
- [Hardware Matrix](HARDWARE-MATRIX.md#meshtastic-usb-serial-radios)
