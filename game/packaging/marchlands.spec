# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for a double-clickable Marchlands.

One file, no console window, and the browser view opens by itself. Three
things in here are load-bearing and each one is a way this otherwise ships
broken:

* **`datas`.** The drawn view is served off disk -- a page, a stylesheet and
  two scripts -- so they have to be inside the bundle. Without this the exe
  starts, serves a path that does not exist and shows a blank page, which is
  exactly the failure `pyproject.toml` warns about for wheels arrived at by a
  different route. `web._static_dir` is the other half of the fix.
* **`console=False`.** Somebody who double-clicks a game should not get a
  black terminal window sitting behind their browser for the whole session.
* **`hiddenimports`.** The scenario table reaches its modules by name in
  places, and PyInstaller's import graph does not always follow that.

Built by .github/workflows/marchlands-windows.yml on every push that
touches the game, and attached to the release on a `marchlands-v*` tag. To
build one by hand see packaging/README.md.
"""

import os

block_cipher = None
HERE = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(HERE, "packaging", "launch.py")],
    pathex=[HERE],
    binaries=[],
    datas=[(os.path.join(HERE, "marchlands", "static"),
            os.path.join("marchlands", "static"))],
    hiddenimports=[
        "marchlands.cartography", "marchlands.chancery", "marchlands.culture",
        "marchlands.keep", "marchlands.lords", "marchlands.voices",
        "marchlands.league", "marchlands.economics", "marchlands.kin",
        "marchlands.scenarios", "marchlands.campaign", "marchlands.sim",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "doctest", "test"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Marchlands",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(HERE, "packaging", "marchlands.ico")
    if os.path.exists(os.path.join(HERE, "packaging", "marchlands.ico")) else None,
)
