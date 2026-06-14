# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('data', 'data'), ('.env', '.'), ('.env.example', '.')]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['sequoia_x', 'sequoia_x.core.config', 'sequoia_x.core.logger', 'sequoia_x.data.engine', 'sequoia_x.strategy.base', 'sequoia_x.strategy.turtle_trade', 'sequoia_x.strategy.ma_volume', 'sequoia_x.strategy.high_tight_flag', 'sequoia_x.strategy.limit_up_shakeout', 'sequoia_x.strategy.uptrend_limit_down', 'sequoia_x.strategy.rps_breakout', 'sequoia_x.strategy.private_placement', 'sequoia_x.notify.feishu'],
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
    a.binaries,
    a.datas,
    [],
    name='Sequoia-X',
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
)
