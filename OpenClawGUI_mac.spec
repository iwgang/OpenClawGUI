# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['OpenClawGUI.py'],
    pathex=[],
    binaries=[],
    datas=[('icons', 'icons')],
    hiddenimports=['pystray', 'PIL', 'AppKit', 'Foundation', 'objc'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='OpenClawGUI',
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
    icon='icons/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OpenClawGUI',
)

app = BUNDLE(
    coll,
    name='OpenClawGUI.app',
    icon='icons/icon.icns',
    bundle_identifier='com.iwgang.openclawgui',
    info_plist={
        'CFBundleName': 'OpenClawGUI',
        'CFBundleDisplayName': 'OpenClawGUI',
        'CFBundleVersion': '1.1',
        'CFBundleShortVersionString': '1.1',
        'NSHighResolutionCapable': True,
    },
)
