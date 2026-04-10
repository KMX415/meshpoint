"""MeshCore USB companion setup steps for the Meshpoint wizard."""

from __future__ import annotations

from src.cli.hardware_detect import HardwareReport


def maybe_add_meshcore_usb(
    config: dict,
    report: HardwareReport,
    confirm_fn,
    choose_fn,
) -> None:
    """Offer to enable MeshCore USB monitoring if USB serial ports exist."""
    capture_port = config.get("capture", {}).get("serial_port")
    candidates = [
        p for p in report.meshcore_usb_candidates if p != capture_port
    ]

    if not candidates:
        return

    print()
    print("        USB serial port(s) detected that could be a MeshCore node:")
    for port in candidates:
        print(f"          - {port}")
    print()
    print("        If you have a MeshCore device (Heltec, T-Beam, etc.) plugged")
    print("        in via USB, Mesh Point can monitor its traffic automatically.")
    print()

    if not confirm_fn("Enable MeshCore USB monitoring?"):
        config.setdefault("capture", {}).setdefault(
            "meshcore_usb", {}
        )["auto_detect"] = False
        print("        MeshCore USB disabled.")
        print()
        return

    sources = config.setdefault("capture", {}).setdefault("sources", [])
    if "meshcore_usb" not in sources:
        sources.append("meshcore_usb")

    if len(candidates) == 1:
        chosen_port = candidates[0]
    else:
        chosen_port = choose_fn(
            "Select MeshCore USB port:", candidates
        )

    config["capture"].setdefault("meshcore_usb", {})["serial_port"] = (
        chosen_port
    )
    print(f"        MeshCore USB enabled on {chosen_port}")
    print()

    selected_region = config.get("radio", {}).get("region", "US")
    configure_meshcore_radio(chosen_port, selected_region, confirm_fn)


def configure_meshcore_radio(
    port: str,
    region: str = "US",
    confirm_fn=None,
    prompt_float_fn=None,
) -> None:
    """Configure the MeshCore companion's radio frequency.

    If the selected region has a known MeshCore preset (US, EU, ANZ),
    it is applied automatically. Otherwise the user is prompted for
    custom parameters or can skip.
    """
    import time

    from src.cli.meshcore_radio_config import (
        REGION_PRESETS,
        configure_radio,
        query_radio,
        verify_radio,
    )

    if confirm_fn is None:
        from src.cli.setup_wizard import _confirm as confirm_fn
    if prompt_float_fn is None:
        from src.cli.setup_wizard import _prompt_float as prompt_float_fn

    print("        Querying companion radio settings...")
    status = query_radio(port)

    if status:
        model_str = f" ({status.model})" if status.model else ""
        print(f"        Device: {status.name}{model_str}")
        print(f"        Current: {status.summary()}")
    else:
        print("        Could not read current radio settings.")

    print()

    meshcore_region_map = {"US": "US", "EU_868": "EU", "ANZ": "ANZ"}
    auto_preset_key = meshcore_region_map.get(region)

    if auto_preset_key and auto_preset_key in REGION_PRESETS:
        preset = REGION_PRESETS[auto_preset_key]
        print(f"        Applying {auto_preset_key} MeshCore preset")
        print(f"        ({preset.label})")
        if not confirm_fn("Apply this preset?", default_yes=True):
            print("        Skipped. Configure manually later if needed.")
            print()
            return
        freq = preset.frequency_mhz
        bw = preset.bandwidth_khz
        sf = preset.spreading_factor
        cr = preset.coding_rate
    else:
        print("        No standard MeshCore preset for your region.")
        print("        Enter custom radio parameters, or skip.")
        print()
        if not confirm_fn("Enter custom MeshCore radio settings?"):
            print("        Skipped.")
            print()
            return
        freq = prompt_float_fn("Frequency MHz (e.g. 910.525):")
        bw = prompt_float_fn("Bandwidth kHz (e.g. 62.5):")
        sf_val = prompt_float_fn("Spreading factor (e.g. 7):")
        cr_val = prompt_float_fn("Coding rate (e.g. 5):")
        if None in (freq, bw, sf_val, cr_val):
            print("        Invalid input. Skipping radio configuration.")
            print()
            return
        sf = int(sf_val)
        cr = int(cr_val)

    print(f"        Setting radio to {freq} MHz / BW{bw} / SF{sf} / CR{cr}...")

    ok = configure_radio(port, freq, bw, sf, cr)
    if not ok:
        print("        Failed to configure radio. Check the device and retry.")
        print()
        return

    print("        Radio configured. Companion is rebooting...")
    time.sleep(4)

    verified = verify_radio(port)
    if verified:
        print(f"        Verified: {verified.summary()}")
    else:
        print("        Could not verify (device may still be rebooting).")
        print("        The settings will apply on next power cycle.")

    print()
