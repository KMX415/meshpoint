"""Compatibility fix for the pinned openHop host radio API.

Its configure_radio path applies LoRa parameters but omits set_tx_power.
Fail closed if the pinned source shape changes instead of patching blindly.
"""
import sys
from pathlib import Path


def patch_power(path: Path) -> None:
    source = path.read_text(encoding='utf-8')
    marker = '            self._sync_repeater_handler_radio_config(radio_cfg)'
    insertion = '''            # Meshpoint: configure_radio does not apply TX power.
            if getattr(radio, "tx_power", None) != radio_cfg["tx_power"]:
                if not hasattr(radio, "set_tx_power") or not radio.set_tx_power(radio_cfg["tx_power"]):
                    return False

'''
    if insertion in source:
        return
    if source.count(marker) != 1:
        raise RuntimeError('Pinned openHop power patch no longer matches; review dependency upgrade')
    path.write_text(source.replace(marker, insertion + marker), encoding='utf-8')


if __name__ == '__main__':
    patch_power(Path(sys.argv[1]))
