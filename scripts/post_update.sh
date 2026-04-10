#!/bin/bash
# Post-update migration hook: runs after git pull, before restart.
# All checks are idempotent: safe to run on every update.
set -e

MESHPOINT_DIR="/opt/meshpoint"
HAL_SRC="/opt/sx1302_hal/libloragw/src/loragw_sx1302.c"

info() { echo "[post_update] $*"; }

CHANGED=0

# ── 1. Sudoers rule ─────────────────────────────────────────────────
SUDOERS_SRC="${MESHPOINT_DIR}/config/sudoers-meshpoint"
SUDOERS_DST="/etc/sudoers.d/meshpoint"
if [ -f "$SUDOERS_SRC" ]; then
    if ! diff -q "$SUDOERS_SRC" "$SUDOERS_DST" >/dev/null 2>&1; then
        info "Updating sudoers rule..."
        cp "$SUDOERS_SRC" "$SUDOERS_DST"
        chmod 440 "$SUDOERS_DST"
        CHANGED=1
    fi
fi

# ── 2. Service file ─────────────────────────────────────────────────
SERVICE_SRC="${MESHPOINT_DIR}/scripts/meshpoint.service"
SERVICE_DST="/etc/systemd/system/meshpoint.service"
if [ -f "$SERVICE_SRC" ]; then
    if ! diff -q "$SERVICE_SRC" "$SERVICE_DST" >/dev/null 2>&1; then
        info "Updating service file..."
        cp "$SERVICE_SRC" "$SERVICE_DST"
        systemctl daemon-reload
        CHANGED=1
    fi
fi

# ── 3. Config directory permissions ─────────────────────────────────
chown -R meshpoint:meshpoint "${MESHPOINT_DIR}/config" 2>/dev/null || true

# ── 4. HAL TX sync word patch (one-time, ~2 minutes if needed) ──────
if [ -f "$HAL_SRC" ]; then
    if ! grep -q "PEAK1_POS.*sx1302_tx_sw_peak1" "$HAL_SRC"; then
        info "TX sync word patch needed (this takes ~2 minutes)..."
        bash "${MESHPOINT_DIR}/scripts/patch_hal.sh"
        CHANGED=1
    fi
fi

if [ "$CHANGED" -eq 0 ]; then
    info "No migrations needed"
else
    info "Migrations applied"
fi
