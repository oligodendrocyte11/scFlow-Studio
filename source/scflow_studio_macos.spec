# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd().resolve()
HIDDEN_IMPORTS = (
    collect_submodules("cryptography")
    + collect_submodules("openpyxl")
    + collect_submodules("app")
    + collect_submodules("core")
    + collect_submodules("ui")
    + collect_submodules("widgets")
    + collect_submodules("tools")
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
    (ROOT / "resources", "resources"),
    (ROOT / "celldex_cache", "celldex_cache"),
    (ROOT / "vendor" / "R.framework", "vendor/R.framework"),
    (ROOT / "vendor" / "cellassign_runtime", "vendor/cellassign_runtime"),
    (ROOT / "vendor" / "cellassign_py", "vendor/cellassign_py"),
    (ROOT / "vendor" / "cellassign_Rsrc", "vendor/cellassign_Rsrc"),
    (ROOT / "r_scripts", "r_scripts"),
    (ROOT / "Singlecell.icns", "."),
    (ROOT / "Singlecell.png", "."),
    (ROOT / "qt.conf", "."),
]:
    if source.exists():
        DATAS.append((str(source), target))

icon_path = ROOT / "Singlecell.icns"
app_icon = str(icon_path) if icon_path.exists() else None

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
    icon=app_icon,
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

app = BUNDLE(
    coll,
    name="scFlow Studio.app",
    icon=app_icon,
    bundle_identifier="com.scflowstudio.app",
    info_plist={
        "CFBundleName": "scFlow Studio",
        "CFBundleDisplayName": "scFlow Studio",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
    },
)
