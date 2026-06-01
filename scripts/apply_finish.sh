#!/bin/bash
# Finish a dashboard-driven apply or rollback after git checkout/reset.
#
# Stops meshpoint, runs the full idempotent installer, then restarts.
# Detached so the stop does not kill the in-process applier mid-stream.
set -euo pipefail

MESHPOINT_DIR="${MESHPOINT_DIR:-/opt/meshpoint}"
SERVICE="${MESHPOINT_SERVICE:-meshpoint}"

/usr/bin/systemctl stop "${SERVICE}" || true
/bin/bash "${MESHPOINT_DIR}/scripts/install.sh"
/usr/bin/systemctl restart "${SERVICE}"
