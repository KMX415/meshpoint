#!/usr/bin/env bash
#
# Install and configure meshtasticd for WisMesh Node platforms.
# Called from scripts/install.sh when --platform node (or auto-detect).
#
set -euo pipefail

MESHTASTICD_CONFIG="/etc/meshtasticd/config.yaml"
MESHTASTICD_CONFIGD="/etc/meshtasticd/config.d"
MAC_SOURCE="${MESHTASTICD_MAC_SOURCE:-eth0}"
PRESET="${MESHTASTICD_PRESET:-lora-RAK6421-13300-slot1.yaml}"

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
    cat > "${MESHTASTICD_CONFIG}" <<EOF
General:
  MACAddressSource: ${MAC_SOURCE}
EOF
}

install_lora_preset() {
    mkdir -p "${MESHTASTICD_CONFIGD}"
    local available="/etc/meshtasticd/available.d/${PRESET}"
    local target="${MESHTASTICD_CONFIGD}/${PRESET}"

    if [ -f "${target}" ]; then
        info "LoRa preset already installed: ${PRESET}"
        return
    fi

    if [ ! -f "${available}" ]; then
        warn "Preset not found in available.d: ${PRESET}"
        warn "List /etc/meshtasticd/available.d/ and copy the right RAK6421 yaml manually."
        return
    fi

    cp "${available}" "${target}"
    info "Installed LoRa preset: ${PRESET}"
}

enable_meshtasticd_service() {
    systemctl daemon-reload
    systemctl enable meshtasticd
    systemctl restart meshtasticd 2>/dev/null || systemctl start meshtasticd
    info "meshtasticd service enabled and started"
}

install_meshtasticd_package
write_meshtasticd_config
install_lora_preset
enable_meshtasticd_service
