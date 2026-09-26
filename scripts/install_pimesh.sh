#!/usr/bin/env bash
# Called by install.sh after common Meshpoint dependencies and user creation.
set -euo pipefail
ROOT=/opt/meshpoint
if [[ -f /etc/meshpoint/pimesh.json ]]; then
    read -r SAVED_BOARD SAVED_BAND SAVED_REGION < <("$ROOT/venv/bin/python" -c 'import json; d=json.load(open("/etc/meshpoint/pimesh.json")); print(d["board"],d["band"],d["region"])')
    PIMESH_BOARD=${PIMESH_BOARD:-$SAVED_BOARD}
    PIMESH_BAND=${PIMESH_BAND:-$SAVED_BAND}
    PIMESH_REGION=${PIMESH_REGION:-$SAVED_REGION}
fi
BOARD=${PIMESH_BOARD:?Select pimesh-v1 or pimesh-v2}
BAND=${PIMESH_BAND:?Select 868 or 915}
REGION=${PIMESH_REGION:?Select the deployment region}
PROTOCOL=${PIMESH_PROTOCOL:-meshtastic}
OPENHOP_REV=13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b
[[ $BOARD == pimesh-v1 || $BOARD == pimesh-v2 ]]
[[ $BAND == 868 || $BAND == 915 ]]
[[ $PROTOCOL == meshtastic || $PROTOCOL == meshcore ]]
[[ $REGION == US || $REGION == EU_868 || $REGION == ANZ ]]
if [[ $REGION == EU_868 ]]; then [[ $BAND == 868 ]]; else [[ $BAND == 915 ]]; fi
if [[ -f /etc/meshpoint/pimesh.json ]]; then
    if [[ $BOARD != "$SAVED_BOARD" || $BAND != "$SAVED_BAND" || $REGION != "$SAVED_REGION" ]]; then
        echo 'Existing PiMesh hardware/region differs. Restore the saved installation options.' >&2
        exit 1
    fi
    systemctl stop meshpoint meshpoint-openhop meshtasticd
fi
BOOT=/boot/firmware/config.txt
[[ -f $BOOT ]] || BOOT=/boot/config.txt
[[ -f $BOOT ]]
grep -qxF 'dtparam=spi=on' "$BOOT" || printf '\n[all]\ndtparam=spi=on\n' >> "$BOOT"
if [[ $BOARD == pimesh-v2 ]]; then
    grep -qxF 'gpio=26=op,dh' "$BOOT" || printf '\n[all]\ngpio=26=op,dh\n' >> "$BOOT"
fi

# Install the Linux Meshtastic daemon without applying the RAK overlay/profile.
if ! command -v meshtasticd >/dev/null; then
    . /etc/os-release
    case "$VERSION_ID" in 12|13) ;; *) echo 'PiMesh requires Debian 12 or 13'; exit 1;; esac
    install -d /etc/apt/keyrings
    curl -fsSL "https://download.opensuse.org/repositories/network:/Meshtastic:/beta/Debian_${VERSION_ID}/Release.key" \
        | gpg --dearmor --yes -o /etc/apt/keyrings/meshtastic.gpg
    echo "deb [signed-by=/etc/apt/keyrings/meshtastic.gpg] https://download.opensuse.org/repositories/network:/Meshtastic:/beta/Debian_${VERSION_ID}/ /" \
        > /etc/apt/sources.list.d/meshtastic.list
    apt-get update -qq
    apt-get install -y meshtasticd
fi
systemctl stop meshtasticd
systemctl disable meshtasticd
install -d /etc/meshtasticd/meshpoint.d /etc/meshpoint /var/lib/meshpoint-radio
PRESET="lora-${BOARD/pimesh-/pimesh-1w-}.yaml"
install -m 644 "$ROOT/config/meshtasticd/$PRESET" /etc/meshtasticd/meshpoint.d/radio.yaml
if [[ ! -f /etc/meshpoint/pimesh.json ]]; then
    [[ ! -f /etc/meshtasticd/config.yaml ]] || cp -n /etc/meshtasticd/config.yaml /etc/meshtasticd/config.yaml.pre-meshpoint
    cat > /etc/meshtasticd/config.yaml <<'YAML'
General:
  MACAddressSource: eth0
  ConfigDirectory: /etc/meshtasticd/meshpoint.d/
Lora:
  Module: auto
YAML
fi

# Dedicated venv/user keeps openHop dependencies and identities separate.
apt-get install -y python3-dev libgpiod-dev libyaml-dev build-essential
id meshpoint-radio >/dev/null 2>&1 || useradd --system --home /var/lib/meshpoint-openhop --shell /usr/sbin/nologin meshpoint-radio
usermod -a -G spi,gpio,dialout meshpoint-radio
if [[ ! -d /opt/meshpoint-openhop/.git ]]; then
    git clone https://github.com/openhop-dev/openhop_repeater.git /opt/meshpoint-openhop
fi
git -C /opt/meshpoint-openhop fetch origin "$OPENHOP_REV"
git -C /opt/meshpoint-openhop checkout --detach "$OPENHOP_REV"
python3 "$ROOT/scripts/patch_openhop.py" /opt/meshpoint-openhop/repeater/config_manager.py
[[ -x /opt/meshpoint-openhop/venv/bin/python ]] || python3 -m venv /opt/meshpoint-openhop/venv
/opt/meshpoint-openhop/venv/bin/pip install /opt/meshpoint-openhop
install -d -o meshpoint-radio -g meshpoint-radio /var/lib/meshpoint-openhop /etc/meshpoint-openhop
"$ROOT/venv/bin/python" "$ROOT/scripts/provision_pimesh.py" "$BOARD" "$BAND" "$REGION" "$PROTOCOL" "$OPENHOP_REV"
chown -R meshpoint-radio:meshpoint-radio /etc/meshpoint-openhop /var/lib/meshpoint-openhop
chmod 700 /etc/meshpoint-openhop
chmod 600 /etc/meshpoint-openhop/config.yaml

install -d /usr/local/libexec /etc/systemd/system/meshtasticd.service.d
install -o root -g root -m 755 "$ROOT/src/radio/pimesh_supervisor.py" /usr/local/libexec/meshpoint-radio
cat > /etc/systemd/system/meshtasticd.service.d/meshpoint.conf <<'UNIT'
[Unit]
Conflicts=meshpoint-openhop.service
[Service]
IPAddressDeny=any
IPAddressAllow=localhost
UNIT
cat > /etc/systemd/system/meshpoint-openhop.service <<'UNIT'
[Unit]
Description=Meshpoint PiMesh MeshCore backend
After=network-online.target
Conflicts=meshtasticd.service
[Service]
User=meshpoint-radio
Group=meshpoint-radio
WorkingDirectory=/var/lib/meshpoint-openhop
ExecStart=/opt/meshpoint-openhop/venv/bin/python -m repeater.main --config /etc/meshpoint-openhop/config.yaml
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/meshpoint-radio-boot.service <<'UNIT'
[Unit]
Description=Restore selected PiMesh protocol
After=network-online.target
Before=meshpoint.service
[Service]
Type=oneshot
ExecStart=/usr/local/libexec/meshpoint-radio boot
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/sudoers.d/meshpoint-pimesh <<'SUDO'
meshpoint ALL=(root) NOPASSWD: /usr/local/libexec/meshpoint-radio request meshtastic, /usr/local/libexec/meshpoint-radio request meshcore
SUDO
chmod 440 /etc/sudoers.d/meshpoint-pimesh
visudo -cf /etc/sudoers.d/meshpoint-pimesh
systemctl daemon-reload
systemctl enable meshpoint-radio-boot
if [[ -e /dev/spidev0.0 ]]; then
    /usr/local/libexec/meshpoint-radio boot
fi
echo 'PiMesh backends installed. Reboot once for SPI, then complete meshpoint setup.'
