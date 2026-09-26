#!/usr/bin/env bash
#
# Install and configure meshtasticd for WisMesh Node platforms.
# Called from scripts/install.sh when --platform node (or auto-detect).
#
set -euo pipefail

MESHTASTICD_CONFIG="/etc/meshtasticd/config.yaml"
MESHTASTICD_CONFIGD="/etc/meshtasticd/config.d"
MAC_SOURCE="${MESHTASTICD_MAC_SOURCE:-eth0}"
PRESET="${MESHTASTICD_PRESET:-lora-RAK6421-13302-slot1.yaml}"

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }

_detect_debian_repo() {
    local version_id=""
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        version_id="${VERSION_ID:-}"
    fi
    case "${version_id}" in
        13|13.*|trixie) echo "Debian_13" ;;
        12|12.*|bookworm) echo "Debian_12" ;;
        11|11.*|bullseye) echo "Debian_11" ;;
        *) echo "Debian_12" ;;
    esac
}

install_meshtasticd_package() {
    if command -v meshtasticd &>/dev/null; then
        info "meshtasticd already installed: $(meshtasticd --version 2>/dev/null || true)"
        return
    fi

    local repo="$(_detect_debian_repo)"
    info "Installing meshtasticd from OBS repo ${repo}..."

    echo "deb http://download.opensuse.org/repositories/network:/Meshtastic:/beta/${repo}/ /" \
        > /etc/apt/sources.list.d/network:Meshtastic:beta.list

    curl -fsSL \
        "https://download.opensuse.org/repositories/network:Meshtastic:beta/${repo}/Release.key" \
        | gpg --dearmor \
        > /etc/apt/trusted.gpg.d/network_Meshtastic_beta.gpg

    apt-get update -qq
    apt-get install -y -qq meshtasticd
}

write_meshtasticd_config() {
    info "Writing ${MESHTASTICD_CONFIG} (MACAddressSource=${MAC_SOURCE})..."
    mkdir -p /etc/meshtasticd
    # ConfigDirectory is required or config.d/*.yaml presets are ignored and
    # meshtasticd falls back to SimRadio (no real RF, no RSSI).
    cat > "${MESHTASTICD_CONFIG}" <<EOF
General:
  MACAddressSource: ${MAC_SOURCE}
  MaxNodes: 200
  MaxMessageQueue: 100
  ConfigDirectory: /etc/meshtasticd/config.d/
  AvailableDirectory: /etc/meshtasticd/available.d/

---
Lora:
  Module: auto
EOF
}

install_lora_preset() {
    mkdir -p "${MESHTASTICD_CONFIGD}"
    local available="/etc/meshtasticd/available.d/${PRESET}"
    local target="${MESHTASTICD_CONFIGD}/${PRESET}"
    local repo_root
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    local bundled="${repo_root}/config/meshtasticd/${PRESET}"

    # Only one RAK6421 slot profile should be active in config.d.
    find "${MESHTASTICD_CONFIGD}" -maxdepth 1 -type f -name 'lora-RAK6421-*.yaml' \
        ! -name "${PRESET}" -delete 2>/dev/null || true

    local source=""
    if [ -f "${available}" ]; then
        source="${available}"
    elif [ -f "${bundled}" ]; then
        source="${bundled}"
        info "Using bundled Meshpoint preset (meshtasticd package lacks ${PRESET})"
    else
        warn "Preset not found: ${PRESET}"
        warn "Check /etc/meshtasticd/available.d/ or config/meshtasticd/ in the repo."
        return
    fi

    cp "${source}" "${target}"
    # With dtoverlay=spi0-0cs the preset still needs an explicit CS pin on Pi 4/5.
    if grep -q '^[[:space:]]*#[[:space:]]*CS:' "${target}"; then
        sed -i 's/^[[:space:]]*#[[:space:]]*CS:/  CS:/' "${target}"
    fi
    chown meshtasticd:meshtasticd "${target}" 2>/dev/null || true
    info "Installed LoRa preset: ${PRESET}"
}

enable_spi_overlay() {
    local boot_cfg="/boot/firmware/config.txt"
    [ -f "${boot_cfg}" ] || boot_cfg="/boot/config.txt"
    if [ ! -f "${boot_cfg}" ]; then
        warn "Could not find boot config for SPI overlay"
        return
    fi
    if ! grep -q '^[[:space:]]*dtparam=spi=on' "${boot_cfg}"; then
        echo "dtparam=spi=on" >> "${boot_cfg}"
        info "Added dtparam=spi=on to ${boot_cfg} (reboot required)"
    fi
    if ! grep -q '^[[:space:]]*dtoverlay=spi0-0cs' "${boot_cfg}"; then
        sed -i '/dtparam=spi=on/a dtoverlay=spi0-0cs' "${boot_cfg}"
        info "Added dtoverlay=spi0-0cs to ${boot_cfg} (reboot required)"
    fi
}

enable_meshtasticd_service() {
    systemctl daemon-reload
    systemctl enable meshtasticd
    systemctl restart meshtasticd 2>/dev/null || systemctl start meshtasticd
    info "meshtasticd service enabled and started"
}

install_meshtasticd_package
enable_spi_overlay
write_meshtasticd_config
install_lora_preset
enable_meshtasticd_service
