# FAQ

Quick answers to questions that come up often. For setup walkthroughs see
[Onboarding](ONBOARDING.md), for error catalogs see [Common Errors](COMMON-ERRORS.md),
and for config syntax see [Configuration](CONFIGURATION.md).

---

## What is a Meshpoint?

A Raspberry Pi 4 plus an SX1302/SX1303 LoRa concentrator that listens to
**eight Meshtastic channels at once** and natively transmits Meshtastic
messages from a browser. Optionally adds MeshCore monitoring and TX through
a USB companion radio. Optionally syncs with [Meshradar](https://meshradar.io)
for multi-site mesh intelligence.

If you have a phone with the Meshtastic app, you already have a single-channel
node. A Meshpoint is the same network from the perspective of an observer
sitting on top of the mesh: it sees everything in range and stores it.

---

## Do I have to use the Meshradar cloud?

No. Set `upstream.enabled: false` in `config/local.yaml` and the device runs
fully offline. The local dashboard, capture, decoding, MQTT publishing, and
storage all keep working. The cloud is opt-in.

> Note: the service still requires a valid `auth_token` at startup as a
> guardrail, even when upstream is off. Run `sudo meshpoint setup` once,
> paste the API key from your Meshradar account, then flip
> `upstream.enabled: false`. A "no API key required" mode is on the backlog.

See [Configuration > Upstream](CONFIGURATION.md#upstream-cloud) for details.

---

## RAK Hotspot V2 or SenseCap M1: which should I buy?

**Functionally identical** for Meshpoint. Both are Pi 4 + SX1302/SX1303
concentrator + metal case + antenna + power supply. RX performance is the
same.

| | RAK Hotspot V2 (RAK7248) | SenseCap M1 |
|---|---|---|
| Concentrator | RAK2287 (SX1302) | WM1303 (SX1303) |
| SD card included | Usually 32 GB | Sometimes 64 GB |
| Carrier crypto chip | None | ATECC608 (auto-detected for board ID) |
| SPI bus latch on hard power loss | Yes (mitigated by service shutdown handler) | No |
| Typical eBay price | $40-70 | $30-60 |

**Decision:** if you have a UPS or your power is reliable, buy whichever is
cheaper. If you expect occasional power loss without a UPS, the SenseCap M1
is the safer pick because the RAK2287 can latch its SPI bus on hard power
cuts and need a 10-second power-off to clear.

For deeper hardware comparison see [Hardware Matrix](HARDWARE-MATRIX.md).

---

## I already have a Pi 4. Can I just buy a concentrator?

Yes. See [README > Option C: Build Your Own](../README.md#option-c-build-your-own-85).
A RAK2287 module + RAK Pi HAT + antenna runs about $50 on eBay. Total cost
with a Pi you already own is in the $50-90 range. Assembly is straightforward:
seat the RAK2287 on the HAT, mount the HAT on the Pi GPIO header, attach
antenna, run the installer.

---

## Can I set up the Pi before the concentrator arrives?

You can run `scripts/install.sh` and `sudo meshpoint setup`, but the wizard
will fail at the hardware-detection step and the API will report
`unreachable` because it cannot initialize the concentrator. The simplest
path is to wait until the concentrator arrives, then flash and set up. If
you do pre-stage, plan to either re-run the wizard or reflash the SD card
when the real hardware lands. You may need a fresh API key from your
Meshradar account.

---

## My Meshpoint flips between online and offline on the cloud map. Why?

The cloud uses a 5-minute heartbeat. If no heartbeat arrives for **15 minutes**
the map dot turns red. Your Pi keeps trying to reconnect indefinitely so it
should self-recover, but a flaky WiFi link or a redoing-the-network situation
can produce long red stretches. Hardwire to Ethernet to confirm. If it
persists on a stable network, check upstream errors:

```bash
sudo journalctl -u meshpoint --since "30 min ago" | grep -i upstream
```

---

## I re-ran setup and now there are two Meshpoints in my fleet. How do I remove the old one?

Two options:

1. **Wait.** The old device disappears from the map after 24 hours of
   inactivity.
2. **Remove now.** Hard-refresh the cloud dashboard, go to **Fleet**, click
   the orphan card, and use the **Remove** button. You will see a
   confirmation dialog. Confirm to delete.

If the old device is still running and connected, the Remove will be
short-lived: it will reappear on the next connection. Stop the service on
the old SD card first if you want it gone for good.

---

## I want to listen on a custom slot (BW500, SF9, custom MHz). Is that supported?

Yes from v0.5.x onward. Set the slot in `local.yaml` and restart:

```yaml
radio:
  region: "US"
  frequency_mhz: 918.25
  bandwidth_khz: 500.0
  spreading_factor: 9
  coding_rate: "4/5"
```

After changing radio config, clear local history if you want a fresh node
table:

```bash
sudo systemctl stop meshpoint
sudo rm /opt/meshpoint/data/concentrator.db
sudo systemctl start meshpoint
```

The database recreates on startup. See [Radio Config Explained](RADIO-CONFIG-EXPLAINED.md)
for the "why" and [Configuration > Radio](CONFIGURATION.md#radio) for syntax.

---

## How do I clear local packet and node history?

```bash
sudo systemctl stop meshpoint
sudo rm /opt/meshpoint/data/concentrator.db
sudo systemctl start meshpoint
```

The cloud (Meshradar) is not affected. This only resets the local SQLite
database.

---

## Can the MeshCore companion talk to Meshpoint over TCP instead of USB?

Not yet. Currently MeshCore companions must be USB serial. TCP support
would allow the companion to live somewhere else on the network with its
own antenna, separate from the concentrator antenna. It is on the roadmap.

---

## I am putting a Meshpoint on a tall tower. What antenna?

At significant height, even a low-gain antenna sees exceptional coverage.
A 3-6 dBi omnidirectional in the 902-928 MHz band (US) is a great starting
point. Higher-gain antennas (10-12 dBi) flatten the radiation pattern,
which is great for distant horizon coverage but loses nearby
low-elevation nodes.

For tower deployments the bigger wins are usually:

1. **Lightning protection** at the antenna and equipment.
2. **Low-loss feedline** (LMR-400 or better for runs over 30 ft).
3. **PoE + UPS at the base** so SD card writes survive breaker trips. The
   RAK2287 SPI latch issue is much more likely if power cuts are frequent.

---

## Does Meshpoint transmit by default?

No. TX is **disabled by default** to be safe. Enable it from the Radio
settings page on the local dashboard once you have verified RX is working
and your antenna is connected. Never transmit without an antenna: it
damages the radio.

See [Configuration > Transmit](CONFIGURATION.md#transmit-native-messaging)
for power, duty cycle, and node identity settings.

---

## Why does the dashboard show an orange triangle next to the version?

A newer version of Meshpoint is available on GitHub. To update:

```bash
cd /opt/meshpoint
sudo git pull origin main
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
sudo systemctl restart meshpoint
```

If you are upgrading from v0.5.x to v0.6.x for the first time, also run
the one-time HAL recompile and sudoers steps documented in
[README > Updating to v0.6.0](../README.md#updating-to-v060-one-time-steps).

---

## How do I get help?

1. Search this `docs/` folder.
2. Check the [Common Errors catalog](COMMON-ERRORS.md).
3. Search [GitHub Issues](https://github.com/KMX415/meshpoint/issues).
4. Open a [GitHub Discussion](https://github.com/KMX415/meshpoint/discussions).
5. Hop into the [Discord](https://discord.gg/BnhSeFXVY8).

When asking for help, please include:

- Output of `meshpoint status`
- Last 50 lines of `meshpoint logs`
- Hardware (RAK V2, SenseCap M1, DIY)
- Region (US, EU_868, etc.) and any non-default radio settings from
  `local.yaml` (mask any keys you want private)
