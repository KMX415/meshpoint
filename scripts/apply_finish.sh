#!/bin/bash
# Finish a dashboard-driven apply after git checkout and pip install.
#
# Runs detached from the Meshpoint process so we can stop the service
# (releasing the concentrator) before install.sh without killing the
# apply chain before git and pip complete.
set -euo pipefail

MESHPOINT_DIR="${MESHPOINT_DIR:-/opt/meshpoint}"
SERVICE="${MESHPOINT_SERVICE:-meshpoint}"

/usr/bin/systemctl stop "${SERVICE}" || true
/bin/bash "${MESHPOINT_DIR}/scripts/install.sh"
/usr/bin/systemctl restart "${SERVICE}"
