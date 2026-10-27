"""Own an unprivileged rnsd child and a separate Reticulum message store."""
import asyncio
import os
from pathlib import Path
import sys
import uuid
from src.plugins.python_dependencies import environment_dir
from . import state
from .config_routes import ReticulumUpdate
from .lxmf_service import LxmfService
from .rns_config import render_config


class ManagedReticulum(LxmfService):
    def __init__(self, *, database, plugin_dir, base, **kwargs):
        super().__init__(**kwargs)
        self.database = database
        self.plugin_dir = Path(plugin_dir)
        self.base = Path(base)
        self.daemon = None
        self.ready_file = None

    async def start(self):
        if not self.available:
            raise RuntimeError("Install Reticulum dependencies in Settings > Plugins")
        # Validate persisted settings too, before writing any interface config.
        cfg = state.to_dict()
        ReticulumUpdate.model_validate(cfg)
        content = render_config(cfg)
        self.base.mkdir(parents=True, exist_ok=True)
        await self.database.connect()
        await self.database.execute("""CREATE TABLE IF NOT EXISTS reticulum_peers (
            destination_hash TEXT PRIMARY KEY, display_name TEXT, aspect TEXT NOT NULL,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)""")
        await self.database.commit()
        config_dir = self.base / "rns_config"
        config_dir.mkdir(exist_ok=True)
        if config_dir.is_symlink() or (config_dir / "config").is_symlink():
            raise ValueError("Managed daemon configuration must not be a symlink")
        (config_dir / "config").write_text(content, encoding="utf-8")
        self.ready_file = self.base / (".ready-" + uuid.uuid4().hex)
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG")
               if key in os.environ}
        env["PYTHONPATH"] = str(environment_dir(self.plugin_dir.parent).resolve())
        self.daemon = await asyncio.create_subprocess_exec(
            sys.executable, "-B", str(self.plugin_dir / "backend" / "daemon_worker.py"),
            "--config", str(config_dir), "--ready", str(self.ready_file),
            env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        for _ in range(120):
            if self.daemon.returncode is not None:
                raise RuntimeError("Reticulum daemon exited before becoming ready")
            if self.ready_file.is_file():
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Reticulum daemon did not become ready")
        await super().start()

    async def stop(self):
        try:
            await super().stop()
        finally:
            # RNS may exit its client process when the shared daemon stops.
            # Flush our database and ready marker before terminating that daemon.
            if self.ready_file is not None:
                self.ready_file.unlink(missing_ok=True)
            await self.database.disconnect()
            if self.daemon is not None and self.daemon.returncode is None:
                self.daemon.terminate()
                try:
                    await asyncio.wait_for(self.daemon.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self.daemon.kill()
                    await self.daemon.wait()
            self.daemon = None
