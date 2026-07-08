# Social media drafts (saved 2026-06)

Capability-first posts. De-emphasize Helium/miner repurposing (hardware prices moved). Two build paths: RAK6421 WisMesh HAT + WisBlock (13300/13302) or SX1302/SX1303 concentrator gateway.

**Stable reference:** v0.7.5.1 on `main`. **RC:** v0.7.6 on `feat/v0.7.6`.

---

## Facebook (LoRa / Meshtastic / MeshCore group)

**What a Meshpoint is (and what you can build one from)**

**Meshpoint** is an open-source **Meshtastic base station** for Raspberry Pi: **8-channel LoRa RX**, **native TX on the mesh**, and a **full browser dashboard** on your LAN. Optional link to [meshradar.io](https://meshradar.io) if you want a multi-site map and history.

**From the dashboard you can:**

- Chat on **channels and DMs** (Meshtastic on the concentrator; **MeshCore** with a USB companion if your area runs both)
- Watch a **live map**, packet feed, and node roster (signal, hops, hardware, favorites)
- Tune **region, preset, frequency, channels/PSKs, TX power, duty cycle, MQTT, GPS** without living in SSH
- Lock it down with **login + optional read-only viewer**, run a **web terminal**, and **apply updates** from Settings when you are ready to pull a new release

**MQTT** to community brokers (Meshtastic protobuf + MeshCore JSON) with privacy gates so private keys do not leak upstream.

**Two hardware paths people are using:**

1. **High-power / modular:** **RAK6421 WisMesh Pi HAT** on a Pi 4/5 + **WisBlock LoRa** (e.g. **RAK13300** or **RAK13302** 1W-class module). Experimental Node track on the repo (`feat/wismesh-hat`).
2. **8-channel gateway:** Pi + **SX1302/SX1303 concentrator** (RAK2287 DIY, **RAK Hotspot V2**, **SenseCap M1**, **Syncrobit Chameleon**, etc.). This is the classic Meshpoint path on `main`.

Same software story: mesh visibility, browser ops, optional cloud. Different RF plumbing.

**Stable today:** v0.7.5.1  
**Early testers:** v0.7.6 RC (`feat/v0.7.6`): stronger **mesh participant** behavior (PKI-aware replies, traceroute, telemetry responses, DM/routing polish)

**Links:**  
[github.com/KMX415/meshpoint](https://github.com/KMX415/meshpoint) (AGPL, docs, Discord in README)  
WisMesh Node guide: `docs/WISMESH-NODE.md`  
Hardware matrix: `docs/HARDWARE-MATRIX.md`

If you are running one, say which path you picked (HAT vs concentrator) and your region. Always good to see another node on the air.

---

## Reddit — r/meshtastic

**Title:**  
`Meshpoint: 8-channel Meshtastic base + browser dashboard (Pi + concentrator or WisMesh HAT)`

**Body:**

**Meshpoint** is an AGPL Meshtastic **base station** stack for Raspberry Pi: concentrator-class **SF7-SF12 RX in parallel on one tuned frequency**, **native TX**, SQLite history, and a **browser UI** for chat, map, config, MQTT, and optional uplink to [Meshradar](https://meshradar.io).

**Repo:** https://github.com/KMX415/meshpoint  
**Stable:** v0.7.5.1 on `main`

### What you get (capability-first)

- **Participate on the mesh** from the Pi (NodeInfo, channels, DMs), not only sniff traffic  
- **Full dashboard:** messaging, live packet feed, node cards, stats, configuration editors  
- **Multi-region** (US, EU_868, ANZ, IN, KR, SG_923), **multi-channel PSK** decode, **MQTT + Home Assistant**  
- **MeshCore** via USB companion on a second protocol/frequency  
- **Auth + web terminal + in-dashboard updates** (v0.7.5+)  
- **Optional cloud** at meshradar.io for fleet/map view  

RC branch **`feat/v0.7.6`** adds more **mesh participant** depth (PKI/channel-aware unicast replies, traceroute answers, telemetry responses).

### How people are building it (pick your RF path)

**Path A: Modular / higher ERP**  
**RAK6421 WisMesh Pi HAT** + WisBlock LoRa (**RAK13300** or **RAK13302** 1W module). Runs the experimental **Node** platform (`feat/wismesh-hat`, meshtasticd). See `docs/WISMESH-NODE.md`.

**Path B: 8-channel gateway**  
Pi 4 (or CM4) + **SX1302/SX1303** concentrator: DIY RAK2287, off-the-shelf **RAK V2**, **SenseCap M1**, **Chameleon**, etc. This is the mainline gateway install (`install.sh` on `main`). See `docs/HARDWARE-MATRIX.md` and `docs/ONBOARDING.md`.

Same project, different radio attachment. Choose based on whether you want **one strong channel / modular WisBlock** or **multi-SF capture on one concentrator-tuned frequency** (not multiple modem presets at once).

### Quick start (gateway / `main`)

```bash
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
sudo /opt/meshpoint/scripts/install.sh
sudo meshpoint setup
sudo systemctl restart meshpoint
```

Then open `http://<pi-ip>:8080`.

### Updates UI stuck on "Reconnecting"?

```bash
cd /opt/meshpoint
sudo bash scripts/apply_finish.sh
# or: pip install -r requirements.txt && sudo systemctl restart meshpoint
```

Pull current `main` or RC for the apply fix.

Happy to answer hardware-specific questions in comments (HAT vs concentrator, region, preset).

---

## One-liner (X / Discord / comment)

Meshpoint: open Pi Meshtastic base with browser chat, 8-ch RX + native TX, MQTT, optional meshradar.io. Build it with an **SX1302 gateway** or the new **RAK6421 WisMesh HAT + 1W WisBlock**. https://github.com/KMX415/meshpoint

---

## Recovery blurb (Updates stuck on Reconnecting)

```bash
cd /opt/meshpoint
sudo bash scripts/apply_finish.sh
```

Or:

```bash
sudo /opt/meshpoint/venv/bin/pip install -r /opt/meshpoint/requirements.txt
sudo systemctl restart meshpoint
```

Then hard-refresh the browser.
