# -*- mode: python ; coding: utf-8 -*-
r"""
PyInstaller build recipe for ParrotRelay.

Build with:
    pyinstaller ParrotRelay.spec

Two modes, switched with ONEFILE below.

ONEFILE = False (default, recommended)
    Produces:
        dist\ParrotRelay\ParrotRelay.exe
        dist\ParrotRelay\RelayData\...      <- runtime files
    Copy the whole "ParrotRelay" folder into the TeknoParrot folder:
        D:\ROM\TeknoParrot\ParrotRelay\ParrotRelay.exe
        D:\ROM\TeknoParrot\ParrotRelay\RelayData\
        D:\ROM\TeknoParrot\ParrotRelay\GameConfigs\   (created at runtime)
        D:\ROM\TeknoParrot\ParrotRelay\parrot_relay_log.txt
    Nothing is ever unpacked into %TEMP%: the files simply stay
    where they are and are used directly on every launch, so
    startup is faster and there is no leftover-temp-folder problem.
    All the clutter sits in RelayData; the folder the user opens
    holds only their own files.

    This mode also sidesteps the RPCS3 "vcruntime140.dll was
    incorrectly installed at ...\_MEIxxxxxx\..." error for good,
    since there is no _MEI folder to inherit in the first place.

ONEFILE = True
    Produces a single dist\ParrotRelay.exe. Convenient to hand
    around, but the bootloader unpacks the whole runtime into a
    fresh temp folder on EVERY launch and deletes it afterwards -
    existing files are never reused; that is how onefile works.
    Set RUNTIME_TMPDIR to an ABSOLUTE path to at least move that
    unpack folder out of %TEMP% and next to the exe, e.g.
        RUNTIME_TMPDIR = r"D:\ROM\TeknoParrot\ParrotRelay\runtime"
    Leave it as None to keep the default %TEMP% location.
"""

ONEFILE = False
RUNTIME_TMPDIR = None

# One directory level only - PyInstaller rejects nested paths here.
# The exe ships inside its own "ParrotRelay" folder, so the runtime
# files end up in ParrotRelay\RelayData and the folder the user
# actually opens (ParrotRelay) holds nothing but RelayData,
# GameConfigs and the log.
CONTENTS_DIRECTORY = "RelayData"

a = Analysis(
    ["parrot_relay.py"],
    pathex=[],
    binaries=[],
    # The icon is bundled as a file too, not just baked into the exe:
    # Tk needs a real .ico on disk for the window and taskbar icon.
    datas=[("icon.ico", ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="ParrotRelay",
        console=False,
        icon="icon.ico",
        upx=True,
        runtime_tmpdir=RUNTIME_TMPDIR,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ParrotRelay",
        console=False,
        icon="icon.ico",
        upx=True,
        contents_directory=CONTENTS_DIRECTORY,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        name="ParrotRelay",
        upx=True,
    )
