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
    excludes=[
        'distutils', 'lib2to3', 'unittest', 'doctest', 'pydoc',
        'ensurepip', 'venv', 'idlelib', 'turtledemo', 'turtle',
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'xmlrpc', 'ftplib', 'imaplib', 'poplib', 'smtplib',
        'nntplib', 'telnetlib', 'cgi', 'cgitb', 'curses',
        'test', 'tkinter.test',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, optimize=2)

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
