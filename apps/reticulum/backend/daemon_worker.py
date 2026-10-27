"""Fixed Reticulum daemon entry point, launched only by the enabled plugin."""
import argparse
from pathlib import Path
import time


def main():
    import RNS
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--ready", required=True)
    args = parser.parse_args()
    instance = RNS.Reticulum(configdir=args.config)
    if not instance.is_shared_instance:
        raise RuntimeError("The Meshpoint Reticulum instance is already owned by another daemon")
    Path(args.ready).touch()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
