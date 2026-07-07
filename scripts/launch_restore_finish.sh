#!/bin/bash
# Launch restore_finish outside the meshpoint service cgroup.
#
# restore_finish must call systemctl stop meshpoint. If this script were
# spawned directly from the API handler, stop would kill the unit cgroup
# and terminate restore_finish before it can extract the archive and start
# the service again. systemd-run starts a transient unit that outlives stop.
set -euo pipefail

ARCHIVE_PATH="${1:-}"
if [[ -z "$ARCHIVE_PATH" || ! -f "$ARCHIVE_PATH" ]]; then
    echo "usage: launch_restore_finish.sh <archive.tar.gz>" >&2
    exit 1
fi

exec /usr/bin/systemd-run \
    --unit=meshpoint-restore-finish \
    --description="Meshpoint backup restore" \
    --remain-after-exit \
    /bin/bash /opt/meshpoint/scripts/restore_finish.sh "$ARCHIVE_PATH"
