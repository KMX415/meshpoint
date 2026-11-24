"""Fixed, hash-pinned optional wheels, installed outside the core environment.

No pip invocation, dependency resolution, setup scripts, or privilege changes.
Only the two reviewed pure-Python package trees are extracted. Existing core
cryptography and serial dependencies remain at their current versions.
"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
import urllib.request
import zipfile

WHEELS = (
    ("RNS", "1.5.3", "https://files.pythonhosted.org/packages/ed/29/101035b03be71c32f74bfd54a347f802ef9e820561cab6541658bc77d2da/rns-1.5.3-py3-none-any.whl",
     "0d02a0166b6f4d398549cb933153e7189c3fcde3c1fbcad03e47ce778091c351"),
    ("LXMF", "1.1.1", "https://files.pythonhosted.org/packages/99/61/e34e25278d20b3afa4c3ddb8cf5db6e1c1c3e5ab812bc8ba35cf46fb6f8e/lxmf-1.1.1-py3-none-any.whl",
     "3cdb4c5b3a4ec091ed538050228d8bd15db3ca4dfe7d69be3350ebc6c6d7e696"),
)
MAX_WHEEL = 8 * 1024 * 1024


def environment_dir(apps_dir):
    return apps_dir.parent / "environments" / "reticulum-v1"


def is_ready(apps_dir):
    base = environment_dir(apps_dir)
    if base.is_symlink():
        return False
    try:
        marker = json.loads((base / "installed.json").read_text(encoding="utf-8"))
        return marker == {name: digest for name, _, _, digest in WHEELS} and all(
            (base / name / "__init__.py").is_file() for name, _, _, _ in WHEELS)
    except (OSError, ValueError):
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Dependency downloads may not redirect")


def _download(url):
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(url, timeout=30) as response:
        data = response.read(MAX_WHEEL + 1)
    if len(data) > MAX_WHEEL:
        raise ValueError("Dependency wheel is too large")
    return data


def _extract(data, package, target):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 4000 or sum(e.file_size for e in entries) > 40 * 1024 * 1024:
            raise ValueError("Dependency wheel exceeds extraction limits")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                raise ValueError("Unsafe dependency wheel path")
            # Wheel metadata and entry-point scripts are not put on sys.path.
            if not path.parts or path.parts[0] != package or entry.is_dir():
                continue
            dest = target.joinpath(*path.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(entry))


def install_reticulum(apps_dir):
    if is_ready(apps_dir):
        return {"ready": True, "already_installed": True}
    target = environment_dir(apps_dir)
    if target.exists() or target.is_symlink():
        raise ValueError("Incomplete dependency directory exists; inspect it before retrying")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reticulum-", dir=target.parent) as temporary:
        staged = Path(temporary) / "library"
        staged.mkdir()
        for name, _, url, digest in WHEELS:
            data = _download(url)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("Dependency checksum verification failed")
            _extract(data, name, staged)
        (staged / "installed.json").write_text(
            json.dumps({name: digest for name, _, _, digest in WHEELS}), encoding="utf-8")
        staged.rename(target)
    return {"ready": True, "already_installed": False}
