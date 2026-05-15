"""Project management: create, load, save, and normalize project parameters."""
import json
import os
import time
from dataclasses import asdict, dataclass, field


def default_step_status() -> dict:
    return {
        "project": "pending",
        "qc": "pending",
        "doublet": "pending",
        "batch": "pending",
        "merge_cluster": "pending",
        "annotation": "pending",
        "subcluster": "pending",
        "deg": "pending",
        "gsea": "pending",
        "gene_analysis": "pending",
        "module_score": "pending",
        "export": "pending",
    }


def default_analysis_settings() -> dict:
    return {
        "qc": {
            "mode": "shared",
            "skip_step": False,
            "shared_params": {},
            "per_sample_params": {},
        },
        "doublet": {
            "mode": "shared",
            "skip_step": False,
            "shared_params": {},
            "per_sample_params": {},
        },
        "object_selection": {
            "subcluster_current_result_id": "",
            "deg": "main",
            "gene_analysis": "main",
            "module_score": "main",
            "export": "main",
        },
    }


@dataclass
class SampleInfo:
    """Sample."""

    name: str = ""
    group: str = ""
    data_type: str = "10X Matrix Folder"
    species: str = "Rat"
    data_path: str = ""
    library_identity: str = ""
    split_suffix: str = ""
    status: str = "unchecked"  # unchecked / valid / missing / error
    cell_count: int = 0
    gene_count: int = 0


@dataclass
class Project:
    """Open an existing project."""

    name: str = ""
    directory: str = ""
    ref_mode: str = "reference"  # reference / copy
    created_at: str = ""
    modified_at: str = ""
    samples: list = field(default_factory=list)
    step_status: dict = field(default_factory=default_step_status)
    analysis_settings: dict = field(default_factory=default_analysis_settings)
    subcluster_results: list = field(default_factory=list)
    deg_results: list = field(default_factory=list)
    current_step: str = "project"
    plot_theme: str = "publication_classic"

    @property
    def config_path(self) -> str:
        return os.path.join(self.directory, "project_config.json")

    @property
    def samples_path(self) -> str:
        return os.path.join(self.directory, "samples.json")

    @property
    def cache_dir(self) -> str:
        return os.path.join(self.directory, "cache")

    @property
    def results_dir(self) -> str:
        return os.path.join(self.directory, "results")

    @property
    def logs_dir(self) -> str:
        return os.path.join(self.directory, "logs")

    def cache_subdir(self, step: str) -> str:
        path = os.path.join(self.cache_dir, step)
        os.makedirs(path, exist_ok=True)
        return path

    def figures_dir(self) -> str:
        path = os.path.join(self.results_dir, "figures")
        os.makedirs(path, exist_ok=True)
        return path

    def tables_dir(self) -> str:
        path = os.path.join(self.results_dir, "tables")
        os.makedirs(path, exist_ok=True)
        return path


class ProjectManager:
    """Open an existing project."""

    CACHE_SUBDIRS = [
        "raw_index",
        "qc",
        "doublet",
        "batch",
        "merged",
        "clustering",
        "annotation",
        "deg",
        "gsea",
        "gene_analysis",
        "module_score",
        "communication",
        "subcluster",
        "pseudotime",
        "temp",
    ]
    RESULT_SUBDIRS = ["figures", "tables", "reports", "exports"]

    def _normalize_deg_results(self, project_dir: str, loaded_results: list | None) -> list:
        loaded_results = loaded_results or []
        normalized = []
        seen_ids = set()

        for idx, item in enumerate(loaded_results, start=1):
            if not isinstance(item, dict):
                continue
            result_id = str(item.get("result_id", "")).strip() or f"deg_result_{idx:03d}"
            if result_id in seen_ids:
                suffix = 2
                base_id = result_id
                while f"{base_id}_{suffix}" in seen_ids:
                    suffix += 1
                result_id = f"{base_id}_{suffix}"
            seen_ids.add(result_id)

            cache_dir_rel = str(item.get("cache_dir_rel", "") or item.get("cache_dir", "")).strip()
            if not cache_dir_rel:
                cache_dir_rel = os.path.join("cache", "deg", "results", result_id)
            if os.path.isabs(cache_dir_rel):
                try:
                    cache_dir_rel = os.path.relpath(cache_dir_rel, project_dir)
                except Exception:
                    cache_dir_rel = os.path.join("cache", "deg", "results", result_id)

            display_name = str(item.get("display_name", "") or item.get("comparison_name", "") or result_id).strip() or result_id
            normalized.append({
                "result_id": result_id,
                "display_name": display_name,
                "created_at": str(item.get("created_at", "") or ""),
                "cache_dir_rel": cache_dir_rel.replace(chr(92), "/"),
                "object_source_key": str(item.get("object_source_key", "") or "main"),
                "object_source_label": str(item.get("object_source_label", "") or ""),
                "comparison_mode": str(item.get("comparison_mode", "") or "same_celltype"),
                "group_1": str(item.get("group_1", "") or ""),
                "ct_1": str(item.get("ct_1", "") or ""),
                "group_2": str(item.get("group_2", "") or ""),
                "ct_2": str(item.get("ct_2", "") or ""),
                "status": str(item.get("status", "") or "ready"),
                "n_up": int(item.get("n_up", 0) or 0),
                "n_down": int(item.get("n_down", 0) or 0),
                "n_genes_tested": int(item.get("n_genes_tested", 0) or 0),
            })

        return normalized

    def _normalize_subcluster_results(self, project_dir: str, loaded_results: list | None) -> list:
        loaded_results = loaded_results or []
        normalized = []
        seen_ids = set()

        for idx, item in enumerate(loaded_results, start=1):
            if not isinstance(item, dict):
                continue
            result_id = str(item.get("result_id", "")).strip() or f"subcluster_result_{idx:03d}"
            if result_id in seen_ids:
                suffix = 2
                base_id = result_id
                while f"{base_id}_{suffix}" in seen_ids:
                    suffix += 1
                result_id = f"{base_id}_{suffix}"
            seen_ids.add(result_id)

            cache_dir_rel = str(item.get("cache_dir_rel", "") or item.get("cache_dir", "")).strip()
            if not cache_dir_rel:
                cache_dir_rel = os.path.join("cache", "subcluster", "results", result_id)
            if os.path.isabs(cache_dir_rel):
                try:
                    cache_dir_rel = os.path.relpath(cache_dir_rel, project_dir)
                except Exception:
                    cache_dir_rel = os.path.join("cache", "subcluster", "results", result_id)

            display_name = str(item.get("display_name", "") or item.get("result_name", "")).strip() or result_id
            target_celltypes = item.get("target_celltypes", [])
            if isinstance(target_celltypes, str):
                target_celltypes = [target_celltypes]
            target_celltypes = [str(x).strip() for x in target_celltypes if str(x).strip()]

            normalized.append({
                "result_id": result_id,
                "display_name": display_name,
                "target_celltypes": target_celltypes,
                "created_at": str(item.get("created_at", "") or ""),
                "cache_dir_rel": cache_dir_rel.replace("\\", "/"),
                "primary_reduction": str(item.get("primary_reduction", "") or "").lower(),
                "status": str(item.get("status", "") or "ready"),
                "n_cells": int(item.get("n_cells", 0) or 0),
                "n_clusters": int(item.get("n_clusters", 0) or 0),
                "n_subtypes": int(item.get("n_subtypes", 0) or 0),
                "legacy_root": bool(item.get("legacy_root", False)),
            })

        legacy_dir = os.path.join(project_dir, "cache", "subcluster")
        legacy_summary = os.path.join(legacy_dir, "summary.json")
        legacy_subclustered = os.path.join(legacy_dir, "subclustered.rds")
        legacy_annotated = os.path.join(legacy_dir, "sub_annotated.rds")
        has_legacy = any(os.path.isfile(path) for path in (legacy_summary, legacy_subclustered, legacy_annotated))
        has_registered_legacy = any(str(item.get("cache_dir_rel", "")).replace("\\", "/") == "cache/subcluster" for item in normalized)

        if has_legacy and not has_registered_legacy:
            legacy_summary_data = {}
            if os.path.isfile(legacy_summary):
                try:
                    with open(legacy_summary, "r", encoding="utf-8") as handle:
                        legacy_summary_data = json.load(handle)
                except Exception:
                    legacy_summary_data = {}
            target_info = legacy_summary_data.get("target_celltype", legacy_summary_data.get("target_celltypes", []))
            if isinstance(target_info, str):
                target_celltypes = [part.strip() for part in target_info.split("+") if part.strip()]
            else:
                target_celltypes = [str(x).strip() for x in (target_info or []) if str(x).strip()]
            display_name = "+".join(target_celltypes) if target_celltypes else "Subcluster Results"
            normalized.append({
                "result_id": "legacy_subcluster_001",
                "display_name": display_name,
                "target_celltypes": target_celltypes,
                "created_at": "",
                "cache_dir_rel": "cache/subcluster",
                "primary_reduction": str(legacy_summary_data.get("primary_reduction", "") or "").lower(),
                "status": "ready",
                "n_cells": int(legacy_summary_data.get("n_cells", 0) or 0),
                "n_clusters": int(legacy_summary_data.get("n_clusters", 0) or 0),
                "n_subtypes": len(legacy_summary_data.get("subtypes", []) or []),
                "legacy_root": True,
            })

        return normalized

    def create_project(self, name: str, directory: str, ref_mode: str = "reference") -> Project:
        """Create a project directory."""
        project_dir = os.path.join(directory, name)
        os.makedirs(project_dir, exist_ok=True)

        for subdir in self.CACHE_SUBDIRS:
            os.makedirs(os.path.join(project_dir, "cache", subdir), exist_ok=True)
        for subdir in self.RESULT_SUBDIRS:
            os.makedirs(os.path.join(project_dir, "results", subdir), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "logs"), exist_ok=True)

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        project = Project(
            name=name,
            directory=project_dir,
            ref_mode=ref_mode,
            created_at=now,
            modified_at=now,
        )
        self.save_project(project)
        return project

    def _merge_analysis_settings(self, loaded: dict | None) -> dict:
        loaded = loaded or {}
        merged = default_analysis_settings()
        for step_name, default_block in merged.items():
            loaded_block = loaded.get(step_name, {}) or {}
            if step_name == "object_selection":
                merged[step_name] = {
                    "subcluster_current_result_id": str(loaded_block.get("subcluster_current_result_id", default_block["subcluster_current_result_id"]) or ""),
                    "deg_current_result_id": str(loaded_block.get("deg_current_result_id", default_block.get("deg_current_result_id", "")) or ""),
                    "deg": str(loaded_block.get("deg", default_block["deg"]) or "main"),
                    "gene_analysis": str(loaded_block.get("gene_analysis", default_block["gene_analysis"]) or "main"),
                    "module_score": str(loaded_block.get("module_score", default_block["module_score"]) or "main"),
                    "export": str(loaded_block.get("export", default_block["export"]) or "main"),
                }
                continue
            merged[step_name] = {
                "mode": loaded_block.get("mode", default_block["mode"]),
                "skip_step": bool(loaded_block.get("skip_step", default_block.get("skip_step", False))),
                "shared_params": loaded_block.get("shared_params", {}) or {},
                "per_sample_params": loaded_block.get("per_sample_params", {}) or {},
            }
        for step_name, loaded_block in loaded.items():
            if step_name not in merged:
                merged[step_name] = loaded_block
        return merged

    def open_project(self, config_path: str) -> Project:
        """Open an existing project."""
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Project file does not exist: {config_path}")

        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        loaded_step_status = data.get("step_status", {}) or {}
        merged_step_status = default_step_status()
        for step_id in merged_step_status:
            if step_id in loaded_step_status:
                merged_step_status[step_id] = loaded_step_status[step_id]

        project = Project(
            name=data.get("name", ""),
            directory=os.path.dirname(config_path),
            ref_mode=data.get("ref_mode", "reference"),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
            step_status=merged_step_status,
            analysis_settings=self._merge_analysis_settings(data.get("analysis_settings", {})),
            subcluster_results=self._normalize_subcluster_results(os.path.dirname(config_path), data.get("subcluster_results", [])),
            deg_results=self._normalize_deg_results(os.path.dirname(config_path), data.get("deg_results", [])),
            plot_theme=data.get("plot_theme", "publication_classic"),
        )

        if os.path.exists(project.samples_path):
            with open(project.samples_path, "r", encoding="utf-8") as handle:
                samples_data = json.load(handle)
            project.samples = [SampleInfo(**sample) for sample in samples_data]

        return project

    def save_project(self, project: Project):
        """Save project samples and settings."""
        project.modified_at = time.strftime("%Y-%m-%d %H:%M:%S")
        project.analysis_settings = self._merge_analysis_settings(project.analysis_settings)

        config_data = {
            "name": project.name,
            "ref_mode": project.ref_mode,
            "created_at": project.created_at,
            "modified_at": project.modified_at,
            "step_status": project.step_status,
            "analysis_settings": project.analysis_settings,
            "subcluster_results": project.subcluster_results,
            "deg_results": project.deg_results,
            "plot_theme": project.plot_theme,
        }
        with open(project.config_path, "w", encoding="utf-8") as handle:
            json.dump(config_data, handle, indent=2, ensure_ascii=False)

        samples_data = [asdict(sample) for sample in project.samples]
        with open(project.samples_path, "w", encoding="utf-8") as handle:
            json.dump(samples_data, handle, indent=2, ensure_ascii=False)
