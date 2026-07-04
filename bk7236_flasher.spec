# -*- mode: python ; coding: utf-8 -*-

import base64
import sys
from pathlib import Path

SPEC_DIR = Path(globals().get('SPECPATH', '.')).resolve()
WORK_DIR = Path(globals().get('WORKPATH', SPEC_DIR / 'build')).resolve()
sys.path.insert(0, str(SPEC_DIR))

from bk7236_flasher_icon import ICON_ICO_B64


# Build as onedir instead of onefile. This avoids runtime extraction to
# TEMP/_MEI... and removes startup/delete-cache problems caused by onefile.
generated_icon_path = WORK_DIR / 'bk7236_flasher.ico'
generated_icon_path.parent.mkdir(parents=True, exist_ok=True)
generated_icon_path.write_bytes(base64.b64decode(ICON_ICO_B64))

a = Analysis(
    [str(SPEC_DIR / 'bk7236_flasher.py')],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=[
        (str(SPEC_DIR / 'res' / 'bk_loader.exe'), 'res'),
        (str(SPEC_DIR / 'res' / 'bk_loader_nor_ver.exe'), 'res'),
    ],
    hiddenimports=['serial', 'wx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='bk7236_flasher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(generated_icon_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='bk7236_flasher',
)