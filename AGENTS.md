# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Meshpoint is a Python 3.12+ FastAPI application (Meshtastic/MeshCore LoRa base station). Single-service architecture with embedded SQLite, vanilla JS frontend (no build step), and no containerization.

### Quick reference

| Task | Command |
|------|---------|
| Install deps | `pip install -r requirements.txt ruff pytest pytest-asyncio httpx` |
| Lint | `ruff check src/ tests/` |
| Test | `python3 -m pytest tests/ -v --ignore=tests/test_crypto_service.py --ignore=tests/test_meshtastic_decoder.py --ignore=tests/test_meshcore_decoder.py` |
| Run server | See "Starting the dev server" below |

### Starting the dev server

The server requires a valid Meshradar API key (`upstream.auth_token`) for the activation check in production. For development, bypass the activation check by patching `validate_activation`:

```bash
python3 -c "
import src.config as config_mod
import src.api.server as server_mod
config_mod.validate_activation = lambda cfg: None
server_mod.validate_activation = lambda cfg: None
import uvicorn
uvicorn.run('src.api.server:create_app', factory=True, host='0.0.0.0', port=8080, reload=False)
"
```

The server runs on port 8080. On first run it redirects to `/setup` to set an admin password.

### Dev config (`config/local.yaml`)

Create `config/local.yaml` to disable hardware dependencies:

```yaml
capture:
  sources: []
  meshcore_usb:
    auto_detect: false
upstream:
  enabled: false
  auth_token: "dev_placeholder"
transmit:
  enabled: false
mqtt:
  enabled: false
```

### Key gotchas

- **Activation gate**: `validate_activation()` in `src/config.py` calls `sys.exit(1)` without a valid Ed25519-signed API key. Must be patched for local dev without a real key.
- **No hardware needed for tests**: All 416 tests pass without LoRa hardware; hardware interactions are mocked.
- **Three test files excluded from CI**: `test_crypto_service.py`, `test_meshtastic_decoder.py`, `test_meshcore_decoder.py` are excluded (match CI config in `.github/workflows/ci.yml`).
- **SQLite auto-creates**: The database at `data/concentrator.db` is created automatically on first server start.
- **Frontend is static**: No build step needed. Vanilla HTML/CSS/JS served from `frontend/`.
- **PATH**: pip installs binaries to `/home/ubuntu/.local/bin` — ensure it's on PATH.
