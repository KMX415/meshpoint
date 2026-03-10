#!/usr/bin/env bash
#
# Mesh Point Core Installer
#
# Downloads and installs the compiled proprietary core modules
# required for SX1302 concentrator operation.
#
# Usage:
#   sudo ./scripts/install_core.sh [path-to-tarball]
#
# If a tarball path is provided, it installs from that file.
# Otherwise it attempts to download from GitHub Releases.
#
set -euo pipefail

MESHPOINT_DIR="/opt/meshpoint"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

if [[ $EUID -ne 0 ]]; then
    fail "This script must be run as root."
fi

TARBALL="${1:-}"

if [ -n "$TARBALL" ] && [ -f "$TARBALL" ]; then
    info "Installing core from local file: ${TARBALL}"
else
    # Attempt download from GitHub Releases
    CORE_VERSION_FILE="${MESHPOINT_DIR}/src/version.py"
    if [ -f "$CORE_VERSION_FILE" ]; then
        CORE_VERSION=$(python3 -c "exec(open('${CORE_VERSION_FILE}').read()); print(__version__)")
    else
        fail "Cannot determine version. Provide a tarball path as argument."
    fi

    GITHUB_TOKEN="${MESHPOINT_GITHUB_TOKEN:-}"
    if [ -z "$GITHUB_TOKEN" ]; then
        echo ""
        echo "  The Mesh Point core modules are required for concentrator operation."
        echo "  These are distributed separately from the open-source framework."
        echo ""
        echo "  Options:"
        echo "    1. Provide the tarball path:  sudo ./scripts/install_core.sh /path/to/meshpoint-core.tar.gz"
        echo "    2. Set MESHPOINT_GITHUB_TOKEN for automatic download"
        echo "    3. Contact the device provider for a pre-configured SD card"
        echo ""
        fail "Core tarball not found and no GitHub token available."
    fi

    ARCH=$(uname -m)
    TARBALL="/tmp/meshpoint-core-${CORE_VERSION}-${ARCH}.tar.gz"
    CORE_URL="https://api.github.com/repos/KMX415/Mesh-Radar/releases/tags/core-v${CORE_VERSION}"

    info "Fetching release info for core-v${CORE_VERSION}..."
    ASSET_URL=$(curl -sL \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github.v3+json" \
        "$CORE_URL" \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for asset in data.get('assets', []):
    if '${ARCH}' in asset['name']:
        print(asset['url'])
        break
")

    if [ -z "$ASSET_URL" ]; then
        fail "No core asset found for architecture ${ARCH} in release core-v${CORE_VERSION}"
    fi

    info "Downloading core modules..."
    curl -sL \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/octet-stream" \
        -o "$TARBALL" \
        "$ASSET_URL"
fi

info "Extracting core modules to ${MESHPOINT_DIR}..."
tar -xzf "$TARBALL" -C "$MESHPOINT_DIR"

# Verify extraction
CORE_COUNT=$(find "${MESHPOINT_DIR}/src" -name "*.cpython-*.so" 2>/dev/null | wc -l)
info "Installed ${CORE_COUNT} compiled core modules"

if [ "$CORE_COUNT" -eq 0 ]; then
    fail "No .so files found after extraction. The tarball may be corrupt."
fi

# Check for hal_patch scripts (included in core tarball)
if [ -d "${MESHPOINT_DIR}/hal_patch" ]; then
    info "HAL patch scripts installed"
fi

echo ""
echo "==========================================="
echo "  Mesh Point core installed successfully!"
echo "==========================================="
echo ""
