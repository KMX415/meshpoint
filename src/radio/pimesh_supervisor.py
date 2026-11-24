#!/usr/bin/python3 -I
"""Root-owned, fixed-command PiMesh supervisor. Also importable for tests.

Installer copies this standalone stdlib-only module outside the app checkout.
Never import writable application modules from this privileged executable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

PROVISION = Path("/etc/meshpoint/pimesh.json")
STATE = Path("/var/lib/meshpoint-radio/state.json")
READY = Path("/run/meshpoint-radio/ready.json")
EXECUTABLE = "/usr/local/libexec/meshpoint-radio"
SERVICES = {"meshtastic": "meshtasticd", "meshcore": "meshpoint-openhop"}
PHASES_BUSY = {"queued", "stopping", "starting", "verifying", "rolling_back"}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        if os.name == "posix":
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


class Supervisor:
    def __init__(self, state=STATE, ready=READY, run=None, timeout=120):
        self.path, self.ready = state, ready
        self.run = run or self._systemctl
        self.timeout = timeout

    @staticmethod
    def _systemctl(action, service):
        subprocess.run(
            ["/usr/bin/systemctl", action, service],
            check=True,
            timeout=45,
            capture_output=True,
        )

    def save(self, state, phase, **values):
        state.update(phase=phase, updated_at=time.time(), **values)
        atomic_json(self.path, state)

    def stop_radios(self):
        for service in SERVICES.values():
            self.run("stop", service)
        # systemctl stop waits for completion; Conflicts= adds a second barrier.

    def activate(self, state, protocol):
        self.ready.unlink(missing_ok=True)
        self.save(state, "starting", active=protocol)
        self.run("start", SERVICES[protocol])
        self.run("start", "meshpoint")
        self.save(state, "verifying")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            health = read_json(self.ready)
            if (
                health.get("operation_id") == state["operation_id"]
                and health.get("protocol") == protocol
                and health.get("ready") is True
            ):
                return
            time.sleep(0.5)
        raise TimeoutError("Meshpoint radio handshake did not become ready")

    def switch(self, target):
        if target not in SERVICES:
            raise ValueError("Unknown radio protocol")
        state = read_json(self.path)
        previous = state.get("last_good", "meshtastic")
        if previous not in SERVICES:
            raise ValueError("Invalid saved protocol")
        if state.get("phase") == "ready" and state.get("active") == target:
            return state
        state.update(operation_id=uuid.uuid4().hex, target=target, error="")
        self.save(state, "stopping")
        try:
            self.run("stop", "meshpoint")
            self.stop_radios()
            self.activate(state, target)
            self.save(state, "ready", last_good=target, target=None)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            # Never log configuration, command stdout, or credentials here.
            self.save(
                state,
                "rolling_back",
                error="Switch failed; restoring previous protocol",
            )
            try:
                self.run("stop", "meshpoint")
                self.stop_radios()
                self.activate(state, previous)
                self.save(
                    state,
                    "ready",
                    target=None,
                    error="Switch failed. Previous protocol restored.",
                )
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                self.stop_radios()
                self.save(
                    state,
                    "failed",
                    active=previous,
                    target=None,
                    error="Both protocols failed readiness. Radio stopped; retry or inspect service logs.",
                )
                self.run("start", "meshpoint")
        return state

    def recover_boot(self):
        state = read_json(self.path)
        protocol = state.get("last_good", "meshtastic")
        if protocol not in SERVICES:
            raise ValueError("Invalid saved protocol")
        self.stop_radios()
        self.ready.unlink(missing_ok=True)
        self.save(
            state,
            "ready",
            active=protocol,
            target=None,
            operation_id=uuid.uuid4().hex,
            error="Interrupted switch recovered."
            if state.get("phase") in PHASES_BUSY
            else "",
        )
        self.run("start", SERVICES[protocol])


def main():
    import fcntl

    if os.geteuid() != 0:
        raise SystemExit("Root required")
    record = read_json(PROVISION)
    if (
        record.get("board") not in ("pimesh-v1", "pimesh-v2")
        or record.get("schema") != 1
    ):
        raise SystemExit("PiMesh is not provisioned")
    args = sys.argv[1:]
    if args == ["boot"]:
        Supervisor().recover_boot()
        return
    if (
        len(args) != 2
        or args[0] not in ("request", "switch")
        or args[1] not in SERVICES
    ):
        raise SystemExit("Usage: meshpoint-radio request|switch meshtastic|meshcore")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE.parent / "switch.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A radio switch is already running")
        if args[0] == "request":
            state = read_json(STATE)
            if state.get("phase") in PHASES_BUSY:
                raise SystemExit("A radio switch is already running")
            if state.get("active") == args[1] and state.get("phase") == "ready":
                print(json.dumps(state))
                return
            previous = dict(state)
            Supervisor().save(state, "queued", target=args[1], error="")
            try:
                subprocess.run(
                    [
                        "/usr/bin/systemd-run",
                        "--quiet",
                        "--collect",
                        "--unit=meshpoint-radio-switch",
                        "--property=Type=exec",
                        "--on-active=2s",
                        EXECUTABLE,
                        "switch",
                        args[1],
                    ],
                    check=True,
                    timeout=15,
                    capture_output=True,
                )
            except Exception:
                atomic_json(STATE, previous)
                raise
            print(json.dumps(state))
        else:
            Supervisor().switch(args[1])


if __name__ == "__main__":
    main()
