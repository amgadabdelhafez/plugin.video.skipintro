#!/bin/bash
set -e

ADDON_SRC="/addon"
ADDON_DST="${KODI_DATA}/addons/plugin.video.skipintro"
KODI_USERDATA="${KODI_DATA}/userdata"
CONFIG_SRC="/addon/test-container/kodi-config"

# Sync addon files into Kodi's addon directory
if [ -d "$ADDON_SRC" ]; then
    echo "==> Syncing addon from $ADDON_SRC to $ADDON_DST"
    cp -r "$ADDON_SRC"/addon.xml "$ADDON_DST"/
    cp -r "$ADDON_SRC"/default.py "$ADDON_DST"/
    cp -r "$ADDON_SRC"/context.py "$ADDON_DST"/
    cp -r "$ADDON_SRC"/resources "$ADDON_DST"/
    # Copy optional files if they exist
    for f in database_tools.py browse_path.py; do
        [ -f "$ADDON_SRC/$f" ] && cp "$ADDON_SRC/$f" "$ADDON_DST"/
    done
    echo "==> Addon files synced"
else
    echo "ERROR: No addon mounted at $ADDON_SRC"
    exit 1
fi

# Copy Kodi configuration
if [ -d "$CONFIG_SRC" ]; then
    echo "==> Applying Kodi configuration"
    cp -f "$CONFIG_SRC"/advancedsettings.xml "$KODI_USERDATA"/ 2>/dev/null || true
    cp -f "$CONFIG_SRC"/sources.xml "$KODI_USERDATA"/ 2>/dev/null || true
    cp -f "$CONFIG_SRC"/guisettings.xml "$KODI_USERDATA"/ 2>/dev/null || true
    cp -f "$CONFIG_SRC"/passwords.xml "$KODI_USERDATA"/ 2>/dev/null || true
    echo "==> Configuration applied"
fi

# Show environment info
echo ""
echo "==> Environment"
echo "    Arch: $(uname -m)"
echo "    Python: $(python3 --version)"
echo "    ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
echo "    Kodi data: ${KODI_DATA}"
echo ""

# If first arg is "test", run unit tests
if [ "${1}" = "test" ]; then
    echo "==> Running addon tests"
    cd "$ADDON_SRC"
    python3 test_video_metadata.py -v 2>&1
    exit $?
fi

# If first arg is "e2e", start Kodi and run JSON-RPC E2E tests
if [ "${1}" = "e2e" ]; then
    echo "==> Starting Xvfb on :99 for E2E"
    rm -f /tmp/.X99-lock
    Xvfb :99 -screen 0 1280x720x24 &
    XVFB_PID=$!
    sleep 1

    KODI_BIN=$(find /usr/lib -name "kodi.bin" -type f 2>/dev/null | head -1)
    if [ -z "$KODI_BIN" ]; then
        echo "ERROR: kodi.bin not found"
        kill "$XVFB_PID" 2>/dev/null || true
        exit 1
    fi

    echo "==> Starting Kodi for E2E ($KODI_BIN)"
    "$KODI_BIN" --standalone --debug &
    KODI_PID=$!

    cleanup() {
        kill "$KODI_PID" 2>/dev/null || true
        kill "$XVFB_PID" 2>/dev/null || true
    }
    trap cleanup EXIT

    cd "$ADDON_SRC"
    python3 test-container/e2e_kodi.py -v
    exit $?
fi

# If first arg is "shell", drop to bash
if [ "${1}" = "shell" ]; then
    exec /bin/bash
fi

# Default: start Kodi with Xvfb (virtual framebuffer)
echo "==> Starting Xvfb on :99"
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1280x720x24 &
sleep 1

# Find the Kodi binary — path varies by architecture
KODI_BIN=$(find /usr/lib -name "kodi.bin" -type f 2>/dev/null | head -1)
if [ -z "$KODI_BIN" ]; then
    echo "ERROR: kodi.bin not found"
    exit 1
fi

echo "==> Starting Kodi ($KODI_BIN)"
echo "    Web interface: http://localhost:8080 (kodi/kodi)"
echo "    JSON-RPC:      http://localhost:9090"
echo ""

exec "$KODI_BIN" --standalone --debug
