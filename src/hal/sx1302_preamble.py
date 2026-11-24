"""Meshtastic service-modem RX settings for the supported SX1302 HAL 2.1 ABI."""

import ctypes
import logging

logger = logging.getLogger(__name__)

# Semtech V2.1.0 loragw_reg.h: RX_TOP_LORA_SERVICE_FSK_TXRX_CFG6/7
# PREAMBLE_SYMB_NB. These are register-table IDs, not bus addresses.
SERVICE_PREAMBLE_LOW = 916
SERVICE_PREAMBLE_HIGH = 917
MESHTASTIC_PREAMBLE = 16


def configure_service_preamble(lib) -> None:
    """Override HAL startup defaults, including on installs retaining their HAL.

    Call after every lgw_start(), which resets these RX-only registers.
    Neither the multi-SF receive engines nor TX packet parameters are changed.
    """
    try:
        write = lib.lgw_reg_w
        read = lib.lgw_reg_r
    except AttributeError as exc:
        raise RuntimeError("HAL lacks service-modem preamble register access") from exc
    write.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    write.restype = ctypes.c_int
    read.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_int32)]
    read.restype = ctypes.c_int
    for register, value in ((SERVICE_PREAMBLE_LOW, MESHTASTIC_PREAMBLE),
                            (SERVICE_PREAMBLE_HIGH, 0)):
        if write(register, value) != 0:
            raise RuntimeError("Cannot set LoRa service modem RX preamble")
    values = []
    for register in (SERVICE_PREAMBLE_LOW, SERVICE_PREAMBLE_HIGH):
        value = ctypes.c_int32()
        if read(register, ctypes.byref(value)) != 0:
            raise RuntimeError("Cannot read LoRa service modem RX preamble")
        values.append(value.value)
    if values != [MESHTASTIC_PREAMBLE, 0]:
        raise RuntimeError("LoRa service modem RX preamble verification failed")
    logger.info("LoRa service modem RX preamble verified: %d symbols", MESHTASTIC_PREAMBLE)
