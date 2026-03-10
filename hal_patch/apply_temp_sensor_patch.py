#!/usr/bin/env python3
"""
Patches lgw_start(), lgw_stop(), and lgw_get_temperature() in loragw_hal.c
to make the STTS751 I2C temperature sensor optional.

The RAK2287 concentrator module does not include a temperature sensor.
Without this patch the HAL aborts on startup when the sensor is absent.
When no sensor is found the HAL will use a fixed 25 °C default.

Usage:
    python3 apply_temp_sensor_patch.py /opt/sx1302_hal/libloragw/src/loragw_hal.c
"""
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Patch 1 – lgw_start(): sensor probe loop
# ---------------------------------------------------------------------------

START_ORIGINAL = """\
        /* Find the temperature sensor on the known supported ports */
        for (i = 0; i < (int)(sizeof I2C_PORT_TEMP_SENSOR); i++) {
            ts_addr = I2C_PORT_TEMP_SENSOR[i];
            err = i2c_linuxdev_open(I2C_DEVICE, ts_addr, &ts_fd);
            if (err != LGW_I2C_SUCCESS) {
                printf("ERROR: failed to open I2C for temperature sensor on port 0x%02X\\n", ts_addr);
                return LGW_HAL_ERROR;
            }

            err = stts751_configure(ts_fd, ts_addr);
            if (err != LGW_I2C_SUCCESS) {
                printf("INFO: no temperature sensor found on port 0x%02X\\n", ts_addr);
                i2c_linuxdev_close(ts_fd);
                ts_fd = -1;
            } else {
                printf("INFO: found temperature sensor on port 0x%02X\\n", ts_addr);
                break;
            }
        }
        if (i == sizeof I2C_PORT_TEMP_SENSOR) {
            printf("ERROR: no temperature sensor found.\\n");
            return LGW_HAL_ERROR;
        }"""

START_PATCHED = """\
        /* Find the temperature sensor on the known supported ports */
        for (i = 0; i < (int)(sizeof I2C_PORT_TEMP_SENSOR); i++) {
            ts_addr = I2C_PORT_TEMP_SENSOR[i];
            err = i2c_linuxdev_open(I2C_DEVICE, ts_addr, &ts_fd);
            if (err != LGW_I2C_SUCCESS) {
                printf("WARNING: could not open I2C on port 0x%02X\\n", ts_addr);
                ts_fd = -1;
                continue;
            }

            err = stts751_configure(ts_fd, ts_addr);
            if (err != LGW_I2C_SUCCESS) {
                printf("INFO: no temperature sensor found on port 0x%02X\\n", ts_addr);
                i2c_linuxdev_close(ts_fd);
                ts_fd = -1;
            } else {
                printf("INFO: found temperature sensor on port 0x%02X\\n", ts_addr);
                break;
            }
        }
        if (ts_fd < 0) {
            printf("WARNING: no temperature sensor found, using default 25 C\\n");
        }"""


# ---------------------------------------------------------------------------
# Patch 2 – lgw_get_temperature(): fall back to 25 °C
# ---------------------------------------------------------------------------

TEMP_ORIGINAL = """\
        case LGW_COM_SPI:
            err = stts751_get_temperature(ts_fd, ts_addr, temperature);
            break;"""

TEMP_PATCHED = """\
        case LGW_COM_SPI:
            if (ts_fd > 0) {
                err = stts751_get_temperature(ts_fd, ts_addr, temperature);
            } else {
                *temperature = 25.0;
                err = LGW_HAL_SUCCESS;
            }
            break;"""


# ---------------------------------------------------------------------------
# Patch 3 – lgw_stop(): skip I2C close when fd is invalid
# ---------------------------------------------------------------------------

STOP_ORIGINAL = """\
        DEBUG_MSG("INFO: Closing I2C for temperature sensor\\n");
        x = i2c_linuxdev_close(ts_fd);
        if (x != 0) {
            printf("ERROR: failed to close I2C temperature sensor device (err=%i)\\n", x);
            err = LGW_HAL_ERROR;
        }"""

STOP_PATCHED = """\
        if (ts_fd > 0) {
            DEBUG_MSG("INFO: Closing I2C for temperature sensor\\n");
            x = i2c_linuxdev_close(ts_fd);
            if (x != 0) {
                printf("ERROR: failed to close I2C temperature sensor device (err=%i)\\n", x);
                err = LGW_HAL_ERROR;
            }
        }"""


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

PATCHES = [
    ("lgw_start (temp sensor probe)", START_ORIGINAL, START_PATCHED),
    ("lgw_get_temperature (fallback)", TEMP_ORIGINAL, TEMP_PATCHED),
    ("lgw_stop (I2C close guard)", STOP_ORIGINAL, STOP_PATCHED),
]


def _validate_path(raw: str) -> Path:
    resolved = Path(raw).resolve()
    if not resolved.is_file():
        print(f"ERROR: not a file: {resolved}")
        sys.exit(1)
    if resolved.suffix != ".c":
        print(f"ERROR: expected a .c source file, got: {resolved.name}")
        sys.exit(1)
    return resolved


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-loragw_hal.c>")
        sys.exit(1)

    path = _validate_path(sys.argv[1])

    with open(path, "r") as fh:
        source = fh.read()

    source = source.replace("\r\n", "\n")

    applied = 0
    skipped = 0

    for label, original, patched in PATCHES:
        if patched in source:
            print(f"  [{label}] already patched, skipping.")
            skipped += 1
            continue
        if original not in source:
            print(f"  [{label}] WARNING: original text not found -- skipping.")
            continue
        source = source.replace(original, patched, 1)
        print(f"  [{label}] patched.")
        applied += 1

    if applied > 0:
        with open(path, "w", newline="\n") as fh:
            fh.write(source)
        print(f"\n{applied} patch(es) applied, {skipped} already present.")
    elif skipped == len(PATCHES):
        print("\nAll patches already applied.")
    else:
        print("\nERROR: some patches could not be applied.")
        sys.exit(1)


if __name__ == "__main__":
    main()
