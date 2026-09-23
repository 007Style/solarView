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

# Create the DMG
hdiutil create \
    -volname "${APP_NAME} ${VERSION}" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "dist/${DMG_NAME}" \
    2>/dev/null

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
