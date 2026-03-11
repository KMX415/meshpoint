#!/usr/bin/env bash
#
# Mesh Radar -- Mesh Point Installer
#
# Prepares a fresh Raspberry Pi for Mesh Point operation:
#   1. System packages and build tools
#   2. SPI / UART / GPS kernel config
#   3. SX1302 HAL (libloragw) compilation
#   4. Python virtual-env and pip dependencies
#   5. systemd service installation
#
# Usage:
#   sudo ./scripts/install.sh
#
# After completion, reboot then run:  meshpoint setup
#
set -euo pipefail

MESHPOINT_DIR="/opt/meshpoint"
HAL_BUILD_DIR="/opt/sx1302_hal"
BOOT_CONFIG="/boot/firmware/config.txt"
SERVICE_FILE="scripts/meshpoint.service"
WATCHDOG_SERVICE_FILE="scripts/network-watchdog.service"
CLI_SCRIPT="scripts/meshpoint"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── Pre-flight checks ──────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    fail "This script must be run as root.  Use:  sudo ./scripts/install.sh"
fi

if ! grep -qi "raspberry\|raspbian\|debian" /etc/os-release 2>/dev/null; then
    warn "This doesn't look like Raspberry Pi OS. Proceeding anyway."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
info "Source directory: ${SCRIPT_DIR}"

# ── 1. System packages ─────────────────────────────────────────────

info "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

info "Installing build tools and dependencies..."
apt-get install -y -qq \
    build-essential \
    git \
    python3 \
    python3-venv \
    python3-pip \
    libsqlite3-dev \
    i2c-tools

# ── 2. Enable SPI ──────────────────────────────────────────────────

info "Enabling SPI interface..."
raspi-config nonint do_spi 0 2>/dev/null || warn "raspi-config SPI failed (may already be enabled)"

# ── 2b. Enable I2C (needed for SX1302 temperature sensor) ─────────

info "Enabling I2C interface..."
raspi-config nonint do_i2c 0 2>/dev/null || warn "raspi-config I2C failed (may already be enabled)"

# ── 3. Enable UART for GPS ─────────────────────────────────────────

info "Enabling UART hardware..."
raspi-config nonint do_serial_hw 0 2>/dev/null || warn "raspi-config UART failed"

info "Disabling serial console (needed for GPS on /dev/ttyAMA0)..."
raspi-config nonint do_serial_cons 1 2>/dev/null || warn "raspi-config serial console failed"

# Disable Bluetooth on primary UART so GPS gets /dev/ttyAMA0
if [ -f "$BOOT_CONFIG" ]; then
    if ! grep -q "dtoverlay=disable-bt" "$BOOT_CONFIG"; then
        info "Adding dtoverlay=disable-bt to ${BOOT_CONFIG}"
        echo "" >> "$BOOT_CONFIG"
        echo "# Mesh Point: free primary UART for GPS" >> "$BOOT_CONFIG"
        echo "dtoverlay=disable-bt" >> "$BOOT_CONFIG"
    else
        info "dtoverlay=disable-bt already present"
    fi
fi

# ── 4. Build patched SX1302 HAL ────────────────────────────────────

if [ -f "/usr/local/lib/libloragw.so" ]; then
    info "libloragw.so already installed, skipping HAL build"
else
    info "Cloning SX1302 HAL..."
    rm -rf "$HAL_BUILD_DIR"
    git clone --depth 1 https://github.com/Lora-net/sx1302_hal.git "$HAL_BUILD_DIR"

    SYNCWORD_PATCH="${SCRIPT_DIR}/hal_patch/apply_syncword_patch.py"
    SYNCWORD_TARGET="${HAL_BUILD_DIR}/libloragw/src/loragw_sx1302.c"
    if [ -f "$SYNCWORD_PATCH" ]; then
        info "Applying Meshtastic sync word patch..."
        python3 "$SYNCWORD_PATCH" "$SYNCWORD_TARGET" || fail "Could not apply sync word patch"
    else
        warn "Sync word patch script not found at ${SYNCWORD_PATCH}, building without it"
    fi

    TEMPSENSOR_PATCH="${SCRIPT_DIR}/hal_patch/apply_temp_sensor_patch.py"
    TEMPSENSOR_TARGET="${HAL_BUILD_DIR}/libloragw/src/loragw_hal.c"
    if [ -f "$TEMPSENSOR_PATCH" ]; then
        info "Applying optional temperature sensor patch (RAK2287 has no STTS751)..."
        python3 "$TEMPSENSOR_PATCH" "$TEMPSENSOR_TARGET" || fail "Could not apply temp sensor patch"
    else
        warn "Temp sensor patch script not found at ${TEMPSENSOR_PATCH}, building without it"
    fi

    info "Compiling libloragw (this takes a few minutes)..."
    cd "$HAL_BUILD_DIR"
    make clean 2>/dev/null || true
    make -j"$(nproc)"

    info "Recompiling with -fPIC for shared library..."
    mkdir -p pic_obj

    for src in libtools/src/*.c; do
        gcc -c -O2 -fPIC -Wall -Wextra -std=c99 \
            -Ilibtools/inc -Ilibtools \
            "$src" -o "pic_obj/$(basename "${src%.c}.o")"
    done

    for src in libloragw/src/*.c; do
        gcc -c -O2 -fPIC -Wall -Wextra -std=c99 \
            -Ilibloragw/inc -Ilibloragw -Ilibtools/inc \
            "$src" -o "pic_obj/$(basename "${src%.c}.o")"
    done

    info "Linking libloragw.so..."
    gcc -shared -o libloragw/libloragw.so pic_obj/*.o -lrt -lm -lpthread

    info "Installing libloragw.so..."
    cp libloragw/libloragw.so /usr/local/lib/
    ldconfig
    info "libloragw.so installed to /usr/local/lib/"
fi

# ── 5. Install Mesh Point application ──────────────────────────────

info "Installing Mesh Point to ${MESHPOINT_DIR}..."
mkdir -p "$MESHPOINT_DIR"

rsync -a --exclude='venv' \
         --exclude='.git' \
         --exclude='__pycache__' \
         --exclude='cdk.out' \
         --exclude='cloud/build' \
         --exclude='data' \
         --exclude='*.pyc' \
         "${SCRIPT_DIR}/" "$MESHPOINT_DIR/"

# ── 6. Python virtual environment ──────────────────────────────────

info "Setting up Python virtual environment..."
python3 -m venv "${MESHPOINT_DIR}/venv"
source "${MESHPOINT_DIR}/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "${MESHPOINT_DIR}/requirements.txt" -q
pip install pyserial -q
deactivate

# ── 7. Create data directory ───────────────────────────────────────

mkdir -p "${MESHPOINT_DIR}/data"

# ── 8. Create meshpoint system user ────────────────────────────────

if ! id -u meshpoint &>/dev/null; then
    info "Creating system user 'meshpoint'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin meshpoint
fi

# Grant access to SPI, UART, GPIO, and I2C
usermod -a -G spi,gpio,dialout,i2c meshpoint 2>/dev/null || true
chown -R meshpoint:meshpoint "${MESHPOINT_DIR}/data"

# ── 9. Configure journald log rotation ─────────────────────────────

info "Configuring journald log limits (100M, 7-day retention)..."
mkdir -p /etc/systemd/journald.conf.d
cp "${MESHPOINT_DIR}/config/journald-meshpoint.conf" /etc/systemd/journald.conf.d/meshpoint.conf
systemctl restart systemd-journald 2>/dev/null || warn "Could not restart journald"

# ── 10. Install systemd service ────────────────────────────────────

info "Installing systemd service..."
cp "${MESHPOINT_DIR}/${SERVICE_FILE}" /etc/systemd/system/meshpoint.service
systemctl daemon-reload
systemctl enable meshpoint
info "Service enabled (will start after 'meshpoint setup')"

# ── 11. Install network watchdog ───────────────────────────────────

info "Installing WiFi network watchdog..."
cp "${MESHPOINT_DIR}/${WATCHDOG_SERVICE_FILE}" /etc/systemd/system/network-watchdog.service
systemctl daemon-reload
systemctl enable network-watchdog
systemctl start network-watchdog 2>/dev/null || warn "Could not start network-watchdog (will start on next boot)"
info "Network watchdog enabled"

# ── 12. Install CLI tool ───────────────────────────────────────────

info "Installing meshpoint CLI..."
chmod +x "${MESHPOINT_DIR}/${CLI_SCRIPT}"
ln -sf "${MESHPOINT_DIR}/${CLI_SCRIPT}" /usr/local/bin/meshpoint

# ── Done ────────────────────────────────────────────────────────────

echo ""
echo "==========================================="
echo "  Mesh Point installation complete!"
echo "==========================================="
echo ""
echo "  Next steps:"
echo ""
echo "  1. Reboot to apply SPI/UART changes:"
echo "       sudo reboot"
echo ""
echo "  2. After reboot, run the setup wizard:"
echo "       meshpoint setup"
echo ""
echo "  3. The wizard will walk you through:"
echo "       - Hardware detection"
echo "       - API key configuration"
echo "       - Device naming and GPS"
echo "       - Starting the service"
echo ""
echo "==========================================="
