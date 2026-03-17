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

# ── 2b. Enable I2C ────────────────────────────────────────────────

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

# ── 4. Build SX1302 HAL ───────────────────────────────────────────

if [ -f "/usr/local/lib/libloragw.so" ]; then
    info "libloragw.so already installed, skipping HAL build"
else
    info "Cloning SX1302 HAL..."
    rm -rf "$HAL_BUILD_DIR"
    git clone --depth 1 https://github.com/Lora-net/sx1302_hal.git "$HAL_BUILD_DIR"

    info "Configuring HAL source..."
    python3 - "${HAL_BUILD_DIR}/libloragw/src/loragw_sx1302.c" \
              "${HAL_BUILD_DIR}/libloragw/src/loragw_hal.c" <<'_HALCFG'
import sys
from pathlib import Path

def _rd(p):
    f = Path(p)
    if not f.is_file():
        print("FAIL: " + p); sys.exit(1)
    return f, f.read_text().replace("\r\n", "\n")

f1, s1 = _rd(sys.argv[1])
f2, s2 = _rd(sys.argv[2])

_A = """\
    int err = LGW_REG_SUCCESS;

    /* Multi-SF modem configuration */
    DEBUG_MSG("INFO: configuring LoRa (Multi-SF) SF5->SF6 with syncword PRIVATE (0x12)\\n");
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF5_PEAK1_POS_SF5, 2);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF5_PEAK2_POS_SF5, 4);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF6_PEAK1_POS_SF6, 2);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF6_PEAK2_POS_SF6, 4);
    if (public == true) {
        DEBUG_MSG("INFO: configuring LoRa (Multi-SF) SF7->SF12 with syncword PUBLIC (0x34)\\n");
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF7TO12_PEAK1_POS_SF7TO12, 6);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF7TO12_PEAK2_POS_SF7TO12, 8);
    } else {
        DEBUG_MSG("INFO: configuring LoRa (Multi-SF) SF7->SF12 with syncword PRIVATE (0x12)\\n");
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF7TO12_PEAK1_POS_SF7TO12, 2);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF7TO12_PEAK2_POS_SF7TO12, 4);
    }

    /* LoRa Service modem configuration */
    if ((public == false) || (lora_service_sf == DR_LORA_SF5) || (lora_service_sf == DR_LORA_SF6)) {
        DEBUG_PRINTF("INFO: configuring LoRa (Service) SF%u with syncword PRIVATE (0x12)\\n", lora_service_sf);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH0_PEAK1_POS, 2);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH1_PEAK2_POS, 4);
    } else {
        DEBUG_PRINTF("INFO: configuring LoRa (Service) SF%u with syncword PUBLIC (0x34)\\n", lora_service_sf);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH0_PEAK1_POS, 6);
        err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH1_PEAK2_POS, 8);
    }

    return err;"""

_B = """\
    int err = LGW_REG_SUCCESS;

    uint8_t sw_reg1, sw_reg2;
    if (public == true) {
        sw_reg1 = 6;
        sw_reg2 = 8;
    } else if (lora_service_sf > 12) {
        sw_reg1 = ((lora_service_sf >> 4) & 0x0F) * 2;
        sw_reg2 = (lora_service_sf & 0x0F) * 2;
        DEBUG_PRINTF("INFO: sync cfg 0x%02X -> %u, %u\\n", lora_service_sf, sw_reg1, sw_reg2);
    } else {
        sw_reg1 = 2;
        sw_reg2 = 4;
    }

    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF5_PEAK1_POS_SF5, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF5_PEAK2_POS_SF5, sw_reg2);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF6_PEAK1_POS_SF6, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF6_PEAK2_POS_SF6, sw_reg2);

    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH0_SF7TO12_PEAK1_POS_SF7TO12, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_FRAME_SYNCH1_SF7TO12_PEAK2_POS_SF7TO12, sw_reg2);

    err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH0_PEAK1_POS, sw_reg1);
    err |= lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FRAME_SYNCH1_PEAK2_POS, sw_reg2);

    return err;"""

if "sw_reg1" in s1:
    pass
elif _A in s1:
    s1 = s1.replace(_A, _B, 1)
    f1.write_text(s1, newline="\n")
else:
    print("FAIL: source mismatch in " + str(f1)); sys.exit(1)

_C = [
("""\
        /* Find the temperature sensor on the known supported ports */
        for (i = 0; i < (int)(sizeof I2C_PORT_TEMP_SENSOR); i++) {
            ts_addr = I2C_PORT_TEMP_SENSOR[i];
            err = i2c_linuxdev_open(I2C_DEVICE, ts_addr, &ts_fd);
            if (err != LGW_I2C_SUCCESS) {
                printf("ERROR: failed to open I2C for temperature sensor on port 0x%02X\\n", ts_addr);
                return LGW_HAL_ERROR;
            }

            err = stts751_configure(ts_fd, ts_addr);
            if (err != LGW_I2C_SUCCESS) {
                printf("INFO: no temperature sensor found on port 0x%02X\\n", ts_addr);
                i2c_linuxdev_close(ts_fd);
                ts_fd = -1;
            } else {
                printf("INFO: found temperature sensor on port 0x%02X\\n", ts_addr);
                break;
            }
        }
        if (i == sizeof I2C_PORT_TEMP_SENSOR) {
            printf("ERROR: no temperature sensor found.\\n");
            return LGW_HAL_ERROR;
        }""",
"""\
        /* Find the temperature sensor on the known supported ports */
        for (i = 0; i < (int)(sizeof I2C_PORT_TEMP_SENSOR); i++) {
            ts_addr = I2C_PORT_TEMP_SENSOR[i];
            err = i2c_linuxdev_open(I2C_DEVICE, ts_addr, &ts_fd);
            if (err != LGW_I2C_SUCCESS) {
                printf("WARNING: could not open I2C on port 0x%02X\\n", ts_addr);
                ts_fd = -1;
                continue;
            }

            err = stts751_configure(ts_fd, ts_addr);
            if (err != LGW_I2C_SUCCESS) {
                printf("INFO: no temperature sensor found on port 0x%02X\\n", ts_addr);
                i2c_linuxdev_close(ts_fd);
                ts_fd = -1;
            } else {
                printf("INFO: found temperature sensor on port 0x%02X\\n", ts_addr);
                break;
            }
        }
        if (ts_fd < 0) {
            printf("WARNING: sensor not available, using default\\n");
        }"""),
("""\
        case LGW_COM_SPI:
            err = stts751_get_temperature(ts_fd, ts_addr, temperature);
            break;""",
"""\
        case LGW_COM_SPI:
            if (ts_fd > 0) {
                err = stts751_get_temperature(ts_fd, ts_addr, temperature);
            } else {
                *temperature = 25.0;
                err = LGW_HAL_SUCCESS;
            }
            break;"""),
("""\
        DEBUG_MSG("INFO: Closing I2C for temperature sensor\\n");
        x = i2c_linuxdev_close(ts_fd);
        if (x != 0) {
            printf("ERROR: failed to close I2C temperature sensor device (err=%i)\\n", x);
            err = LGW_HAL_ERROR;
        }""",
"""\
        if (ts_fd > 0) {
            DEBUG_MSG("INFO: Closing I2C for temperature sensor\\n");
            x = i2c_linuxdev_close(ts_fd);
            if (x != 0) {
                printf("ERROR: failed to close I2C temperature sensor device (err=%i)\\n", x);
                err = LGW_HAL_ERROR;
            }
        }"""),
]

ok = True
for o, n in _C:
    if n in s2:
        continue
    if o not in s2:
        ok = False; break
    s2 = s2.replace(o, n, 1)
if ok:
    f2.write_text(s2, newline="\n")
else:
    print("FAIL: source mismatch in " + str(f2)); sys.exit(1)
_HALCFG

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

info "Installing Meshpoint to ${MESHPOINT_DIR}..."
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
echo "       sudo meshpoint setup"
echo ""
echo "  3. The wizard will walk you through:"
echo "       - Hardware detection"
echo "       - API key configuration"
echo "       - Device naming and GPS"
echo "       - Starting the service"
echo ""
echo "  IMPORTANT: Never yank the power cable"
echo "  without shutting down first. Always run:"
echo "       sudo poweroff"
echo "  and wait for the LED to go dark."
echo ""
echo "==========================================="
