# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import PySide6

from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd().resolve()
HIDDEN_IMPORTS = (
    collect_submodules("cryptography")
    + [
        "numpy",
        "pandas",
        "scipy",
        "scipy.io",
        "scipy.sparse",
        "h5py",
    ]
)
EXCLUDES = [
    "matplotlib",
    "matplotlib_inline",
    "matplotlib.backends",
    "pyarrow",
    "anndata",
    "xarray",
    "zarr",
    "dask",
    "distributed",
    "panel",
    "plotly",
    "bokeh",
    "altair",
    "nbconvert",
    "notebook",
    "jupyterlab",
    "skimage",
    "sklearn",
    "numba",
    "llvmlite",
    "cv2",
    "astropy",
    "imageio",
    "pywt",
    "intake",
    "kaleido",
    "sphinx",
    "docutils",
    "paramiko",
    "statsmodels",
    "patsy",
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
BLACKLIST_DLLS = {"icuuc.dll", "icudt73.dll"}

for source, target in [
    (ROOT / "resources" / "styles", "resources/styles"),
    (ROOT / "resources" / "license", "resources/license"),
    (ROOT / "resources" / "celldex_cache" / "R", "resources/celldex_cache/R"),
    (ROOT / "r_scripts", "r_scripts"),
    (ROOT / "Singlecell.ico", "."),
    (ROOT / "qt.conf", "."),
    (ROOT / "vendor" / "R-portable", "vendor/R-portable"),
    (Path(PySide6.__file__).resolve().parent / "plugins" / "platforms", "PySide6/plugins/platforms"),
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
a.binaries = TOC([entry for entry in a.binaries if Path(entry[0]).name.lower() not in BLACKLIST_DLLS])
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scFlow Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "Singlecell.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="scFlow Studio",
)
