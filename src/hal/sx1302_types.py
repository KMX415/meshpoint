"""ctypes struct definitions mirroring the Semtech SX1302 HAL (loragw_hal.h).

Shared between the wrapper and any module that builds or inspects
HAL-level packet structures. TX structs enable native LoRa transmission
through the SX1261 companion radio on the RAK2287.
"""

from __future__ import annotations

import ctypes


# ── RX configuration structs ────────────────────────────────────────

class LgwConfBoardS(ctypes.Structure):
    """Mirrors struct lgw_conf_board_s."""
    _fields_ = [
        ("lorawan_public", ctypes.c_bool),
        ("clksrc", ctypes.c_uint8),
        ("full_duplex", ctypes.c_bool),
        ("com_type", ctypes.c_int),
        ("com_path", ctypes.c_char * 64),
    ]


class LgwRssiTcompS(ctypes.Structure):
    """Mirrors struct lgw_rssi_tcomp_s."""
    _fields_ = [
        ("coeff_a", ctypes.c_float),
        ("coeff_b", ctypes.c_float),
        ("coeff_c", ctypes.c_float),
        ("coeff_d", ctypes.c_float),
        ("coeff_e", ctypes.c_float),
    ]


class LgwConfRxrfS(ctypes.Structure):
    """Mirrors struct lgw_conf_rxrf_s."""
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("freq_hz", ctypes.c_uint32),
        ("rssi_offset", ctypes.c_float),
        ("rssi_tcomp", LgwRssiTcompS),
        ("type", ctypes.c_int),
        ("tx_enable", ctypes.c_bool),
        ("single_input_mode", ctypes.c_bool),
    ]


class LgwConfRxifS(ctypes.Structure):
    """Mirrors struct lgw_conf_rxif_s."""
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("rf_chain", ctypes.c_uint8),
        ("freq_hz", ctypes.c_int32),
        ("bandwidth", ctypes.c_uint8),
        ("datarate", ctypes.c_uint32),
        ("sync_word_size", ctypes.c_uint8),
        ("sync_word", ctypes.c_uint64),
        ("implicit_hdr", ctypes.c_bool),
        ("implicit_payload_length", ctypes.c_uint8),
        ("implicit_crc_en", ctypes.c_bool),
        ("implicit_coderate", ctypes.c_uint8),
    ]


class LgwPktRxS(ctypes.Structure):
    """Mirrors struct lgw_pkt_rx_s."""
    _fields_ = [
        ("freq_hz", ctypes.c_uint32),
        ("freq_offset", ctypes.c_int32),
        ("if_chain", ctypes.c_uint8),
        ("status", ctypes.c_uint8),
        ("count_us", ctypes.c_uint32),
        ("rf_chain", ctypes.c_uint8),
        ("modem_id", ctypes.c_uint8),
        ("modulation", ctypes.c_uint8),
        ("bandwidth", ctypes.c_uint8),
        ("datarate", ctypes.c_uint32),
        ("coderate", ctypes.c_uint8),
        ("rssic", ctypes.c_float),
        ("rssis", ctypes.c_float),
        ("snr", ctypes.c_float),
        ("snr_min", ctypes.c_float),
        ("snr_max", ctypes.c_float),
        ("crc", ctypes.c_uint16),
        ("size", ctypes.c_uint16),
        ("payload", ctypes.c_uint8 * 256),
        ("ftime_received", ctypes.c_bool),
        ("ftime", ctypes.c_uint32),
    ]


# ── TX structs ──────────────────────────────────────────────────────

class LgwTxGainS(ctypes.Structure):
    """Mirrors struct lgw_tx_gain_s from loragw_hal.h.

    Field order must match the C struct exactly. For SX1250 radios
    (RAK2287), rf_power, pa_gain, and pwr_idx are the active fields.
    """
    _fields_ = [
        ("rf_power", ctypes.c_int8),
        ("dig_gain", ctypes.c_uint8),
        ("pa_gain", ctypes.c_uint8),
        ("dac_gain", ctypes.c_uint8),
        ("mix_gain", ctypes.c_uint8),
        ("offset_i", ctypes.c_int8),
        ("offset_q", ctypes.c_int8),
        ("pwr_idx", ctypes.c_uint8),
    ]


class LgwTxGainLutS(ctypes.Structure):
    """Mirrors struct lgw_tx_gain_lut_s (up to 16 entries)."""
    _fields_ = [
        ("lut", LgwTxGainS * 16),
        ("size", ctypes.c_uint8),
    ]


# ── SX1261 companion / spectral scan / LBT structs ──────────────────

LGW_LBT_CHANNEL_NB_MAX: int = 16


class LgwConfChanS(ctypes.Structure):
    """Mirrors struct lgw_conf_chan_s — one LBT channel descriptor."""
    _fields_ = [
        ("freq_hz", ctypes.c_uint32),
        ("bandwidth", ctypes.c_uint8),
        ("scan_time_us", ctypes.c_uint16),
        ("transmit_time_ms", ctypes.c_uint16),
    ]


class LgwConfLbtS(ctypes.Structure):
    """Mirrors struct lgw_conf_lbt_s.

    We never enable LBT (Listen Before Talk); this struct is only
    here so its bytes are correctly laid out inside
    ``LgwConfSx1261S``. ``enable=False`` makes the rest of the
    fields irrelevant from the HAL's perspective.
    """
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("rssi_target", ctypes.c_int8),
        ("nb_channel", ctypes.c_uint8),
        ("channels", LgwConfChanS * LGW_LBT_CHANNEL_NB_MAX),
    ]


class LgwConfSx1261S(ctypes.Structure):
    """Mirrors struct lgw_conf_sx1261_s.

    Required by ``lgw_spectral_scan_*``. The Semtech HAL gates
    spectral scan on this struct's ``enable`` flag — without an
    explicit ``lgw_sx1261_setconf(enable=true)`` call, every
    ``lgw_spectral_scan_start`` returns -1 with the HAL stderr
    line ``ERROR: sx1261 is not enabled, no spectral scan``.

    ``spi_path`` selects the SPI device used to talk to the SX1261
    companion radio. On RAK2287 / RAK5146 boards this is typically
    ``/dev/spidev0.1`` (separate from the SX1302's
    ``/dev/spidev0.0``); on other carriers it can match the SX1302
    path when the chip is daisy-chained behind the SX1302's SPI
    router.
    """
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("spi_path", ctypes.c_char * 64),
        ("rssi_offset", ctypes.c_int8),
        ("lbt_conf", LgwConfLbtS),
    ]


class LgwPktTxS(ctypes.Structure):
    """Mirrors struct lgw_pkt_tx_s.

    Fields map directly to the C struct in loragw_hal.h.
    Populate and pass to lgw_send() for LoRa transmission
    through the SX1261 companion on RF chain 0.
    """
    _fields_ = [
        ("freq_hz", ctypes.c_uint32),
        ("tx_mode", ctypes.c_uint8),
        ("count_us", ctypes.c_uint32),
        ("rf_chain", ctypes.c_uint8),
        ("rf_power", ctypes.c_int8),
        ("modulation", ctypes.c_uint8),
        ("freq_offset", ctypes.c_int8),
        ("bandwidth", ctypes.c_uint8),
        ("datarate", ctypes.c_uint32),
        ("coderate", ctypes.c_uint8),
        ("invert_pol", ctypes.c_bool),
        ("f_dev", ctypes.c_uint8),
        ("preamble", ctypes.c_uint16),
        ("no_crc", ctypes.c_bool),
        ("no_header", ctypes.c_bool),
        ("size", ctypes.c_uint16),
        ("payload", ctypes.c_uint8 * 256),
    ]
