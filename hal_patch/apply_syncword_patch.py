#!/usr/bin/env python3
"""
Patches sx1302_lora_syncword() in loragw_sx1302.c to support
custom LoRa sync words (e.g. 0x2B for Meshtastic).

The SX1302 converts sync word bytes to peak positions by doubling
each nibble independently:
    0x2B -> nibbles 0x2, 0xB -> peaks 4, 22

Usage:
    python3 apply_syncword_patch.py /opt/sx1302_hal/libloragw/src/loragw_sx1302.c
"""
import sys
from pathlib import Path

ORIGINAL_BODY = """\
    int err = LGW_REG_SUCCESS;

    /* Multi-SF modem configuration */
    DEBUG_MSG("INFO: configuring LoRa (Multi-SF) SF5->SF6 with syncword PRIVATE (0x12)\\n");
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF5_PEAK1_POS_SF5, 2);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF5_PEAK2_POS_SF5, 4);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF6_PEAK1_POS_SF6, 2);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF6_PEAK2_POS_SF6, 4);
    if (public == true) {
        DEBUG_MSG("INFO: configuring LoRa (Multi-SF) SF7->SF12 with syncword PUBLIC (0x34)\\n");
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF7TO12_PEAK1_POS_SF7TO12, 6);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF7TO12_PEAK2_POS_SF7TO12, 8);
    } else {
        DEBUG_MSG("INFO: configuring LoRa (Multi-SF) SF7->SF12 with syncword PRIVATE (0x12)\\n");
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF7TO12_PEAK1_POS_SF7TO12, 2);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF7TO12_PEAK2_POS_SF7TO12, 4);
    }

    /* LoRa Service modem configuration */
    if ((public == false) || (lora_service_sf == DR_LORA_SF5) || (lora_service_sf == DR_LORA_SF6)) {
        DEBUG_PRINTF("INFO: configuring LoRa (Service) SF%u with syncword PRIVATE (0x12)\\n", lora_service_sf);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH0_PEAK1_POS, 2);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH1_PEAK2_POS, 4);
    } else {
        DEBUG_PRINTF("INFO: configuring LoRa (Service) SF%u with syncword PUBLIC (0x34)\\n", lora_service_sf);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH0_PEAK1_POS, 6);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH1_PEAK2_POS, 8);
    }

    return err;"""

PATCHED_BODY = """\
    int err = LGW_REG_SUCCESS;

    /* Compute sync word register values.
     * Each nibble of the sync word byte is independently doubled
     * to get the SX1302 correlation peak position.
     * Example: 0x2B -> nibbles 0x2, 0xB -> regs 4, 22 (Meshtastic)
     *          0x12 -> nibbles 0x1, 0x2 -> regs 2, 4  (private)
     *          0x34 -> nibbles 0x3, 0x4 -> regs 6, 8  (public) */
    uint8_t sw_reg1, sw_reg2;
    if (public == true) {
        sw_reg1 = 6; /* 0x34 public */
        sw_reg2 = 8;
    } else if (lora_service_sf > 12) {
        sw_reg1 = ((lora_service_sf >> 4) & 0x0F) * 2;
        sw_reg2 = (lora_service_sf & 0x0F) * 2;
        DEBUG_PRINTF("INFO: custom sync word 0x%02X -> regs %u, %u\\n", lora_service_sf, sw_reg1, sw_reg2);
    } else {
        sw_reg1 = 2; /* 0x12 private */
        sw_reg2 = 4;
    }

    /* Multi-SF modem: SF5-SF6 */
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF5_PEAK1_POS_SF5, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF5_PEAK2_POS_SF5, sw_reg2);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF6_PEAK1_POS_SF6, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF6_PEAK2_POS_SF6, sw_reg2);

    /* Multi-SF modem: SF7-SF12 */
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF7TO12_PEAK1_POS_SF7TO12, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF7TO12_PEAK2_POS_SF7TO12, sw_reg2);

    /* LoRa Service modem */
    err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH0_PEAK1_POS, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH1_PEAK2_POS, sw_reg2);

    return err;"""

# The old v1 patch used byte-doubling (0x2B*2=0x56 -> regs 5,6) which is WRONG.
# Detect it so we can upgrade in-place.
OLD_BUGGY_FORMULA = "uint8_t doubled = lora_service_sf * 2;"
FIXED_FORMULA = "sw_reg1 = ((lora_service_sf >> 4) & 0x0F) * 2;"


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
        print(f"Usage: {sys.argv[0]} <path-to-loragw_sx1302.c>")
        sys.exit(1)

    path = _validate_path(sys.argv[1])

    with open(path, "r") as fh:
        source = fh.read()

    source = source.replace("\r\n", "\n")

    if FIXED_FORMULA in source:
        print("Already patched (correct nibble-doubling), skipping.")
        sys.exit(0)

    if OLD_BUGGY_FORMULA in source:
        print("Found old buggy byte-doubling patch, upgrading...")
        source = source.replace(
            "        uint8_t doubled = lora_service_sf * 2;\n"
            "        sw_reg1 = (doubled >> 4) & 0x0F;\n"
            "        sw_reg2 = doubled & 0x0F;\n"
            '        DEBUG_PRINTF("INFO: custom sync word 0x%02X -> regs 0x%X, 0x%X\\n", lora_service_sf, sw_reg1, sw_reg2);',
            "        sw_reg1 = ((lora_service_sf >> 4) & 0x0F) * 2;\n"
            "        sw_reg2 = (lora_service_sf & 0x0F) * 2;\n"
            '        DEBUG_PRINTF("INFO: custom sync word 0x%02X -> regs %u, %u\\n", lora_service_sf, sw_reg1, sw_reg2);',
            1,
        )
        with open(path, "w", newline="\n") as fh:
            fh.write(source)
        print("Upgraded to correct nibble-doubling formula.")
        sys.exit(0)

    if ORIGINAL_BODY not in source:
        print("ERROR: could not find original function body to patch.")
        print("The upstream HAL may have changed again.")
        sys.exit(1)

    patched = source.replace(ORIGINAL_BODY, PATCHED_BODY, 1)

    with open(path, "w", newline="\n") as fh:
        fh.write(patched)

    print("Patch applied successfully.")


if __name__ == "__main__":
    main()
