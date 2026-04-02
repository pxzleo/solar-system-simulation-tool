# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import panda3d
import ursina


panda3d_package_dir = Path(panda3d.__file__).resolve().parent
ursina_package_dir = Path(ursina.__file__).resolve().parent


a = Analysis(
    ['solar_system_3d.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        (str(panda3d_package_dir), 'panda3d'),
        (str(ursina_package_dir), 'ursina'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SolarSystem3D',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SolarSystem3D',
)
