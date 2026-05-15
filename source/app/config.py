"""
Global configuration management
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from core.runtime_paths import get_appdata_dir, get_bundled_rscript, is_frozen


@dataclass
class AppConfig:
    r_executable: str = "Rscript"
    default_seed: int = 1234
    preview_dpi: int = 150
    export_dpi: int = 300
    max_recent_projects: int = 10
    recent_projects: list = field(default_factory=list)

    qc_min_ncount: int = 500
    qc_max_ncount: int = 50000
    qc_min_nfeature: int = 250
    qc_max_nfeature: int = 5000
    qc_max_mt_percent: float = 5.0
    qc_remove_mt_genes: bool = True
    qc_mt_pattern: str = "^[mM][tT]-"
    qc_min_gene_umi: int = 3
    qc_regress_vars: str = "nCount_RNA,percent.mt"

    doublet_expected_rate: float = 0.06
    doublet_pcs: str = "1:30"
    doublet_pn: float = 0.25
    doublet_sct: bool = False

    cluster_hvg_number: int = 3000
    cluster_npcs: int = 50
    cluster_dims: str = "1:30"
    cluster_resolution: float = 1.2

    annotation_min_pct: float = 0.25
    annotation_logfc: float = 0.25
    annotation_only_pos: bool = True
    annotation_profile: str = "Conservative"

    deg_test_use: str = "MAST"
    deg_min_pct: float = 0.1
    deg_logfc_threshold: float = 0.6
    deg_padj_cutoff: float = 0.05

    ui_theme: str = "light"
    color_scheme: str = "publication_classic"


def get_config_dir() -> str:
    return str(get_appdata_dir())


def _config_path() -> Path:
    return get_appdata_dir().joinpath("app_config.json")


def load_app_config() -> AppConfig:
    config_path = _config_path()
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            allowed = {
                key: value
                for key, value in data.items()
                if key in AppConfig.__dataclass_fields__
            }
            return AppConfig(**allowed)
        except Exception:
            pass
    return AppConfig()


def save_app_config(config: AppConfig):
    config_path = _config_path()
    config_path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_rscript() -> Optional[str]:
    bundled = get_bundled_rscript()
    if bundled and is_frozen():
        return str(bundled)

    rscript = shutil.which("Rscript")
    if rscript:
        return rscript

    if os.name == "nt":
        program_files = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        for pf in program_files:
            r_dir = os.path.join(pf, "R")
            if not os.path.isdir(r_dir):
                continue
            for entry in sorted(os.listdir(r_dir), reverse=True):
                candidate = os.path.join(r_dir, entry, "bin", "Rscript.exe")
                if os.path.isfile(candidate):
                    return candidate
    else:
        for candidate in (
            "/usr/local/bin/Rscript",
            "/opt/homebrew/bin/Rscript",
            "/Library/Frameworks/R.framework/Resources/bin/Rscript",
            "/Library/Frameworks/R.framework/Versions/Current/Resources/bin/Rscript",
        ):
            if os.path.isfile(candidate):
                return candidate

    bundled = get_bundled_rscript()
    if bundled:
        return str(bundled)
    return None
