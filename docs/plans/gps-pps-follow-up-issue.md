# GitHub issue draft: HAL GPS/PPS sync on SX1303 (follow-up to #65)

**Title:** `feat(hal): GPS PPS timestamp sync via lgw_gps_* for RAK SX1303 HAT`

**Labels:** `enhancement`, `hardware`, `hal`

---

## Context

PR #65 (RAK SX1303 HAL guard + `location.source: uart`) deliberately split two GPS concerns:

| Layer | Config | Purpose |
|--------|--------|---------|
| Dashboard / NodeInfo | `location.source` (`static`, `gpsd`, `uart`) | Human-readable lat/lon |
| Concentrator timestamps | `radio.gps_pps_*` + Semtech `lgw_gps_*` | Align `timestamp_us` with GPS via PPS |

On RAK Pi gateways the u-blox speaks NMEA/UBX on `/dev/ttyAMA0` and drives a PPS line into the SX1302/SX1303. Meshpoint can use the HAL to parse UBX, call `lgw_gps_sync` on `UBX-NAV-TIMEGPS`, and enable `sx1302_gps_enable(true)` — but only when `libloragw` includes `loragw_gps.c`.

## Problem

Without PPS sync, packet `timestamp_us` values are concentrator-relative counters. That is fine for RSSI/SNR analytics but weak for:

- Correlating captures to wall-clock or external sensors
- Future TDoA / multilateration experiments
- Debugging “when did this burst happen?” across reboots

## Proposed solution

1. ctypes bindings for `lgw_gps_enable`, `lgw_parse_nmea`/`ubx`, `lgw_gps_get`, `lgw_gps_sync`, `lgw_get_trigcnt`, `lgw_cnt2utc`, `sx1302_gps_enable`.
2. Background reader thread after `lgw_start()`.
3. Config under `radio:`:
   - `gps_pps_enabled` (default `false`)
   - `gps_pps_tty_path` (default `/dev/ttyAMA0`)
   - `gps_family` (default `ubx7`)
   - `gps_pps_target_baud` (default `0` = HAL default)
4. Startup guard: reject `gps_pps_enabled` + `location.source: uart` on the same TTY.
5. `GET /api/device/gps-pps-status` for operators.
6. Docs in `CONFIGURATION.md` with the uart vs PPS matrix.

## Acceptance criteria

- [ ] With `gps_pps_enabled: true` on hardware with PPS wired, logs show `GPS/PPS sync #1 ok` after fix.
- [ ] `GET /api/device/gps-pps-status` reports `last_sync_ok: true` and increasing `sync_count`.
- [ ] Misconfigured dual-UART use fails at config load with a clear error.
- [ ] Graceful degrade when HAL lacks GPS symbols (info log, concentrator still starts).
- [ ] Unit tests mock `libloragw` GPS entry points.

## Out of scope (this issue)

- Automatic UBX CFG-PPS programming (operators may use u-center / `gpsd` once).
- Sharing one UART between HAL PPS and `UartSource` (documented conflict; use `gpsd` or `static` for map coords).
- Spectral scan / SX1261 path changes (covered in #65).

## Hardware test plan

1. RAK2287/5146 + Pi, `chip version 0x12` (SX1303), outdoor antenna.
2. `config/local.yaml`:
   ```yaml
   radio:
     gps_pps_enabled: true
   location:
     source: static   # or gpsd on USB
   ```
3. `journalctl -u meshpoint -f` → expect PPS sync lines.
4. `curl -s -H "Authorization: Bearer …" http://127.0.0.1:8080/api/device/gps-pps-status | jq`

## References

- Semtech `loragw_gps.h` / `loragw_sx1302.h` in sx1302_hal
- Related: #65, RAK `install.sh` UART enable for `/dev/ttyAMA0`
