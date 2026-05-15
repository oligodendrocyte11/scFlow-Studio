# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd().resolve()
HIDDEN_IMPORTS = collect_submodules("cryptography")
EXCLUDES = [
    "matplotlib",
    "matplotlib_inline",
    "matplotlib.backends",
    "pyarrow",
    "pytest",
    "IPython",
    "jedi",
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt6",
    "PySide2",
    "qtpy",
    "numexpr",
    "bottleneck",
    "tables",
    "sqlalchemy",
    "botocore",
]
DATAS = []

for source, target in [
    (ROOT / "resources", "resources"),
    (ROOT / "r_scripts", "r_scripts"),
    (ROOT / "Singlecell.ico", "."),
    (ROOT / "vendor" / "R-portable", "vendor/R-portable"),
]:
    if source.exists():
        DATAS.append((str(source), target))


a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scFlow Studio Debug",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ROOT / "Singlecell.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="scFlow Studio Debug",
)

