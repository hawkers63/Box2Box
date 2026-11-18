# PyInstaller spec for a single-file Box2Box.exe (windowed): dist\Box2Box.exe.
# Same bundled data as Box2Box.spec. The exe unpacks itself to a temporary folder (sys._MEIPASS) on each start, so
# anything the app writes must go beside sys.executable, which fm_review.APP_DIR does.

from pathlib import Path

import tkinterdnd2

ROOT = Path(SPECPATH)
TKDND_SOURCE = Path(tkinterdnd2.__file__).parent / "tkdnd"
ICON_PATH = ROOT / "icon" / "football-64-sky-blue.ico"

a = Analysis(
    ["fm_review.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(TKDND_SOURCE), "tkinterdnd2/tkdnd"),
        (str(ROOT / "LICENSE"), "."),
        (str(ROOT / "icon" / "football-64-sky-blue.ico"), "icon"),
        (str(ROOT / "fonts"), "fonts"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "test_fm_data",
        "test_fm_review_ui",
        "fm27_probe",
    ],
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
    name="Box2Box",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
)
