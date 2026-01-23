# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['bk7236_flasher.py'],
    pathex=['E:\\share\\code\\python_work\\test_for_python\\.venv\\Lib\\site-packages'],
    binaries=[],
    datas=[('res', 'res')],
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
    a.binaries,
    a.datas,
    [],
    name='bk7236_flasher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['res\\bk7236_flasher.ico'],
)
