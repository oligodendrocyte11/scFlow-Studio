"""
2:Single-Sample QC
:
1. Shared parameters for all samples
2. Per-sample parameters
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.matrix_importer import split_sparse_bundle_folder
from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


class QCPage(BasePage):
    STEP_ID = "qc"
    STEP_NAME = "② Single-Sample QC"

    def __init__(self, main_window, app_config, r_bridge, task_runner):
        self._updating_ui = False
        self._current_sample_name = ""
        super().__init__(main_window, app_config, r_bridge, task_runner)

    def _default_shared_params(self) -> dict:
        cfg = self.app_config
        return {
            "min_ncount": cfg.qc_min_ncount,
            "max_ncount": cfg.qc_max_ncount,
            "min_nfeature": cfg.qc_min_nfeature,
            "max_nfeature": cfg.qc_max_nfeature,
            "max_mt_percent": cfg.qc_max_mt_percent,
            "mt_pattern": cfg.qc_mt_pattern,
            "remove_mt_genes": cfg.qc_remove_mt_genes,
        }

    def _default_settings(self) -> dict:
        return {
            "mode": "shared",
            "skip_step": False,
            "shared_params": self._default_shared_params(),
            "per_sample_params": {},
        }

    def _settings(self) -> dict:
        if not self.project:
            return self._default_settings()
        settings = self.project.analysis_settings.setdefault("qc", self._default_settings())
        settings.setdefault("mode", "shared")
        settings.setdefault("skip_step", False)
        settings.setdefault("shared_params", {})
        settings.setdefault("per_sample_params", {})
        merged = self._default_shared_params()
        merged.update(settings["shared_params"])
        settings["shared_params"] = merged
        return settings

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)

        grp_mode = QGroupBox("Parameters")
        form_mode = QFormLayout(grp_mode)
        self.chk_same_params = QCheckBox("Use the same QC parameters for all samples")
        self.chk_same_params.setChecked(True)
        self.chk_same_params.toggled.connect(self._on_mode_toggled)
        self.chk_skip_step = QCheckBox("Skip QC (use raw objects downstream)")
        self.chk_skip_step.toggled.connect(self._on_skip_toggled)

        self.cmb_sample = QComboBox()
        self.cmb_sample.currentIndexChanged.connect(self._on_sample_changed)

        self.lbl_mode_tip = QLabel("Shared parameter mode: the QC settings below will be applied to all samples.")
        self.lbl_mode_tip.setWordWrap(True)
        self.lbl_mode_tip.setStyleSheet("color:#666; padding:4px 0;")
        self.lbl_skip_tip = QLabel("QC filtering is enabled.")
        self.lbl_skip_tip.setWordWrap(True)
        self.lbl_skip_tip.setStyleSheet("color:#8A6D3B; padding:2px 0;")

        form_mode.addRow("", self.chk_same_params)
        form_mode.addRow("", self.chk_skip_step)
        form_mode.addRow("Current sample:", self.cmb_sample)
        form_mode.addRow("", self.lbl_mode_tip)
        form_mode.addRow("", self.lbl_skip_tip)
        layout.addWidget(grp_mode)

        grp_qc = QGroupBox("QC Parameters")
        form_qc = QFormLayout(grp_qc)

        self.spn_min_ncount = QSpinBox()
        self.spn_min_ncount.setRange(0, 100000)

        self.spn_max_ncount = QSpinBox()
        self.spn_max_ncount.setRange(0, 500000)

        self.spn_min_nfeature = QSpinBox()
        self.spn_min_nfeature.setRange(0, 50000)

        self.spn_max_nfeature = QSpinBox()
        self.spn_max_nfeature.setRange(0, 50000)

        self.spn_max_mt = QDoubleSpinBox()
        self.spn_max_mt.setRange(0, 100)
        self.spn_max_mt.setDecimals(1)
        self.spn_max_mt.setSuffix(" %")

        self.txt_mt_pattern = QLineEdit()
        self.chk_remove_mt = QCheckBox("Remove mitochondrial genes after QC")

        form_qc.addRow("Minimum UMI (nCount_RNA):", self.spn_min_ncount)
        form_qc.addRow("Maximum UMI (nCount_RNA):", self.spn_max_ncount)
        form_qc.addRow("Minimum genes (nFeature_RNA):", self.spn_min_nfeature)
        form_qc.addRow("Maximum genes (nFeature_RNA):", self.spn_max_nfeature)
        form_qc.addRow("Maximum mitochondrial percentage:", self.spn_max_mt)
        form_qc.addRow("mitochondrialgenes:", self.txt_mt_pattern)
        form_qc.addRow("", self.chk_remove_mt)
        layout.addWidget(grp_qc)

        self.lbl_scope = QLabel("")
        self.lbl_scope.setWordWrap(True)
        self.lbl_scope.setStyleSheet("color:#1976D2; padding:2px 0 0 2px;")
        layout.addWidget(self.lbl_scope)

        self.spn_min_ncount.valueChanged.connect(self._on_params_changed)
        self.spn_max_ncount.valueChanged.connect(self._on_params_changed)
        self.spn_min_nfeature.valueChanged.connect(self._on_params_changed)
        self.spn_max_nfeature.valueChanged.connect(self._on_params_changed)
        self.spn_max_mt.valueChanged.connect(self._on_params_changed)
        self.txt_mt_pattern.textChanged.connect(self._on_params_changed)
        self.chk_remove_mt.toggled.connect(self._on_params_changed)

        self.bind_help_refresh(
            self.cmb_sample,
            self.chk_same_params,
            self.chk_skip_step,
            self.spn_min_ncount,
            self.spn_max_ncount,
            self.spn_min_nfeature,
            self.spn_max_nfeature,
            self.spn_max_mt,
            self.txt_mt_pattern,
            self.chk_remove_mt,
        )
        self.reset_params()
        return container

    def _capture_form_params(self) -> dict:
        return {
            "min_ncount": self.spn_min_ncount.value(),
            "max_ncount": self.spn_max_ncount.value(),
            "min_nfeature": self.spn_min_nfeature.value(),
            "max_nfeature": self.spn_max_nfeature.value(),
            "max_mt_percent": self.spn_max_mt.value(),
            "mt_pattern": self.txt_mt_pattern.text().strip(),
            "remove_mt_genes": self.chk_remove_mt.isChecked(),
        }

    def _apply_form_params(self, params: dict):
        params = {**self._default_shared_params(), **(params or {})}
        self._updating_ui = True
        try:
            self.spn_min_ncount.setValue(int(params["min_ncount"]))
            self.spn_max_ncount.setValue(int(params["max_ncount"]))
            self.spn_min_nfeature.setValue(int(params["min_nfeature"]))
            self.spn_max_nfeature.setValue(int(params["max_nfeature"]))
            self.spn_max_mt.setValue(float(params["max_mt_percent"]))
            self.txt_mt_pattern.setText(str(params["mt_pattern"]))
            self.chk_remove_mt.setChecked(bool(params["remove_mt_genes"]))
        finally:
            self._updating_ui = False

    def _sample_names(self) -> list[str]:
        if not self.project or not self.project.samples:
            return []
        return [sample.name for sample in self.project.samples]

    def _save_current_sample_params(self):
        if self._updating_ui or not self.project:
            return
        settings = self._settings()
        if self.chk_same_params.isChecked():
            settings["shared_params"] = self._capture_form_params()
        else:
            sample_name = self._current_sample_name
            if sample_name:
                settings["per_sample_params"][sample_name] = self._capture_form_params()

    def _seed_per_sample_from_shared(self):
        if not self.project:
            return
        settings = self._settings()
        shared = dict(settings["shared_params"])
        for sample_name in self._sample_names():
            settings["per_sample_params"].setdefault(sample_name, dict(shared))

    def _update_mode_tip(self):
        if self.chk_skip_step.isChecked():
            self.lbl_skip_tip.setText("Skip QC is enabled. Raw objects will be passed to the next step without filtering.")
        else:
            self.lbl_skip_tip.setText("QC filtering is enabled.")
        if self.chk_same_params.isChecked():
            self.lbl_mode_tip.setText("Shared parameters: the same QC settings are applied to all samples.")
            self.lbl_scope.setText("All samples use the shared QC parameters.")
        else:
            sample_name = self._current_sample_name or "Sample"
            self.lbl_mode_tip.setText("Per-sample mode: switch samples to save independent QC parameters for each sample.")
            self.lbl_scope.setText(f"Editing sample: {sample_name}. Each sample will use its own QC parameters.")
        self.cmb_sample.setEnabled(not self.chk_same_params.isChecked())

    def _persist_settings(self):
        if not self.project or self._updating_ui:
            return
        self._save_current_sample_params()
        settings = self._settings()
        settings["mode"] = "shared" if self.chk_same_params.isChecked() else "per_sample"
        settings["skip_step"] = self.chk_skip_step.isChecked()
        self.project.analysis_settings["qc"] = settings
        self.main_window.project_manager.save_project(self.project)

    def _load_settings_to_ui(self):
        settings = self._settings()
        self._updating_ui = True
        try:
            self.chk_same_params.setChecked(settings.get("mode", "shared") != "per_sample")
            self.chk_skip_step.setChecked(bool(settings.get("skip_step", False)))
        finally:
            self._updating_ui = False

        if self.chk_same_params.isChecked():
            self._apply_form_params(settings["shared_params"])
        else:
            if not self._current_sample_name and self.cmb_sample.count() > 0:
                self._current_sample_name = self.cmb_sample.currentData() or self.cmb_sample.currentText()
            sample_params = settings["per_sample_params"].get(self._current_sample_name, settings["shared_params"])
            self._apply_form_params(sample_params)
        self._update_mode_tip()

    def _refresh_samples(self):
        self.cmb_sample.clear()
        if self.project and self.project.samples:
            for sample in self.project.samples:
                self.cmb_sample.addItem(f"{sample.name} ({sample.group})", sample.name)
            if self.project.samples:
                species = (self.project.samples[0].species or "").strip().lower()
                settings = self._settings()
                if not settings["shared_params"].get("mt_pattern"):
                    settings["shared_params"]["mt_pattern"] = "^MT-" if species == "human" else "^[mM][tT]-"
        self._current_sample_name = self.cmb_sample.currentData() or ""
        self._load_settings_to_ui()
        self.refresh_help()

    def _on_mode_toggled(self, checked: bool):
        if self._updating_ui:
            return
        self._save_current_sample_params()
        settings = self._settings()
        if not checked:
            settings["shared_params"] = self._capture_form_params()
            self._seed_per_sample_from_shared()
            sample_name = self.cmb_sample.currentData() or self._current_sample_name
            self._current_sample_name = sample_name or ""
            sample_params = settings["per_sample_params"].get(self._current_sample_name, settings["shared_params"])
            self._apply_form_params(sample_params)
        else:
            settings["shared_params"] = self._capture_form_params()
            self._apply_form_params(settings["shared_params"])
        settings["mode"] = "shared" if checked else "per_sample"
        self._update_mode_tip()
        self._persist_settings()
        self.refresh_help()

    def _on_sample_changed(self, _idx: int):
        if self._updating_ui:
            return
        self._save_current_sample_params()
        self._current_sample_name = self.cmb_sample.currentData() or ""
        if not self.chk_same_params.isChecked():
            settings = self._settings()
            params = settings["per_sample_params"].get(self._current_sample_name, settings["shared_params"])
            self._apply_form_params(params)
        self._update_mode_tip()
        self.refresh_help()

    def _on_params_changed(self):
        if self._updating_ui:
            return
        self._persist_settings()
        self._update_mode_tip()
        self.refresh_help()

    def _on_skip_toggled(self, _checked: bool):
        if self._updating_ui:
            return
        self._persist_settings()
        self._update_mode_tip()
        self.refresh_help()

    def get_params(self) -> dict:
        settings = self._settings()
        current_name = self._current_sample_name or (self.cmb_sample.currentData() or "")
        current_params = settings["shared_params"] if settings["mode"] == "shared" else settings["per_sample_params"].get(current_name, settings["shared_params"])
        return {
            "mode": settings["mode"],
            "skip_step": bool(settings.get("skip_step", False)),
            "shared_params": settings["shared_params"],
            "per_sample_params": settings["per_sample_params"],
            "current_sample": current_name,
            "current_params": current_params,
            "min_gene_umi": self.app_config.qc_min_gene_umi,
            "regress_vars": self.app_config.qc_regress_vars,
            "seed": self.app_config.default_seed,
        }

    def reset_params(self):
        self._apply_form_params(self._default_shared_params())
        self._updating_ui = True
        try:
            self.chk_same_params.setChecked(True)
            self.chk_skip_step.setChecked(False)
        finally:
            self._updating_ui = False
        self._update_mode_tip()

    def get_help_html(self) -> str:
        params = self.get_params()
        current_params = params["current_params"]
        return build_step_help(
            "qc",
            {
                "mode": params["mode"],
                "skip_step": params["skip_step"],
                "current_sample": params["current_sample"] or "All Samples",
                "min_ncount": current_params["min_ncount"],
                "max_ncount": current_params["max_ncount"],
                "min_nfeature": current_params["min_nfeature"],
                "max_nfeature": current_params["max_nfeature"],
                "max_mt_percent": current_params["max_mt_percent"],
                "mt_pattern": current_params["mt_pattern"],
                "remove_mt_genes": current_params["remove_mt_genes"],
                "min_gene_umi": self.app_config.qc_min_gene_umi,
            },
        )

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_samples()

    def on_page_entered(self):
        self._refresh_samples()
        self.refresh_help()

    def _prepare_sparse_bundle_runtime(self, samples):
        bundle_samples = [s for s in samples if getattr(s, "data_type", "") == "Sparse Bundle Folder"]
        if not bundle_samples:
            return {}

        runtime_map = {}
        grouped = {}
        for sample in bundle_samples:
            grouped.setdefault(sample.data_path, []).append(sample)

        for bundle_path, sample_group in grouped.items():
            base_root = os.path.basename(os.path.normpath(bundle_path))
            output_root = os.path.join(
                self.project.cache_subdir("raw_index"),
                "folder_bundle_runtime",
                base_root,
            )

            missing = []
            for sample in sample_group:
                target_dir = os.path.join(output_root, sample.name)
                required = [
                    os.path.join(target_dir, "barcodes.tsv.gz"),
                    os.path.join(target_dir, "features.tsv.gz"),
                    os.path.join(target_dir, "matrix.mtx.gz"),
                ]
                if all(os.path.isfile(path) for path in required):
                    runtime_map[sample.name] = target_dir
                else:
                    missing.append(sample)

            if not missing:
                continue

            progress = QProgressDialog("Previewing QC matrix samples...", None, 0, 100, self)
            progress.setWindowTitle("Single-Sample QC")
            progress.setMinimumDuration(0)
            progress.setCancelButton(None)
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(0)
            progress.show()

            def _update_progress(percent: int, message: str):
                progress.setValue(max(0, min(int(percent), 100)))
                progress.setLabelText(message)
                QApplication.processEvents()

            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                outputs = split_sparse_bundle_folder(
                    bundle_path,
                    [
                        {
                            "sample_name": s.name,
                            "group": s.group,
                            "library_identity": getattr(s, "library_identity", s.name),
                            "cell_count": getattr(s, "cell_count", 0),
                            "gene_count": getattr(s, "gene_count", 0),
                        }
                        for s in missing
                    ],
                    output_root,
                    progress_callback=_update_progress,
                )
            finally:
                progress.close()
                QApplication.restoreOverrideCursor()

            for item in outputs:
                runtime_map[item["sample_name"]] = item["data_path"]

        return runtime_map

    def _build_samples_info(self, samples, runtime_map=None):
        runtime_map = runtime_map or {}
        settings = self._settings()
        shared_params = dict(settings["shared_params"])
        per_sample = settings["per_sample_params"]
        sample_items = []
        for sample in samples:
            data_type = sample.data_type
            data_path = sample.data_path
            if sample.name in runtime_map:
                data_type = "10X Matrix Folder"
                data_path = runtime_map[sample.name]

            effective_params = dict(shared_params)
            if settings["mode"] == "per_sample":
                effective_params.update(per_sample.get(sample.name, {}))

            sample_items.append(
                {
                    "name": sample.name,
                    "group": sample.group,
                    "species": sample.species,
                    "data_type": data_type,
                    "data_path": data_path.replace("\\", "/"),
                    "library_identity": getattr(sample, "library_identity", ""),
                    "split_suffix": getattr(sample, "split_suffix", ""),
                    "qc_params": effective_params,
                }
            )
        return sample_items

    def run_step(self):
        if not self.require_project():
            return
        if not self.project.samples:
            QMessageBox.warning(self, "Notice", " QC Sample.")
            return

        self._persist_settings()
        self.clear_log()
        settings = self._settings()
        if settings.get("skip_step", False):
            self.append_log("=== Skip Single-Sample QC ===")
            self.append_log("Skip QC. QC Object.")
        else:
            self.append_log("=== Single-Sample QC ===")
        runtime_map = self._prepare_sparse_bundle_runtime(self.project.samples)

        params = dict(settings["shared_params"])
        params["min_gene_umi"] = self.app_config.qc_min_gene_umi
        params["regress_vars"] = self.app_config.qc_regress_vars
        params["seed"] = self.app_config.default_seed
        params["param_mode"] = settings["mode"]
        params["skip_step"] = bool(settings.get("skip_step", False))
        params["per_sample_params"] = settings["per_sample_params"]
        params["samples"] = self._build_samples_info(self.project.samples, runtime_map)
        params["cache_dir"] = self.project.cache_subdir("qc").replace("\\", "/")

        self.register_task_owner()
        self.task_runner.run_r_script(
            script_name="02_qc_passthrough.R" if settings.get("skip_step", False) else "02_qc.R",
            params=params,
            output_dir=self.project.cache_subdir("qc"),
            step_name="Skip Single-Sample QC" if settings.get("skip_step", False) else "Single-Sample QC",
        )

        self.project.step_status["qc"] = "running"
        idx = self.main_window.get_step_index("qc")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "running")

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        skipped = bool(summary.get("skipped", False))
        if skipped:
            self.append_log("=== QC skip ===")
            self.append_log("QC was skipped. Downstream analysis will use the unfiltered objects.")
        else:
            self.append_log("=== QC Finished ===")
        self.project.step_status["qc"] = "done"
        idx = self.main_window.get_step_index("qc")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

        if "sample_stats" in summary:
            stats = summary["sample_stats"]
            headers = ["Sample", "", "", "", ""]
            data = [
                [
                    item.get("name", ""),
                    str(item.get("cells_before", "")),
                    str(item.get("cells_after", "")),
                    str(item.get("cells_removed", "")),
                    item.get("pct_removed", item.get("percent_removed", "")),
                ]
                for item in stats
            ]
            self.set_result_table(data, headers)
            self.main_window.show_preview_table(data, headers, "QC Statistics")

        figures = getattr(result, "figures", summary.get("figures", []))
        cache_dir = self.project.cache_subdir("qc")
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache_dir, fig)
            if os.path.isfile(fig_path):
                name = os.path.splitext(os.path.basename(fig_path))[0]
                self.main_window.add_preview_item(name=name, path=fig_path, item_type="figure", step="QC")
                self.append_log(f"Generated QC object: {name}")

        self.main_window.project_manager.save_project(self.project)

    def on_step_error(self, step, summary, detail):
        QMessageBox.warning(self, "QC Failed", summary)

    def preview(self):
        if not self.require_project():
            return
        idx = self.cmb_sample.currentIndex()
        if idx < 0 or not self.project.samples:
            QMessageBox.warning(self, "Notice", "Sample.")
            return

        sample = self.project.samples[idx]
        self._persist_settings()
        self.append_log(f"Sample QC: {sample.name}")
        runtime_map = self._prepare_sparse_bundle_runtime([sample])

        settings = self._settings()
        params = dict(settings["shared_params"])
        params["min_gene_umi"] = self.app_config.qc_min_gene_umi
        params["regress_vars"] = self.app_config.qc_regress_vars
        params["seed"] = self.app_config.default_seed
        params["param_mode"] = settings["mode"]
        params["skip_step"] = bool(settings.get("skip_step", False))
        params["per_sample_params"] = settings["per_sample_params"]
        params["samples"] = self._build_samples_info([sample], runtime_map)
        params["cache_dir"] = self.project.cache_subdir("qc").replace("\\", "/")
        params["preview_only"] = True

        self.register_task_owner()
        self.task_runner.run_r_script(
            script_name="02_qc.R",
            params=params,
            output_dir=self.project.cache_subdir("qc"),
            step_name="QC ",
        )
