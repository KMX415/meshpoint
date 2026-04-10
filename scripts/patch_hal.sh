#!/usr/bin/env bash
#
# Patch and recompile the SX1302 HAL for TX sync word support.
#
# The stock HAL hardcodes TX sync words to LoRaWAN values (0x12/0x34).
# This patch makes TX use the same sync word configured for RX (e.g.
# 0x2B for Meshtastic), so transmitted packets are heard by mesh nodes.
#
# Run once after updating to enable Meshtastic TX. Idempotent.
# Requires HAL source at /opt/sx1302_hal (preserved from install.sh).
#
# Usage:
#   sudo /opt/meshpoint/scripts/patch_hal.sh
#

set -euo pipefail

HAL_SRC="/opt/sx1302_hal/libloragw/src/loragw_sx1302.c"
HAL_DIR="/opt/sx1302_hal"
LIB_DEST="/usr/local/lib/libloragw.so"

info()  { echo "[patch_hal] $*"; }
fail()  { echo "[patch_hal] ERROR: $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
    fail "Must run as root (sudo)"
fi

if [ ! -f "$HAL_SRC" ]; then
    fail "HAL source not found at $HAL_SRC. Run install.sh for a fresh build."
fi

if grep -q "sx1302_tx_sw_peak1" "$HAL_SRC"; then
    info "TX sync word patch already applied"
else
    info "Applying TX sync word patch..."
    python3 - "$HAL_SRC" <<'TXPATCH'
import re, sys
from pathlib import Path

f = Path(sys.argv[1])
s = f.read_text()

if "sx1302_tx_sw_peak1" not in s:
    s = s.replace(
        "int sx1302_lora_syncword(",
        "static uint8_t sx1302_tx_sw_peak1 = 2;\n"
        "static uint8_t sx1302_tx_sw_peak2 = 4;\n\n"
        "int sx1302_lora_syncword(",
        1
    )

if "sx1302_tx_sw_peak1 = sw_reg1" not in s:
    s = s.replace(
        "    sw_reg2 = 4;\n    }\n\n    err |= lgw_reg_w("
        "SX1302_REG_RX_TOP_FRAME_SYNCH0_SF5_PEAK1_POS_SF5",
        "    sw_reg2 = 4;\n    }\n\n"
        "    sx1302_tx_sw_peak1 = sw_reg1;\n"
        "    sx1302_tx_sw_peak2 = sw_reg2;\n\n"
        "    err |= lgw_reg_w("
        "SX1302_REG_RX_TOP_FRAME_SYNCH0_SF5_PEAK1_POS_SF5",
        1
    )

tx_re = re.compile(
    r'([ \t]*)/\* Syncword \*/\n'
    r'[ \t]*if \(\(lwan_public == false\)[^\n]*\{\n'
    r'[^\n]*Setting LoRa syncword 0x12[^\n]*\n'
    r'[^\n]*FRAME_SYNCH_0_PEAK1_POS[^\n]*,\s*2\)[^\n]*\n'
    r'[^\n]*CHECK_ERR[^\n]*\n'
    r'[^\n]*FRAME_SYNCH_1_PEAK2_POS[^\n]*,\s*4\)[^\n]*\n'
    r'[^\n]*CHECK_ERR[^\n]*\n'
    r'[ \t]*\} else \{[^\n]*\n'
    r'[^\n]*Setting LoRa syncword 0x34[^\n]*\n'
    r'[^\n]*FRAME_SYNCH_0_PEAK1_POS[^\n]*,\s*6\)[^\n]*\n'
    r'[^\n]*CHECK_ERR[^\n]*\n'
    r'[^\n]*FRAME_SYNCH_1_PEAK2_POS[^\n]*,\s*8\)[^\n]*\n'
    r'[^\n]*CHECK_ERR[^\n]*\n'
    r'[ \t]*\}'
)

def repl(m):
    ws = m.group(1)
    return (
        f"{ws}/* Syncword */\n"
        f"{ws}err = lgw_reg_w(SX1302_REG_TX_TOP_FRAME_SYNCH_0_PEAK1_POS"
        f"(pkt_data->rf_chain), sx1302_tx_sw_peak1);\n"
        f"{ws}CHECK_ERR(err);\n"
        f"{ws}err = lgw_reg_w(SX1302_REG_TX_TOP_FRAME_SYNCH_1_PEAK2_POS"
        f"(pkt_data->rf_chain), sx1302_tx_sw_peak2);\n"
        f"{ws}CHECK_ERR(err);"
    )

new_s, n = tx_re.subn(repl, s, count=1)
if n == 0:
    print("FAIL: TX sync word section not found")
    sys.exit(1)

Path(sys.argv[1]).write_text(new_s)
print("OK: all patches applied")
TXPATCH
fi

info "Compiling libloragw (this takes a few minutes)..."
cd "$HAL_DIR"
mkdir -p pic_obj

for src in libtools/src/*.c; do
    gcc -c -O2 -fPIC -Wall -Wextra -std=c99 \
        -Ilibtools/inc -Ilibtools \
        "$src" -o "pic_obj/$(basename "${src%.c}.o")"
done

for src in libloragw/src/*.c; do
    gcc -c -O2 -fPIC -Wall -Wextra -std=c99 \
        -Ilibloragw/inc -Ilibloragw -Ilibtools/inc \
        "$src" -o "pic_obj/$(basename "${src%.c}.o")"
done

gcc -shared -o libloragw/libloragw.so pic_obj/*.o -lrt -lm -lpthread

cp libloragw/libloragw.so "$LIB_DEST"
ldconfig

info "Done. Restart meshpoint: sudo systemctl restart meshpoint"
