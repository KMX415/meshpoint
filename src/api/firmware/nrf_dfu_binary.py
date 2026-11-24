"""Resolve the adafruit-nrfutil binary for nRF DFU flash subprocesses."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional


class AdafruitNrfutilBinaryResolver:
    """Prefer venv-local adafruit-nrfutil next to ``sys.executable``, else PATH.

    Do not ``Path.resolve()`` the interpreter first: on Linux a venv
    ``python`` is often a symlink into ``/usr/bin``, which would miss
    sibling console scripts under ``venv/bin``.
    """

    _CANDIDATES = (
        "adafruit-nrfutil",
        "adafruit-nrfutil.exe",
        "adafruit_nrfutil",
        "adafruit_nrfutil.exe",
    )

    def resolve_path(self) -> Optional[str]:
        bin_dir = Path(sys.executable).parent
        for name in self._CANDIDATES:
            sibling = bin_dir / name
            if sibling.is_file():
                return str(sibling)
        return (
            shutil.which("adafruit-nrfutil")
            or shutil.which("adafruit_nrfutil")
        )

    def resolve_argv(self) -> list[str]:
        path = self.resolve_path()
        if path:
            return [path]
        return [sys.executable, "-m", "nordicsemi.__main__"]

    def missing_install_hint(self) -> Optional[str]:
        if self.resolve_path() is not None:
            return None
        try:
            import nordicsemi  # noqa: F401
        except ImportError:
            return (
                "adafruit-nrfutil is not installed in the Meshpoint venv. "
                "Run: sudo /opt/meshpoint/venv/bin/pip install "
                "adafruit-nrfutil && sudo systemctl restart meshpoint"
            )
        return None
