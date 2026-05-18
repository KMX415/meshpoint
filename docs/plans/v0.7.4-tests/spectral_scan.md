# Spectral-Scan Noise Floor — Test Checklist

Validates the SX1302 spectral scan path (`src/hal/sx1302_spectral_scan.py`, `src/api/telemetry/spectral_scan_service.py`) and its plumbing through `NoiseFloorTracker` to the sidebar telemetry rail.

The packet-derived rolling-minimum estimate is the **default** noise-floor source on every shipping board. The SX1302 spectral scan path is **opt-in** and only works on carriers where the SX1261 companion radio is wired to a Pi-visible SPI chip-select (Semtech SX1302CXXXGW1 reference kit and similar). RAK2287 / RAK5146 / SenseCap M1 wire the SX1261 behind the SX1302's internal SPI router, so spectral scan is not available on those boards and the packet-derived path is the production behaviour.

## Status

- [x] Hardware-validated on `.141` (RAK V2): packet-derived path active, spectral scan correctly skipped, service stays up
- [ ] Hardware-validated on `.15` (SenseCap M1): same expectation as `.141`
- [ ] Hardware-validated on Semtech SX1302CXXXGW1 reference kit (only board where opt-in spectral scan can be exercised)
- [ ] Browser-only checks complete

## Pre-conditions

- Service running on the target unit (`sudo systemctl status meshpoint`).
- Dashboard logged in as admin.
- Default config (`radio.sx1261_spi_path: ""`) for the packet-derived sections; explicitly set `radio.sx1261_spi_path: "/dev/spidev0.1"` for the opt-in section.

## 1. Default install: packet-derived path is active and stable

Goal: confirm the shipping default works on every supported carrier without crashing the service.

- [ ] On a fresh restart the journal logs `SX1261 spi_path empty; spectral scan disabled, falling back to packet-derived noise floor`.
- [ ] No `lgw_sx1261_setconf` errors appear before `lgw_start()`.
- [ ] `lgw_start() succeeded` (or equivalent) appears and the service reaches `Application startup complete`.
- [ ] Within 3 successfully-decoded packets the sidebar telemetry rail switches from `calibrating` to a real number.
- [ ] Hovering the readout shows the packet-derived tooltip variant (mentions "rolling minimum of recently decoded packets").
- [ ] After 30 minutes of normal RX traffic the displayed floor sits at a believable value for the install (e.g. `-115` to `-95 dBm` for typical rural / suburban / urban environments respectively).

## 2. Opt-in: spectral scan on a board that supports it

Skip this section on RAK / SenseCap hardware. Run on a Semtech SX1302CXXXGW1 reference kit or any custom carrier known to wire the SX1261 directly to `/dev/spidev0.1`.

- [ ] Set `radio.sx1261_spi_path: "/dev/spidev0.1"` and `radio.spectral_scan_interval_seconds: 60` in `local.yaml`.
- [ ] Restart. Journal contains `SX1261 companion configured for spectral scan (spi=/dev/spidev0.1)` and **no** `sx1261_check_status` errors.
- [ ] `SpectralScanService started: <freq> MHz, every 60s, first scan in 10s` follows.
- [ ] Within ~15 seconds the sidebar readout's tooltip switches to the spectral-scan variant ("SX1302 spectral scan").
- [ ] Tail the journal for ~3 minutes; one scan completes every 60 seconds (±1 s).
- [ ] Compare the dashboard reading to a Waveshare SX1262 HAT (or similar single-channel SDR) tuned to the same frequency and bandwidth. Numbers should agree within ~3 dB.

## 3. Opt-in failure mode is graceful (board doesn't expose SX1261)

Run on a RAK2287 / RAK5146 / SenseCap M1 unit (any board where the SX1261 is hidden behind the SX1302).

- [ ] Set `radio.sx1261_spi_path: "/dev/spidev0.1"` (deliberately wrong for this hardware).
- [ ] Restart. Journal contains `lgw_sx1261_setconf(spi=/dev/spidev0.1) failed (rc=-1); spectral scan disabled, falling back to packet-derived noise floor` **OR** `lgw_sx1261_setconf raised (...); spectral scan disabled, falling back to packet-derived noise floor`.
- [ ] **Critical:** the service still reaches `Application startup complete` — `lgw_start()` is **not** called after a failed SX1261 setconf, so the carrier-specific HAL state corruption that caused the v0.7.4 dev-cycle regression cannot recur.
- [ ] Sidebar readout populates from packet-derived data after the first 3+ packets arrive (same path as section 1).
- [ ] Revert `local.yaml` (`sx1261_spi_path: ""`) and restart to confirm the warning lines stop appearing.

## 4. Cadence and RX impact (only meaningful when section 2 passed)

Skip if spectral scan is not enabled on the unit under test.

- [ ] Tail `journalctl -u meshpoint -f` for ~3 minutes.
- [ ] One spectral-scan log line at DEBUG level (`Spectral scan: <freq> MHz floor=...`) appears every 60 seconds (give or take ~1 s).
- [ ] Packet RX continues normally throughout. No noticeable gap (>1 received packet drop attributable to the scan window).

## 5. Disable spectral scan via cadence config

Run on a unit where section 2 passed (only that unit can demonstrate the difference between "enabled" and "explicitly disabled").

- [ ] Set `radio.spectral_scan_interval_seconds: 0` in `local.yaml`, leave `sx1261_spi_path` set.
- [ ] Restart. The journal logs `Spectral scan disabled via radio.spectral_scan_interval_seconds`.
- [ ] No scan log lines appear at the configured cadence.
- [ ] The sidebar readout falls back to the packet-derived path; tooltip wording reflects this.

## 6. Configurable cadence

Run on a unit where section 2 passed.

- [ ] Set `radio.spectral_scan_interval_seconds: 300` in `local.yaml`.
- [ ] Restart. The journal logs `every 300s` in the service-start line.
- [ ] Subsequent scan log lines arrive ~5 minutes apart.
- [ ] Set `radio.spectral_scan_interval_seconds: 1` (intentionally too low). Restart. The service clamps to the 5 s minimum and the journal still reports usable cadence (no scan storm).

## 7. Frequency change reflects in scans

Run on a unit where section 2 passed.

- [ ] Edit `radio.frequency_mhz` to a different in-band value via the dashboard Configuration page.
- [ ] Restart. The journal `SpectralScanService started` line carries the new frequency.
- [ ] After the next scan, the sidebar readout's tooltip mentions the new frequency.

## 8. HAL graceful degradation (no symbols at all)

- [ ] On a unit whose `libloragw` is older than the patched HAL we ship (or temporarily symlink `/usr/local/lib/libloragw.so` to a stripped build for the test), restart the service.
- [ ] The journal logs `libloragw lacks lgw_sx1261_setconf; spectral scan unavailable` (with empty `sx1261_spi_path`) **or** `libloragw does not expose lgw_spectral_scan_*; spectral scan disabled, falling back to packet-derived noise floor` (with `sx1261_spi_path` set).
- [ ] No scan log lines appear at the configured cadence.
- [ ] The sidebar readout still populates from packet-derived data after the first 3+ packets arrive.

## 9. Frontend sparkline

- [ ] Watch the sidebar telemetry-rail noise sparkline for ~5 minutes.
- [ ] On packet-derived installs: a new sample is appended each time `NoiseFloorTracker.update` is called from a successfully-decoded packet (variable cadence, depends on RX traffic).
- [ ] On spectral-scan installs: one new sample appears per scan interval (e.g. 12 samples in 12 minutes at default cadence).
- [ ] Sparkline shape is smooth — no gaps or spikes that would suggest dropped frames over the websocket.

## Acceptance

- [ ] Sections 1 and 9 green on `.141` and `.15` (default packet-derived path on production hardware).
- [ ] Section 3 green on `.141` (failure mode is graceful, service stays up when SX1261 init fails).
- [ ] Sections 2, 4–7 green on a Semtech SX1302CXXXGW1 reference kit if one is available; otherwise documented as untested-on-supported-hardware in the release notes.
- [ ] No regression in CRC_BAD or CRC_OK packet rates compared to the same window before the spectral scan service was wired in.
