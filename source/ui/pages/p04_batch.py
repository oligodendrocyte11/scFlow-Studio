from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


class BatchCorrectionPage(BasePage):
    STEP_ID = "batch"
    STEP_NAME = "④ Batch Correction"

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp_main = QGroupBox("Settings")
        form = QFormLayout(grp_main)

        self.chk_enable = QCheckBox("Enable batch correction")
        self.chk_enable.setChecked(False)
        self.chk_enable.toggled.connect(self._sync_ui_state)

        self.cmb_batch_key = QComboBox()
        self.cmb_batch_key.addItems(["sample", "group"])

        self.cmb_method = QComboBox()
        self.cmb_method.addItems(["RPCA (Recommended)", "Harmony", "CCA"])

        self.lst_samples = QListWidget()
        self.lst_samples.setMaximumHeight(140)

        self.lbl_hint = QLabel(
            "Enable this step only when batch correction is needed. "
            "Use sample or group as the batch column depending on your experimental design."
        )
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color:#5F6B7A; font-size:11px;")

        self.lbl_status = QLabel("Not run yet.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#666;")

        self.btn_run_batch = QPushButton("Run / Save Batch Correction")
        self.btn_run_batch.setProperty("role", "primary")
        self.btn_run_batch.clicked.connect(self.run_step)

        form.addRow("Batch correction:", self.chk_enable)
        form.addRow("Batch field:", self.cmb_batch_key)
        form.addRow("Integration method:", self.cmb_method)
        form.addRow("Project samples:", self.lst_samples)
        form.addRow("", self.lbl_hint)
        form.addRow("", self.btn_run_batch)
        form.addRow("", self.lbl_status)
        layout.addWidget(grp_main)

        grp_note = QGroupBox("Help")
        note_layout = QVBoxLayout(grp_note)
        note = QLabel(
            "Batch correction is optional. Choose a batch key and an integration method when correction is required.\n"
            "If disabled, the workflow passes objects through unchanged for downstream clustering."
        )
        note.setWordWrap(True)
        note_layout.addWidget(note)
        layout.addWidget(grp_note)

        self.bind_help_refresh(self.chk_enable, self.cmb_batch_key, self.cmb_method)
        self._sync_ui_state()
        return container

    def _sync_ui_state(self):
        enabled = self.chk_enable.isChecked()
        self.cmb_batch_key.setEnabled(enabled)
        self.cmb_method.setEnabled(enabled)
        self.refresh_help()

    def _refresh_samples(self):
        self.lst_samples.clear()
        if not self.project or not self.project.samples:
            self.lst_samples.addItem("Sample")
            return
        for sample in self.project.samples:
            self.lst_samples.addItem(f"{sample.name}  |  group={sample.group}")

    def _config_path(self) -> str:
        return os.path.join(self.project.cache_subdir("batch"), "batch_config.json")

    def get_params(self) -> dict:
        return {
            "batch_enabled": self.chk_enable.isChecked(),
            "batch_key": self.cmb_batch_key.currentText(),
            "batch_method": self.cmb_method.currentText(),
            "seed": self.app_config.default_seed,
        }

    def reset_params(self):
        self.chk_enable.setChecked(False)
        self.cmb_batch_key.setCurrentText("sample")
        self.cmb_method.setCurrentIndex(0)
        self.lbl_status.setText("Not run yet.")
        self.lbl_status.setStyleSheet("color:#666;")
        self._sync_ui_state()

    def get_help_html(self) -> str:
        return build_step_help("batch", {
            "batch_enabled": self.chk_enable.isChecked(),
            "batch_key": self.cmb_batch_key.currentText(),
            "batch_method": self.cmb_method.currentText(),
            "sample_count": len(self.project.samples) if self.project and self.project.samples else 0,
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_samples()
        self._load_saved_config()
        self.refresh_help()

    def on_page_entered(self):
        self._refresh_samples()
        self._load_saved_config()
        self.refresh_help()

    def _load_saved_config(self):
        if not self.project:
            return
        path = self._config_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.chk_enable.setChecked(bool(data.get("batch_enabled", False)))
            batch_key = data.get("batch_key", "sample")
            method = data.get("batch_method", "RPCA (Recommended)")
            if self.cmb_batch_key.findText(batch_key) >= 0:
                self.cmb_batch_key.setCurrentText(batch_key)
            if self.cmb_method.findText(method) >= 0:
                self.cmb_method.setCurrentText(method)
        except Exception:
            pass
        self._sync_ui_state()

    def run_step(self):
        if not self.require_project():
            return
        if not self.project.samples:
            QMessageBox.warning(self, "Notice", "Please add project samples first.")
            return

        self.clear_log()
        self.append_log("=== Batch Correction Preview ===")
        params = self.get_params()
        self.append_log(f"batch_enabled = {str(params['batch_enabled']).lower()}")
        if not params["batch_enabled"]:
            self.append_log("Batch correction is disabled.")
            self.append_log("Batch correction is skipped; integration methods such as RPCA, Harmony, or CCA will not be run.")
            self.append_log("Pass-through mode finished. Downstream clustering will use the uncorrected merged data.")

        samples_rds = []
        missing = []
        for sample in self.project.samples:
            rds_path = os.path.join(self.project.cache_subdir("doublet"), f"{sample.name}_singlet.rds").replace("\\", "/")
            if not os.path.isfile(rds_path):
                missing.append(sample.name)
            samples_rds.append({
                "name": sample.name,
                "group": sample.group,
                "rds_path": rds_path,
            })
        if missing:
            QMessageBox.warning(
                self,
                "Notice",
                "Missing singlet objects for samples:\n"
                + "\n".join(missing),
            )
            return

        params["samples"] = samples_rds
        params["cache_dir"] = self.project.cache_subdir("batch").replace("\\", "/")

        self.task_runner.run_r_script(
            script_name="04_batch.R",
            params=params,
            output_dir=self.project.cache_subdir("batch"),
            step_name="Batch Correction",
        )
        self.project.step_status["batch"] = "running"
        idx = self.main_window.get_step_index("batch")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "running")

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        self.append_log("=== Batch correction step finished ===")

        enabled = bool(summary.get("batch_enabled", False))
        requested = bool(summary.get("batch_requested", self.chk_enable.isChecked()))
        batch_status = str(summary.get("batch_status", "enabled" if enabled else "skipped"))
        batch_message = str(summary.get("batch_message", ""))
        batch_key = summary.get("batch_key", self.cmb_batch_key.currentText())
        method = summary.get("batch_method", self.cmb_method.currentText())
        batch_units = summary.get("batch_units", [])
        if isinstance(batch_units, str):
            batch_units = [batch_units]

        headers = ["Item", "Value"]
        data = [
            ["Requested", "yes" if requested else "no"],
            ["Enabled", "yes" if enabled else "no"],
            ["Step status", batch_status],
            ["Batch column", batch_key],
            ["Integration method", method],
            ["Samples", summary.get("n_samples", "")],
            ["Batch units", summary.get("n_batches", "")],
            ["Cells", summary.get("n_cells", "")],
            ["Batch labels", ", ".join([str(x) for x in batch_units])],
            ["Help", batch_message],
        ]
        self.set_result_table(data, headers)

        figures = getattr(result, "figures", None) or []
        if isinstance(figures, str):
            figures = [figures]
        if not figures:
            summary_figures = summary.get("figures", [])
            if isinstance(summary_figures, str):
                summary_figures = [summary_figures]
            cache = self.project.cache_subdir("batch")
            figures = [os.path.join(cache, fig) for fig in summary_figures if isinstance(fig, str)]

        group_compare_path = ""
        compare_path = ""
        sample_compare_path = ""
        for fig in figures:
            figure_path = fig if os.path.isabs(fig) else os.path.join(self.project.cache_subdir("batch"), fig)
            if os.path.isfile(figure_path):
                name = os.path.splitext(os.path.basename(figure_path))[0]
                self.main_window.add_preview_item(name, figure_path, "figure", "Batch")
                if name == "batch_group_compare":
                    group_compare_path = figure_path
                elif name == "batch_compare":
                    compare_path = figure_path
                elif name == "batch_sample_compare":
                    sample_compare_path = figure_path
        if group_compare_path:
            title = "Batch Correction (Group)"
            if batch_status != "enabled":
                title = "Batch correction is disabled (group preview)"
            self.main_window.show_preview_image(group_compare_path, title)
        elif compare_path:
            title = "Batch Correction"
            if batch_status != "enabled":
                title = "Batch correction is disabled"
            self.main_window.show_preview_image(compare_path, title)
        elif sample_compare_path:
            title = "Batch Correction (Sample)"
            if batch_status != "enabled":
                title = "Batch correction is disabled (sample preview)"
            self.main_window.show_preview_image(sample_compare_path, title)

        self.project.step_status["batch"] = "done"
        idx = self.main_window.get_step_index("batch")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

        if enabled:
            self.append_log("batch_enabled = true")
            self.append_log("Batch correction has been performed.")
            self.lbl_status.setText(f"Saved: {batch_key} / {method}")
            self.lbl_status.setStyleSheet("color:#2E7D32; font-weight:600;")
        else:
            self.append_log("batch_enabled = false")
            self.append_log("Skipping batch correction.")
            self.append_log("Current step completed (skipped / pass-through).")
            self.lbl_status.setText("Batch correction is disabled. This step completed in pass-through mode; clustering can continue.")
            self.lbl_status.setStyleSheet("color:#1565C0; font-weight:600;")

    def on_step_error(self, step, summary, detail):
        self.lbl_status.setText(f"Batch correction failed: {summary}")
        self.lbl_status.setStyleSheet("color:#C62828; font-weight:600;")
