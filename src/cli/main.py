"""Mesh Point CLI -- argparse dispatcher for management subcommands."""

from __future__ import annotations

import argparse
import subprocess
import sys

VERSION = "0.1.0"


def cmd_setup(_args: argparse.Namespace) -> None:
    from src.cli.setup_wizard import run_setup
    run_setup()


def cmd_status(_args: argparse.Namespace) -> None:
    from src.cli.status_command import show_status
    show_status()


def cmd_logs(_args: argparse.Namespace) -> None:
    try:
        subprocess.run(
            ["journalctl", "-u", "meshpoint", "-f", "--no-pager", "-n", "100", "-o", "cat"],
            check=False,
        )
    except KeyboardInterrupt:
        pass


def cmd_restart(_args: argparse.Namespace) -> None:
    print("  Restarting meshpoint service...")
    result = subprocess.run(
        ["sudo", "systemctl", "restart", "meshpoint"],
        check=False,
    )
    if result.returncode == 0:
        print("  Service restarted.")
    else:
        print("  Failed to restart. Check: meshpoint logs")


def cmd_stop(_args: argparse.Namespace) -> None:
    print("  Stopping meshpoint service...")
    subprocess.run(["sudo", "systemctl", "stop", "meshpoint"], check=False)
    print("  Service stopped.")


def cmd_version(_args: argparse.Namespace) -> None:
    print(f"  Mesh Point v{VERSION}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="meshpoint",
        description="Mesh Radar -- Mesh Point management CLI",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Run the interactive setup wizard")
    sub.add_parser("status", help="Show device status and health")
    sub.add_parser("logs", help="Tail the service logs (journalctl)")
    sub.add_parser("restart", help="Restart the meshpoint service")
    sub.add_parser("stop", help="Stop the meshpoint service")
    sub.add_parser("version", help="Print version information")

    args = parser.parse_args()

    dispatch = {
        "setup": cmd_setup,
        "status": cmd_status,
        "logs": cmd_logs,
        "restart": cmd_restart,
        "stop": cmd_stop,
        "version": cmd_version,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
