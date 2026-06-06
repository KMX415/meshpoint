## Summary

Follow-up to #65: adds Semtech **HAL GPS/PPS** bindings so the SX1302/SX1303 concentrator can align internal packet `timestamp_us` with GPS time on RAK Pi HATs (u-blox on `/dev/ttyAMA0`, PPS into the concentrator).

This is **orthogonal** to `location.source: uart` / `gpsd`, which only feed dashboard coordinates and NodeInfo.

## Changes

**HAL (`src/hal/`)**
- `sx1302_gps_types.py` — `TimespecS`, `TrefS`, `CoordS`, GPS message constants.
- `sx1302_gps_signatures.py` + `apply_gps_signatures()` from `apply_signatures()`.
- `sx1302_gps.py` — `HalGpsPpsSync`: `lgw_gps_enable`, background UBX/NMEA parser, `lgw_gps_sync` on `UBX-NAV-TIMEGPS`, `sx1302_gps_enable`, optional `lgw_cnt2utc`.
- `SX1302Wrapper.start_gps_pps()` / `stop_gps_pps()`; `ConcentratorCaptureSource` starts PPS after `lgw_start()` when configured.

**Config**
- `radio.gps_pps_enabled`, `gps_pps_tty_path`, `gps_family`, `gps_pps_target_baud`.
- `validate_config_consistency()` rejects `gps_pps_enabled` + `location.source: uart` on the same TTY.

**API**
- `GET /api/device/gps-pps-status` — sync count, last error, reference counter.
- `radio_advanced` in `GET /api/config` exposes PPS fields.

**Docs**
- `CONFIGURATION.md` — GPS PPS section + uart/PPS matrix.
- `docs/plans/gps-pps-follow-up-issue.md` — issue template for trackers.

## Why

#65 fixed `lgw_start()` on RAK/SX1303 and wired UART for **map** GPS. Operators running SX1303 with PPS still need concentrator-time alignment for accurate packet timestamps — that path lives in `lgw_gps_*`, not in NMEA GGA parsing.

## Operator notes

| Need | Config |
|------|--------|
| Live map from HAT UART | `location.source: uart`, `gps_pps_enabled: false` |
| PPS timestamps + USB gpsd map | `location.source: gpsd`, `gps_pps_enabled: true` |
| PPS only, fixed coords | `location.source: static`, `gps_pps_enabled: true` |

Requires `libloragw` built with `loragw_gps.c`. If symbols are missing, Meshpoint logs once and continues without PPS.

## Type

- [x] Feature
- [x] Hardware change
- [x] Docs
- [ ] Bug fix
- [ ] UI (status API only; no dashboard card in this PR)

## Testing

- [x] Local unit tests
- [ ] Tested on RAK hardware (needs reviewer / field)

```bash
python -m unittest tests.test_hal_gps_pps tests.test_sx1302_wrapper_hal_guard -v
```

## Depends on

- Best reviewed **after** #65 merges (stacked from the same fork branch family). Can rebase onto `main` once #65 lands.

## Closes

<!-- Link issue when filed: Closes #NNN -->
