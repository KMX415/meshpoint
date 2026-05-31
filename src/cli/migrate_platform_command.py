"""Switch Meshpoint between Gateway (SX1302) and Node (meshtasticd) platforms."""

from __future__ import annotations

import argparse
import subprocess

from src.config import save_section_to_yaml
from src.cli.hardware_detect import detect_all


def run_migrate_platform(args: argparse.Namespace) -> int:
    target = args.to.strip().lower()
    if target not in ("node", "gateway"):
        print(f"  Unknown platform: {target!r}. Use 'node' or 'gateway'.")
        return 1

    report = detect_all()
    print(f"  Hardware: {report.hardware_description}")
    print(f"  Detected platform: {report.platform}")

    if target == "node":
        if not report.wismesh_hat_detected and not args.force:
            print(
                "  No WisMesh HAT detected. Re-run with --force if you "
                "intentionally want Node (meshtasticd) mode."
            )
            return 1
        save_section_to_yaml("device", {"platform": "node"})
        save_section_to_yaml("capture", {"sources": ["meshtasticd"]})
        print("  Updated local.yaml: platform=node, capture.sources=[meshtasticd]")
        print("")
        print("  Next steps:")
        print("    sudo ./scripts/install.sh --platform node")
        print("    sudo meshpoint setup   # if not already configured")
        print("    sudo systemctl restart meshtasticd meshpoint")
    else:
        if not report.concentrator_available and not args.force:
            print(
                "  No SX1302/SX1303 concentrator detected. Re-run with "
                "--force if you intentionally want Gateway mode."
            )
            return 1
        save_section_to_yaml("device", {"platform": "gateway"})
        save_section_to_yaml("capture", {"sources": ["concentrator"]})
        print("  Updated local.yaml: platform=gateway, capture.sources=[concentrator]")
        print("")
        print("  Next steps:")
        print("    sudo ./scripts/install.sh --platform gateway")
        print("    sudo systemctl restart meshpoint")

    if args.restart:
        print("  Restarting meshpoint service...")
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "meshpoint"],
            check=False,
        )
        if result.returncode != 0:
            print("  Restart failed. Run: sudo systemctl restart meshpoint")
            return result.returncode

    return 0


def add_migrate_platform_parser(sub) -> None:
    parser = sub.add_parser(
        "migrate-platform",
        help="Switch between Gateway (SX1302) and Node (meshtasticd) mode",
    )
    parser.add_argument(
        "--to",
        required=True,
        choices=["node", "gateway"],
        help="Target platform",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even when hardware detection disagrees",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart meshpoint after updating local.yaml",
    )
    parser.set_defaults(handler=run_migrate_platform)
