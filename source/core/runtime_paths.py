from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "scFlowStudio"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_app_root() -> Path:
    if is_frozen():
        bundle_root = getattr(sys, "_MEIPASS", "")
        if bundle_root:
            return Path(bundle_root).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(*parts: str) -> Path:
    return get_app_root().joinpath("resources", *parts)


def get_r_scripts_dir() -> Path:
    return get_app_root().joinpath("r_scripts")


def get_vendor_path(*parts: str) -> Path:
    return get_app_root().joinpath("vendor", *parts)


def get_bundled_rscript() -> Path | None:
    if os.name == "nt":
        candidate = get_vendor_path("R-portable", "bin", "Rscript.exe")
        return candidate if candidate.is_file() else None

    framework_root = get_vendor_path("R.framework")
    candidates = [
        framework_root.joinpath("Resources", "bin", "scflow_Rscript"),
        framework_root.joinpath("Versions", "Current", "Resources", "bin", "scflow_Rscript"),
    ]
    candidates.extend(sorted(framework_root.glob("Versions/*/Resources/bin/scflow_Rscript")))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def get_icon_path() -> Path:
    for name in ("Singlecell.icns", "Singlecell.png", "Singlecell.ico"):
        candidate = get_app_root().joinpath(name)
        if candidate.is_file():
            return candidate
    return get_app_root().joinpath("Singlecell.ico")


def get_public_key_path() -> Path:
    return get_resource_path("license", "public_key.pem")


def get_appdata_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA", str(Path.home()))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    target = Path(base).joinpath(APP_DIR_NAME)
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_license_dir() -> Path:
    return get_appdata_dir().joinpath("license")
