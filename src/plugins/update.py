"""Replace disabled plugin code with filesystem rollback on failed persistence."""
from pathlib import Path
import shutil
import tempfile
from src.plugins import installer


def replace_disabled(runtime, catalog, source, entry, persist):
    pid = entry["id"]
    dest = runtime.apps_dir / pid
    if dest.is_symlink() or dest.resolve().parent != runtime.apps_dir.resolve():
        raise ValueError("Plugin directory is not safe to replace")
    settings = runtime.config.plugins.get(pid, {})
    installed_source = settings.get("source", {})
    if installed_source.get("url") != source["url"]:
        raise ValueError("Updates must come from the plugin's original source")
    with tempfile.TemporaryDirectory(prefix="meshpoint-update-") as temporary:
        backup = Path(temporary) / pid
        shutil.copytree(dest, backup, symlinks=True)
        try:
            result = installer.install_from_source(catalog["owner"], catalog["repo"], source["ref"],
                                                   entry, runtime.apps_dir)
            updated = {**settings, "enabled": False,
                       "source": {"url": source["url"], "commit": source["ref"]}}
            persist("plugins", {pid: updated})
        except Exception:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(backup, dest, symlinks=True)
            raise
    runtime.config.plugins[pid] = updated
    runtime.states.pop(pid, None)
    runtime.discover()
    return result
