"""Report declarative dependencies without executing downloaded code."""
import shutil


def dependency_report(manifest):
    missing = [name for name in manifest.executables if shutil.which(name) is None]
    return {
        "ready": not missing,
        "missing_commands": missing,
        "packages": list(manifest.apt),
        "manual_setup": bool(manifest.setup),
        "instructions": "Install the dependencies documented in the plugin README, then refresh and restart Meshpoint. Downloaded setup scripts are not run by the dashboard.",
    }
