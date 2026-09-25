# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for solarView
# Run via:  ./build.sh
#
# Produces:  dist/solarView.app  (macOS .app bundle)
#            dist/solarView-1.0.0-macos-arm64.dmg  (distributable DMG)

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Data files bundled into the app ──────────────────────────────────────────
datas = [
    # Default config shipped inside the bundle
    ('config/default.yaml',       'config'),
    # README shown in the About → View README panel
    ('README.md',                 '.'),
]

# Collect matplotlib's data (font cache, style sheets, etc.)
datas += collect_data_files('matplotlib')

# Collect pymodbus data files if any
datas += collect_data_files('pymodbus')

# Collect Pillow — matplotlib depends on it at runtime
datas += collect_data_files('PIL')

# ── Hidden imports that PyInstaller static analysis misses ───────────────────
hiddenimports = [
    # matplotlib TkAgg backend — not auto-detected because it's selected at runtime
    'matplotlib.backends.backend_tkagg',
    'matplotlib.backends._backend_tk',
    # pymodbus transports
    'pymodbus.client',
    'pymodbus.client.tcp',
    'pymodbus.framer',
    'pymodbus.framer.socket',
    'pymodbus.pdu',
    # tkinter — usually bundled but be explicit
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    # yaml
    'yaml',
    # Pillow — required by matplotlib.colors at runtime
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFilter',
    # our packages
    'solaredge_modbus',
    'solaredge_modbus.client',
    'solaredge_modbus.registers',
    'ui',
    'ui.about',
    'ui.charts',
    'ui.dashboard',
    'ui.summary',
]

hiddenimports += collect_submodules('pymodbus')
hiddenimports += collect_submodules('PIL')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Only exclude GUI toolkits we definitely don't use
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'wx', 'gi', 'gtk',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='solarView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,       # UPX causes issues with macOS code signing — leave off
    console=False,   # No terminal window on macOS
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/solarview.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name='solarView',
)

app = BUNDLE(
    coll,
    name='solarView.app',
    icon='icons/solarview.icns',
    bundle_identifier='com.daneyand.solarview',
    info_plist={
        'CFBundleDisplayName':        'solarView',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion':            '1.0.0',
        'NSHighResolutionCapable':    True,
        'LSUIElement':                False,
        # Allow network access for Modbus TCP
        'NSAppTransportSecurity': {
            'NSAllowsArbitraryLoads': True,
        },
    },
)
