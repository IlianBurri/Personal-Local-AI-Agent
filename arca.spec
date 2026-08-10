# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build for Arca.
#
#   pip install pyinstaller
#   pyinstaller arca.spec
#
# Produces a standalone app in dist/arca/ that bundles the Python backend,
# the Flask server and the built frontend (ui/web/dist).

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/web/dist', 'ui/web/dist')],
    # webview loads its platform backend (gtk/qt/winforms/...) dynamically,
    # so all submodules must be collected explicitly. The GTK runtime itself
    # (libwebkit2gtk-4.1 etc.) is provided by the distro on Linux; Windows
    # and macOS builds use the OS webviews and are fully self-contained.
    hiddenimports=collect_submodules('flask') + collect_submodules('webview'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6', 'pytest', 'flake8'],
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
    name='arca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='arca',
)
