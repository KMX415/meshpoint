#!/bin/bash
# Finish a dashboard-driven apply or rollback after git checkout/reset.
#
# Lightweight upgrade path (not full install.sh): stop the service so the
# concentrator is idle, refresh Python deps, run idempotent post-update
# migrations (sudoers, systemd unit, HAL patch if needed), then restart.
# Typical runtime: about 1-2 minutes. Full install.sh remains for manual
# SSH upgrades when release notes call for it.
set -euo pipefail

MESHPOINT_DIR="${MESHPOINT_DIR:-/opt/meshpoint}"
SERVICE="${MESHPOINT_SERVICE:-meshpoint}"
PIP="${MESHPOINT_DIR}/venv/bin/pip"
REQ="${MESHPOINT_DIR}/requirements.txt"

/usr/bin/systemctl stop "${SERVICE}" || true

if [[ -x "$PIP" && -f "$REQ" ]]; then
    "$PIP" install --upgrade pip -q
    "$PIP" install -r "$REQ" -q
    "$PIP" install pyserial -q
fi

/bin/bash "${MESHPOINT_DIR}/scripts/post_update.sh"
/usr/bin/systemctl restart "${SERVICE}"
