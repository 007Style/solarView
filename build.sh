#!/usr/bin/env bash
# ── solarView build script ────────────────────────────────────────────────────
#
# Produces a self-contained macOS .app bundle and a distributable DMG.
# No Python installation required on the target machine.
#
# Usage:
#   ./build.sh            — full build (app + DMG)
#   ./build.sh --app-only — build the .app but skip DMG creation
#
# Output:
#   dist/solarView.app
#   dist/solarView-1.0.0-macos-arm64.dmg
#
# Requirements (first time only):
#   python3 -m venv .venv
#   .venv/bin/pip install pyinstaller pymodbus matplotlib numpy pyyaml
#   (build.sh will do this automatically if .venv is missing)
#
# *From the minds of IBM Bob & Daneyand*
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_NAME="solarView"
VERSION="1.0.0"
ARCH="$(uname -m)"          # arm64 or x86_64
DMG_NAME="${APP_NAME}-${VERSION}-macos-${ARCH}.dmg"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SCRIPT_DIR}/.venv"
APP_ONLY=false

# ── Parse args ────────────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --app-only) APP_ONLY=true ;;
        --help|-h)
            echo "Usage: $0 [--app-only]"
            exit 0
            ;;
    esac
done

cd "${SCRIPT_DIR}"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        solarView v${VERSION} — Build Script        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Ensure venv exists with all dependencies ──────────────────────────────────
if [[ ! -f "${VENV}/bin/pyinstaller" ]]; then
    echo "► Creating virtual environment and installing dependencies…"
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install --quiet --upgrade pip
    "${VENV}/bin/pip" install --quiet \
        "pyinstaller>=6.0" \
        "pymodbus>=3.5.0" \
        "matplotlib>=3.7.0" \
        "numpy>=1.24.0" \
        "pyyaml>=6.0"
    echo "  ✓ Dependencies installed"
else
    echo "► Virtual environment found — skipping install"
fi

PYINSTALLER="${VENV}/bin/pyinstaller"
echo "  PyInstaller: $("${PYINSTALLER}" --version)"
echo ""

# ── Clean previous build ──────────────────────────────────────────────────────
echo "► Cleaning previous build artifacts…"
rm -rf build dist
echo "  ✓ Cleaned"
echo ""

# ── Run PyInstaller ───────────────────────────────────────────────────────────
echo "► Building ${APP_NAME}.app with PyInstaller…"
"${PYINSTALLER}" \
    --clean \
    --noconfirm \
    --distpath "${SCRIPT_DIR}/dist" \
    --workpath "${SCRIPT_DIR}/build" \
    "${SCRIPT_DIR}/solarview.spec"

if [[ ! -d "dist/${APP_NAME}.app" ]]; then
    echo ""
    echo "✗ Build failed — dist/${APP_NAME}.app not found"
    exit 1
fi
echo "  ✓ dist/${APP_NAME}.app created"
echo ""

# ── Ad-hoc code sign (no Apple Developer account needed for local use) ────────
echo "► Code signing (ad-hoc)…"
codesign --force --deep --sign - "dist/${APP_NAME}.app" 2>/dev/null && \
    echo "  ✓ Ad-hoc signed" || \
    echo "  ⚠ Code signing skipped (codesign not available)"
echo ""

if [[ "${APP_ONLY}" == "true" ]]; then
    echo "╔══════════════════════════════════════════════╗"
    echo "║  Build complete (.app only)                  ║"
    echo "╚══════════════════════════════════════════════╝"
    echo "  App: dist/${APP_NAME}.app"
    echo ""
    exit 0
fi

# ── Create DMG ────────────────────────────────────────────────────────────────
echo "► Creating DMG: ${DMG_NAME}…"

DMG_STAGING="${SCRIPT_DIR}/build/dmg_staging"
rm -rf "${DMG_STAGING}"
mkdir -p "${DMG_STAGING}"

# Copy app into staging area
cp -r "dist/${APP_NAME}.app" "${DMG_STAGING}/"

# Symlink to /Applications so the user can drag-and-drop
ln -s /Applications "${DMG_STAGING}/Applications"

# ── Install.command — double-click installer that strips quarantine ───────────
# macOS Gatekeeper quarantines every app downloaded from the internet.
# Ad-hoc signed apps (no Apple Developer ID) are blocked silently.
# This script removes the quarantine flag then launches the app — the user
# just double-clicks it in Finder, no Terminal required.
cat > "${DMG_STAGING}/Install.command" << 'INSTALL_EOF'
#!/usr/bin/env bash
# ── solarView — macOS Installer ───────────────────────────────────────────────
# Double-click this file in Finder to install solarView.
# It removes the Gatekeeper quarantine flag and copies the app to /Applications.
set -euo pipefail

APP="solarView.app"
DMG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${DMG_DIR}/${APP}"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ☀️  solarView — macOS Installer    ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Step 1: Remove quarantine from the app bundle ────────────────────────────
echo "► Removing macOS quarantine flag…"
xattr -r -d com.apple.quarantine "${SRC}" 2>/dev/null || true
echo "  ✓ Quarantine cleared"

# ── Step 2: Copy to /Applications ────────────────────────────────────────────
echo "► Copying solarView.app to /Applications…"
if [[ -d "/Applications/${APP}" ]]; then
    echo "  Removing previous version…"
    rm -rf "/Applications/${APP}"
fi
cp -r "${SRC}" "/Applications/${APP}"
echo "  ✓ Installed to /Applications/solarView.app"

# ── Step 3: Remove quarantine from the installed copy too ────────────────────
xattr -r -d com.apple.quarantine "/Applications/${APP}" 2>/dev/null || true

# ── Step 4: Launch ────────────────────────────────────────────────────────────
echo ""
echo "✅ Installation complete! Launching solarView…"
echo ""
open "/Applications/${APP}"
INSTALL_EOF

chmod +x "${DMG_STAGING}/Install.command"

# ── Plain-text open-me note ───────────────────────────────────────────────────
cat > "${DMG_STAGING}/READ ME FIRST.txt" << 'NOTE_EOF'
☀️ solarView — Installation Instructions
==========================================

IF THE APP WON'T OPEN after dragging to Applications:
------------------------------------------------------
macOS blocks apps that aren't signed with an Apple Developer certificate.
Fix it in 5 seconds with ONE of these options:

OPTION 1 — Double-click "Install.command" (easiest)
  It removes the block and launches solarView automatically.
  If Terminal asks for permission, click OK.

OPTION 2 — Right-click the app → Open → Open
  macOS shows a warning but lets you proceed.
  You only need to do this ONCE.

OPTION 3 — Terminal (one line)
  xattr -r -d com.apple.quarantine /Applications/solarView.app

WHY DOES THIS HAPPEN?
---------------------
Apple requires a $99/year Developer ID to sign apps "officially".
solarView is free and open source — we're not paying Apple to give
you free software. The app is completely safe; it's a Python app
that reads Modbus data from your solar inverter over your local network.

Source code: https://github.com/007Style/solarView

From the minds of IBM Bob & Daneyand 🍺
NOTE_EOF

# ── Volume icon ───────────────────────────────────────────────────────────────
if [[ -f "${SCRIPT_DIR}/icons/solarview.icns" ]]; then
    cp "${SCRIPT_DIR}/icons/solarview.icns" "${DMG_STAGING}/.VolumeIcon.icns"
    SetFile -a C "${DMG_STAGING}" 2>/dev/null || true
fi

# Create the DMG (writable first so we can bless the volume icon, then convert)
TEMP_DMG="dist/${APP_NAME}-temp.dmg"
hdiutil create \
    -volname "${APP_NAME} ${VERSION}" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDRW \
    "${TEMP_DMG}" \
    2>/dev/null

# Mount the writable DMG, set the volume icon via osascript, then unmount
MOUNT_DIR="$(mktemp -d)"
hdiutil attach "${TEMP_DMG}" -mountpoint "${MOUNT_DIR}" -noautoopen -quiet 2>/dev/null

# Copy the volume icon into the mounted volume and bless it
if [[ -f "${SCRIPT_DIR}/icons/solarview.icns" ]]; then
    cp "${SCRIPT_DIR}/icons/solarview.icns" "${MOUNT_DIR}/.VolumeIcon.icns"
    SetFile -a C "${MOUNT_DIR}" 2>/dev/null || true
fi

hdiutil detach "${MOUNT_DIR}" -quiet 2>/dev/null
rm -rf "${MOUNT_DIR}"

# Convert the writable DMG to compressed read-only
hdiutil convert "${TEMP_DMG}" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "dist/${DMG_NAME}" \
    -ov 2>/dev/null
rm -f "${TEMP_DMG}"

if [[ ! -f "dist/${DMG_NAME}" ]]; then
    echo "  ✗ DMG creation failed"
    exit 1
fi

DMG_SIZE=$(du -sh "dist/${DMG_NAME}" | cut -f1)
echo "  ✓ dist/${DMG_NAME} (${DMG_SIZE})"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════╗"
echo "║  Build complete ✓                            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  App:  dist/${APP_NAME}.app"
echo "  DMG:  dist/${DMG_NAME}"
echo ""
echo "  To install: open dist/${DMG_NAME}"
echo "              drag solarView → Applications"
echo ""
echo "  From the minds of IBM Bob & Daneyand"
echo ""
