# meshtasticd LoRa presets (WisMesh Node)

Bundled Portduino presets for the RAK6421 WisMesh Pi HAT. Copied to
`/etc/meshtasticd/config.d/` by `scripts/install_meshtasticd.sh` when the
meshtasticd Debian package does not ship the matching file yet.

| File | Module | Notes |
|------|--------|-------|
| `lora-RAK6421-13302-slot1.yaml` | RAK13302 1W | **Default.** `Enable_Pins` + `TX_GAIN_LORA` for SKY66122 PA |
| `lora-RAK6421-13300-slot1.yaml` | RAK13300 | Standard ~22 dBm; override via `meshtasticd.preset` in `local.yaml` |

Upstream source: [Meshtastic firmware `bin/config.d/`](https://github.com/meshtastic/firmware/tree/master/bin/config.d).
