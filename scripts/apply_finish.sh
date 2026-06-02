#!/bin/bash
# Finish a dashboard-driven apply or rollback after git checkout/reset.
#
# Lightweight upgrade path (not full install.sh): refresh Python deps,
# run idempotent post-update migrations (sudoers, systemd unit, HAL patch
# if needed), then restart the service. Typical runtime: about 1-2 minutes.
# Full install.sh remains for manual SSH upgrades when release notes call
# for it.
set -euo pipefail

MESHPOINT_DIR="${MESHPOINT_DIR:-/opt/meshpoint}"
SERVICE="${MESHPOINT_SERVICE:-meshpoint}"
PIP="${MESHPOINT_DIR}/venv/bin/pip"
REQ="${MESHPOINT_DIR}/requirements.txt"

log() {
    echo "[apply_finish] $*"
    logger -t meshpoint-apply-finish "$*" 2>/dev/null || true
}

_on_error() {
    log "failed near line ${1:-?}; attempting ${SERVICE} restart"
    /usr/bin/systemctl restart "${SERVICE}" || true
}
trap '_on_error ${LINENO}' ERR

# Do NOT systemctl stop here. This script is spawned from the meshpoint
# service process; stop kills the unit cgroup and terminates us before
# pip or restart can finish. Restart at the end stops the concentrator.

if [[ -x "$PIP" && -f "$REQ" ]]; then
    log "Refreshing Python dependencies"
    "$PIP" install --upgrade pip -q
    "$PIP" install -r "$REQ" -q
    "$PIP" install pyserial -q
fi

log "Running post_update migrations"
/bin/bash "${MESHPOINT_DIR}/scripts/post_update.sh"

log "Restarting ${SERVICE}"
/usr/bin/systemctl restart "${SERVICE}"
trap - ERR
log "Done"
