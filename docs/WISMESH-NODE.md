# WisMesh Node (RAK6421 HAT)

Experimental **Meshpoint Node** support for the [RAK6421 WisMesh Pi HAT](https://store.rakwireless.com/products/meshtastic-raspberry-pi-hat-rak6421) and compatible WisBlock LoRa modules. This path uses **meshtasticd** (Portduino) for RF instead of an SX1302/SX1303 concentrator.

**Status:** Experimental. Available on the **`feat/wismesh-hat`** branch via Settings → Updates → **Experimental: WisMesh Node**. Not merged to Stable (`main`) yet.

**Do not use on gateway hardware.** RAK Hotspot V2, SenseCap M1, Syncrobit Chameleon, and DIY RAK2287 builds must stay on **Stable (main)**. The Node platform skips the concentrator HAL and replaces it with meshtasticd.

---

## Gateway vs Node

| | Gateway (Stable) | Node (Experimental) |
|---|---|---|
| **Hardware** | SX1302/SX1303 concentrator (8-channel) | RAK6421 WisMesh Pi HAT + WisBlock module |
| **RF owner** | Meshpoint HAL (`libloragw`) | **meshtasticd** |
| **Branch** | `main` | `feat/wismesh-hat` |
| **Install** | `./scripts/install.sh` | `./scripts/install.sh --platform node` |
| **Native 8-channel RX** | Yes | No (single-radio via meshtasticd) |
| **Dashboard** | Full gateway UI | Same dashboard; RF path differs |

---

## Requirements

- Raspberry Pi 4 (64-bit Raspberry Pi OS Lite)
- **RAK6421 WisMesh Pi HAT** with a LoRa WisBlock module seated in **slot 1** (default install path)
- Network access for the meshtasticd package repo (installed by `install.sh`)
- A [Meshradar](https://meshradar.io) API key if you want cloud upstream (optional)

---

## Supported WisBlock modules

Meshpoint's Node installer configures **meshtasticd** with the preset for **slot 1** on the RAK6421 HAT. Pick a module that matches a preset in `/etc/meshtasticd/available.d/` on your Pi.

| Module | LoRa radio | Default preset (slot 1) | Status |
|--------|------------|---------------------------|--------|
| **RAK13300** | SX1262 (standard) | `lora-RAK6421-13300-slot1.yaml` | Validated on `feat/wismesh-hat` |
| **RAK13302** | SX1262 (high power) | `lora-RAK6421-13302-slot1.yaml` | Supported when that preset ships in your meshtasticd package |

The default in `config/default.yaml` on the Node branch is **`lora-RAK6421-13300-slot1.yaml`**. Override with `meshtasticd.preset` in `local.yaml` if you use a **RAK13302** or a different slot.

If meshtasticd logs `Unable to find config for 6421 Pi Hat`, the preset file is missing from `/etc/meshtasticd/config.d/`:

```bash
ls /etc/meshtasticd/available.d/lora-RAK6421-*
sudo cp /etc/meshtasticd/available.d/lora-RAK6421-13300-slot1.yaml /etc/meshtasticd/config.d/
sudo systemctl restart meshtasticd meshpoint
```

Other WisBlock LoRa modules may work if meshtasticd publishes a matching `lora-RAK6421-*.yaml` preset, but only **RAK13300** has been hardware-validated on this branch so far. Open an issue if you test another SKU.

---

## Install from dashboard (recommended)

1. Open **Settings → Updates** on a gateway running Meshpoint **v0.7.4+** (Stable or RC).
2. Select **Experimental: WisMesh Node (RAK6421 HAT)**.
3. Click **Apply update** and confirm the experimental warning.
4. After the service restarts, SSH in and run:

```bash
cd /opt/meshpoint
sudo ./scripts/install.sh --platform node
sudo meshpoint setup
sudo systemctl restart meshtasticd meshpoint
```

The installer skips the SX1302 HAL, installs **meshtasticd**, applies the RAK6421 LoRa preset, and switches systemd to `meshpoint-node.service` (starts after meshtasticd).

---

## Install from git (manual)

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/wismesh-hat
sudo git pull origin feat/wismesh-hat
sudo ./scripts/install.sh --platform node
sudo meshpoint setup
sudo systemctl restart meshtasticd meshpoint
```

The setup wizard writes `device.platform: node` and `capture.sources: [meshtasticd]`.

---

## Verify

```bash
systemctl status meshtasticd meshpoint
ss -tn state established '( sport = :4403 or dport = :4403 )'
journalctl -u meshpoint -n 50 --no-pager | grep -E 'bridge connected|>> PKT|DM identity'
```

Healthy signs:

- `meshtasticd bridge connected to 127.0.0.1:4403`
- `Meshtastic DM identity:` listing meshtasticd's live node id
- OTA `>> PKT` lines continue under load (not only at boot)

Optional CLI probe (**stop Meshpoint first**; meshtasticd allows only one Phone API client):

```bash
sudo systemctl stop meshpoint
/opt/meshpoint/venv/bin/meshtastic --host localhost:4403 --info
sudo systemctl start meshpoint
```

---

## Operator rules

- **meshtasticd owns RF identity.** Meshpoint does not broadcast NodeInfo on the Node platform; meshtasticd advertises the HAT's node id.
- **Do not run** `meshtastic --host localhost:4403` while Meshpoint is running (steals the single client slot).
- **Restart order:** `meshtasticd` first, then `meshpoint`.
- **Direct messages** target meshtasticd's node id (derived from the HAT MAC), which may differ from `transmit.node_id` in `local.yaml`. Meshpoint routes DMs to both ids when they differ. Prefer removing a stale pinned `transmit.node_id` on Node installs unless you need it for upstream identity.

---

## Return to gateway mode

Gateway users who accidentally applied the experimental channel must move back to Stable and re-run the gateway installer. See [Migrate gateway to Node](MIGRATE-GATEWAY-TO-NODE.md) on the `feat/wismesh-hat` branch for the full two-way procedure (`meshpoint migrate-platform`).

Quick recovery outline:

1. Settings → Updates → **Stable (main)** → Apply (or `git checkout main && git pull`).
2. `sudo ./scripts/install.sh` (no `--platform node`).
3. `sudo meshpoint setup` and restart.

---

## Feedback

This track is early. Open an issue on [GitHub](https://github.com/KMX415/meshpoint/issues) with hardware model, branch SHA, and `journalctl -u meshpoint -u meshtasticd` excerpts (redact API keys and channel PSKs).
