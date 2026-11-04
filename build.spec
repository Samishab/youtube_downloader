# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

# مسار customtkinter لإدراج ملفاته (ثيمات وأيقونات)
import customtkinter
CTK_PATH = str(Path(customtkinter.__file__).parent)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        (CTK_PATH, 'customtkinter'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
    ],
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
    name='YouTube-Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # بدون نافذة CMD
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
