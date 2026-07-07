#!/bin/bash
# Finish a dashboard-driven backup restore after the API validates the archive.
#
# Stops meshpoint, stashes the current config + data tree, extracts the backup,
# fixes ownership, and restarts the service. Invoked detached from the API so the
# HTTP response can return before systemctl stop kills this process tree.
set -euo pipefail

ARCHIVE_PATH="${1:-}"
MESHPOINT_DIR="${MESHPOINT_DIR:-/opt/meshpoint}"
SERVICE="${MESHPOINT_SERVICE:-meshpoint}"
CONFIG_PATH="${CONCENTRATOR_CONFIG:-${MESHPOINT_DIR}/config/local.yaml}"

log() {
    echo "[restore_finish] $*"
    logger -t meshpoint-restore-finish "$*" 2>/dev/null || true
}

# restore-incoming holds the upload; stash dirs are recovery copies.
_should_skip_data_entry() {
    case "$1" in
        restore-incoming|backup-staging|pre-restore-stash-*)
            return 0
            ;;
    esac
    return 1
}

_clear_live_data_tree() {
    if [[ ! -d "${MESHPOINT_DIR}/data" ]]; then
        return 0
    fi
    for entry in "${MESHPOINT_DIR}/data"/*; do
        [[ -e "$entry" ]] || continue
        base="$(basename "$entry")"
        if _should_skip_data_entry "$base"; then
            continue
        fi
        rm -rf "$entry"
    done
}

if [[ -z "$ARCHIVE_PATH" || ! -f "$ARCHIVE_PATH" ]]; then
    log "missing archive path"
    exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STASH_DIR="${MESHPOINT_DIR}/data/pre-restore-stash-${STAMP}"
EXTRACT_DIR="$(mktemp -d /tmp/meshpoint-restore-extract.XXXXXX)"

cleanup() {
    rm -rf "$EXTRACT_DIR"
}
trap cleanup EXIT

_on_error() {
    log "failed near line ${1:-?}; attempting ${SERVICE} restart"
    /usr/bin/systemctl start "${SERVICE}" || true
}
trap '_on_error ${LINENO}' ERR

log "Stopping ${SERVICE}"
/usr/bin/systemctl stop "${SERVICE}" || true

log "Stashing current state to ${STASH_DIR}"
mkdir -p "${STASH_DIR}/config" "${STASH_DIR}/data"
if [[ -f "${CONFIG_PATH}" ]]; then
    cp -a "${CONFIG_PATH}" "${STASH_DIR}/config/local.yaml"
fi
if [[ -d "${MESHPOINT_DIR}/data" ]]; then
    for entry in "${MESHPOINT_DIR}/data"/*; do
        base="$(basename "$entry")"
        if _should_skip_data_entry "$base"; then
            continue
        fi
        cp -a "$entry" "${STASH_DIR}/data/"
    done
fi

log "Extracting ${ARCHIVE_PATH}"
tar -xzf "${ARCHIVE_PATH}" -C "${EXTRACT_DIR}"
BUNDLE_DIR="$(find "${EXTRACT_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$BUNDLE_DIR" || ! -f "${BUNDLE_DIR}/manifest.json" ]]; then
    log "archive layout invalid; restarting ${SERVICE}"
    /usr/bin/systemctl start "${SERVICE}" || true
    exit 1
fi

log "Applying backup from ${BUNDLE_DIR}"
mkdir -p "${MESHPOINT_DIR}/config" "${MESHPOINT_DIR}/data"
if [[ -f "${BUNDLE_DIR}/config/local.yaml" ]]; then
    cp -a "${BUNDLE_DIR}/config/local.yaml" "${CONFIG_PATH}"
fi
log "Clearing live data tree before restore"
_clear_live_data_tree
if [[ -d "${BUNDLE_DIR}/data" ]]; then
    for entry in "${BUNDLE_DIR}/data"/*; do
        [[ -e "$entry" ]] || continue
        base="$(basename "$entry")"
        cp -a "$entry" "${MESHPOINT_DIR}/data/${base}"
        if [[ "$base" == *.db ]]; then
            rm -f "${MESHPOINT_DIR}/data/${base}-wal" \
                "${MESHPOINT_DIR}/data/${base}-shm" \
                "${MESHPOINT_DIR}/data/${base}-journal"
        fi
    done
fi

if [[ -f "${MESHPOINT_DIR}/data/keys.yaml" ]]; then
    chmod 600 "${MESHPOINT_DIR}/data/keys.yaml"
fi

/bin/chown -R meshpoint:meshpoint "${MESHPOINT_DIR}/config" "${MESHPOINT_DIR}/data"

log "Starting ${SERVICE}"
/usr/bin/systemctl start "${SERVICE}"
trap - ERR
log "Done; stash at ${STASH_DIR}"
