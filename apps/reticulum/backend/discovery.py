"""Opt-in interface discovery metadata; never automatically connect to peers."""
import re


def contact_address(value):
    address = str(value or "").strip().lower()
    if address and not re.fullmatch(r"[0-9a-f]{32}", address):
        raise ValueError("Operator LXMF address must contain exactly 32 hexadecimal characters")
    return address


def publication_block(config):
    address = contact_address(config.get("rnode_discovery_lxmf_address"))
    if config.get("rnode_discovery_enabled") is not True:
        return ""
    if config.get("rnode_enabled") is not True or not address:
        raise ValueError("Publishing an RNode interface requires an enabled RNode and an operator LXMF address")
    # RNS requires AP mode for discoverable RNode interfaces. Do not enable
    # transport, publish IFAC credentials or copy the device location.
    return ("    mode = access_point\n    discoverable = Yes\n"
            "    discovery_name = Meshpoint RNode\n    announce_interval = 360\n"
            "    publish_ifac = No\n"
            f"    discovery_lxmf_address = {address}\n")


def public_interfaces(rows):
    """Allowlist contact metadata; omit credentials, generated configs and hosts."""
    result = []
    for row in rows[:200]:
        if not isinstance(row, dict):
            continue
        try:
            address = contact_address(row.get("operator_lxmf_address"))
        except ValueError:
            address = ""
        result.append({
            "name": str(row.get("name") or "Unnamed interface")[:128],
            "type": str(row.get("type") or "Unknown")[:64],
            "status": str(row.get("status") or "unknown")[:32],
            "operator_lxmf_address": address,
        })
    return result
