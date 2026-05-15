"""
3:Doublet Removal(DoubletFinder)
:
1. Shared parameters for all samples
2. Per-sample parameters
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


class DoubletPage(BasePage):
    STEP_ID = "doublet"
    STEP_NAME = "③ Doublet Removal"

    def __init__(self, main_window, app_config, r_bridge, task_runner):
        self._updating_ui = False
        self._current_sample_name = ""
        super().__init__(main_window, app_config, r_bridge, task_runner)

    def _default_shared_params(self) -> dict:
        cfg = self.app_config
        return {
            "mode_label": "Auto mode",
            "expected_doublet_rate": cfg.doublet_expected_rate,
            "pcs": cfg.doublet_pcs,
            "pN": cfg.doublet_pn,
            "resolution": 0.5,
            "auto_pk": True,
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
        settings = self.project.analysis_settings.setdefault("doublet", self._default_settings())
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
        self.chk_same_params = QCheckBox("Use the same DoubletFinder parameters for all samples")
        self.chk_same_params.setChecked(True)
        self.chk_same_params.toggled.connect(self._on_mode_toggled)
        self.chk_skip_step = QCheckBox("Skip doublet removal (use QC objects directly downstream)")
        self.chk_skip_step.toggled.connect(self._on_skip_toggled)

        self.cmb_sample = QComboBox()
        self.cmb_sample.currentIndexChanged.connect(self._on_sample_changed)

        self.lbl_mode_tip = QLabel("Shared parameter mode: the settings below will be applied to all samples.")
        self.lbl_mode_tip.setWordWrap(True)
        self.lbl_mode_tip.setStyleSheet("color:#666; padding:4px 0;")
        self.lbl_skip_tip = QLabel("Doublet removal is enabled.")
        self.lbl_skip_tip.setWordWrap(True)
        self.lbl_skip_tip.setStyleSheet("color:#8A6D3B; padding:2px 0;")

        form_mode.addRow("", self.chk_same_params)
        form_mode.addRow("", self.chk_skip_step)
        form_mode.addRow("Current sample:", self.cmb_sample)
        form_mode.addRow("", self.lbl_mode_tip)
        form_mode.addRow("", self.lbl_skip_tip)
        layout.addWidget(grp_mode)

        grp_info = QGroupBox("Sample")
        form_info = QFormLayout(grp_info)
        self.lbl_sample_info = QLabel("Please finish the QC step first.")
        self.lbl_sample_info.setWordWrap(True)
        self.lbl_sample_info.setStyleSheet("color:#666; padding:4px;")
        form_info.addRow("", self.lbl_sample_info)
        layout.addWidget(grp_info)

        grp_params = QGroupBox("DoubletFinder Parameters")
        form = QFormLayout(grp_params)

        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Auto mode", "Advanced mode"])

        self.spn_rate = QDoubleSpinBox()
        self.spn_rate.setRange(0.001, 0.5)
        self.spn_rate.setDecimals(3)
        self.spn_rate.setSingleStep(0.005)

        self.txt_pcs = QLineEdit()

        self.spn_pn = QDoubleSpinBox()
        self.spn_pn.setRange(0.01, 0.5)
        self.spn_pn.setDecimals(2)

        self.spn_resolution = QDoubleSpinBox()
        self.spn_resolution.setRange(0.05, 3.0)
        self.spn_resolution.setDecimals(2)
        self.spn_resolution.setSingleStep(0.1)

        self.chk_auto_pk = QCheckBox("Auto-select pK")
        self.chk_auto_pk.setChecked(True)

        form.addRow("Parameter mode:", self.cmb_mode)
        form.addRow("Expected doublet rate:", self.spn_rate)
        form.addRow("PCs:", self.txt_pcs)
        form.addRow("pN:", self.spn_pn)
        form.addRow("Clustering resolution (pK sweep):", self.spn_resolution)
        form.addRow("", self.chk_auto_pk)
        layout.addWidget(grp_params)

        self.lbl_scope = QLabel("")
        self.lbl_scope.setWordWrap(True)
        self.lbl_scope.setStyleSheet("color:#1976D2; padding:2px 0 0 2px;")
        layout.addWidget(self.lbl_scope)

        self.cmb_mode.currentTextChanged.connect(self._on_params_changed)
        self.spn_rate.valueChanged.connect(self._on_params_changed)
        self.txt_pcs.textChanged.connect(self._on_params_changed)
        self.spn_pn.valueChanged.connect(self._on_params_changed)
        self.spn_resolution.valueChanged.connect(self._on_params_changed)
        self.chk_auto_pk.toggled.connect(self._on_params_changed)

        self.bind_help_refresh(
            self.chk_same_params,
            self.chk_skip_step,
            self.cmb_sample,
            self.cmb_mode,
            self.spn_rate,
            self.txt_pcs,
            self.spn_pn,
            self.spn_resolution,
            self.chk_auto_pk,
        )
        self.reset_params()
        return container

    def _capture_form_params(self) -> dict:
        return {
            "mode_label": self.cmb_mode.currentText(),
            "expected_doublet_rate": self.spn_rate.value(),
            "pcs": self.txt_pcs.text().strip(),
            "pN": self.spn_pn.value(),
            "resolution": self.spn_resolution.value(),
            "auto_pk": self.chk_auto_pk.isChecked(),
        }

    def _apply_form_params(self, params: dict):
        params = {**self._default_shared_params(), **(params or {})}
        self._updating_ui = True
        try:
            self.cmb_mode.setCurrentText(str(params["mode_label"]))
            self.spn_rate.setValue(float(params["expected_doublet_rate"]))
            self.txt_pcs.setText(str(params["pcs"]))
            self.spn_pn.setValue(float(params["pN"]))
            self.spn_resolution.setValue(float(params["resolution"]))
            self.chk_auto_pk.setChecked(bool(params["auto_pk"]))
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
            self.lbl_skip_tip.setText("Skip doublet removal is enabled. QC objects will be passed to the next step unchanged.")
        else:
            self.lbl_skip_tip.setText("Doublet removal is enabled.")
        if self.chk_same_params.isChecked():
            self.lbl_mode_tip.setText("Shared parameters: the same DoubletFinder settings are applied to all samples.")
            self.lbl_scope.setText("All samples use the shared DoubletFinder parameters.")
        else:
            sample_name = self._current_sample_name or "Sample"
            self.lbl_mode_tip.setText("Per-sample mode: switch samples to save independent DoubletFinder parameters for each sample.")
            self.lbl_scope.setText(f"Editing sample: {sample_name}. Each sample will use its own DoubletFinder parameters.")
        self.cmb_sample.setEnabled(not self.chk_same_params.isChecked())

    def _persist_settings(self):
        if not self.project or self._updating_ui:
            return
        self._save_current_sample_params()
        settings = self._settings()
        settings["mode"] = "shared" if self.chk_same_params.isChecked() else "per_sample"
        settings["skip_step"] = self.chk_skip_step.isChecked()
        self.project.analysis_settings["doublet"] = settings
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
            names = [f"{sample.name} ({sample.group})" for sample in self.project.samples]
            self.lbl_sample_info.setText(
                f"{len(names)} samples: {', '.join(names)}\nClick Run Current Step to process all samples for doublet removal."
            )
            for sample in self.project.samples:
                self.cmb_sample.addItem(f"{sample.name} ({sample.group})", sample.name)
        else:
            self.lbl_sample_info.setText("Please finish the QC step first.")
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
            "doublet",
            {
                "mode": params["mode"],
                "skip_step": params["skip_step"],
                "current_sample": params["current_sample"] or "All Samples",
                "expected_rate": current_params["expected_doublet_rate"],
                "pcs": current_params["pcs"],
                "pN": current_params["pN"],
                "resolution": current_params["resolution"],
                "auto_pk": current_params["auto_pk"],
            },
        )

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_samples()

    def on_page_entered(self):
        self._refresh_samples()
        self.refresh_help()

    def _build_samples_info(self, samples):
        settings = self._settings()
        shared_params = dict(settings["shared_params"])
        per_sample = settings["per_sample_params"]
        sample_items = []
        for sample in samples:
            qc_rds = os.path.join(self.project.cache_subdir("qc"), f"{sample.name}_qc.rds").replace("\\", "/")
            effective_params = dict(shared_params)
            if settings["mode"] == "per_sample":
                effective_params.update(per_sample.get(sample.name, {}))
            sample_items.append(
                {
                    "name": sample.name,
                    "qc_rds": qc_rds,
                    "doublet_params": effective_params,
                }
            )
        return sample_items

    def run_step(self):
        if not self.require_project():
            return

        self._persist_settings()
        self.clear_log()
        settings = self._settings()
        if settings.get("skip_step", False):
            self.append_log("=== Skip Doublet Removal ===")
            self.append_log("Doublet removal is skipped. QC objects will be passed to downstream steps unchanged.")
        else:
            self.append_log("=== Doublet Removal(DoubletFinder) ===")

        params = dict(settings["shared_params"])
        params["seed"] = self.app_config.default_seed
        params["param_mode"] = settings["mode"]
        params["skip_step"] = bool(settings.get("skip_step", False))
        params["per_sample_params"] = settings["per_sample_params"]
        params["samples"] = self._build_samples_info(self.project.samples)
        params["cache_dir"] = self.project.cache_subdir("doublet").replace("\\", "/")

        self.register_task_owner()
        self.task_runner.run_r_script(
            script_name="03_doublet_passthrough.R" if settings.get("skip_step", False) else "03_doublet.R",
            params=params,
            output_dir=self.project.cache_subdir("doublet"),
            step_name="Skip Doublet Removal" if settings.get("skip_step", False) else "Doublet Removal",
        )
        self.project.step_status["doublet"] = "running"
        idx = self.main_window.get_step_index("doublet")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "running")

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        skipped = bool(summary.get("skipped", False))
        if skipped:
            self.append_log("=== Doublet Removal Skipped ===")
            self.append_log("Downstream analysis will use data before doublet removal.")
        else:
            self.append_log("=== Doublet Removal Finished ===")
        self.project.step_status["doublet"] = "done"
        idx = self.main_window.get_step_index("doublet")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

        if "sample_stats" in summary:
            stats = summary["sample_stats"]
            headers = ["Sample", "Before", "After", "Doublets", "Doublet rate"]
            data = [
                [
                    item.get("name", ""),
                    str(item.get("before", "")),
                    str(item.get("after", "")),
                    str(item.get("doublets", "")),
                    item.get("doublet_rate", ""),
                ]
                for item in stats
            ]
            self.set_result_table(data, headers)
            self.main_window.show_preview_table(data, headers, "Doublet Statistics")

        figures = getattr(result, "figures", summary.get("figures", []))
        cache_dir = self.project.cache_subdir("doublet")
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache_dir, fig)
            if os.path.isfile(fig_path):
                name = os.path.splitext(os.path.basename(fig_path))[0]
                self.main_window.add_preview_item(name=name, path=fig_path, item_type="figure", step="Doublet")

        self.main_window.project_manager.save_project(self.project)

    def on_step_error(self, step, summary, detail):
        QMessageBox.warning(self, "Doublet Removal Failed", summary)

    def preview(self):
        if not self.require_project():
            return
        if not self.project.samples:
            QMessageBox.warning(self, "Notice", "Please add samples before previewing doublet results.")
            return
        idx = self.cmb_sample.currentIndex()
        if idx < 0:
            idx = 0
        sample = self.project.samples[idx]
        self._persist_settings()
        self.append_log(f"Sample: {sample.name}")

        settings = self._settings()
        params = dict(settings["shared_params"])
        params["seed"] = self.app_config.default_seed
        params["param_mode"] = settings["mode"]
        params["skip_step"] = bool(settings.get("skip_step", False))
        params["per_sample_params"] = settings["per_sample_params"]
        params["samples"] = self._build_samples_info([sample])
        params["cache_dir"] = self.project.cache_subdir("doublet").replace("\\", "/")
        params["preview_only"] = True

        self.register_task_owner()
        self.task_runner.run_r_script(
            script_name="03_doublet.R",
            params=params,
            output_dir=self.project.cache_subdir("doublet"),
            step_name="Doublet Removal",
        )
