from __future__ import annotations

import csv
import json
import os
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


class GSEAStandalonePage(BasePage):
    STEP_ID = "gsea"
    STEP_NAME = "⑨ GSEA Enrichment"

    def __init__(self, main_window, app_config, r_bridge, task_runner):
        self.current_deg_full_csv = ""
        self.current_comparison_name = ""
        self.current_gsea_results_csv = ""
        self.current_gsea_context_rds = ""
        self.available_pathways: list[str] = []
        super().__init__(main_window, app_config, r_bridge, task_runner)

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp1 = QGroupBox("Step 1 - DEG Results")
        f1 = QFormLayout(grp1)
        self.cmb_deg_result = QComboBox()
        self.btn_refresh_deg = QPushButton(" DEG Lists")
        self.btn_refresh_deg.clicked.connect(self._refresh_deg_results)
        row_deg = QHBoxLayout()
        row_deg.addWidget(self.cmb_deg_result, 1)
        row_deg.addWidget(self.btn_refresh_deg)
        wrap_deg = QWidget()
        wrap_deg.setLayout(row_deg)
        f1.addRow("DEG Results:", wrap_deg)
        self.lbl_deg_hint = QLabel(" 8 finished, Load cache/deg deg_results_full_*.csv Results.")
        self.lbl_deg_hint.setWordWrap(True)
        self.lbl_deg_hint.setStyleSheet("color:#666; font-size:11px;")
        f1.addRow("", self.lbl_deg_hint)
        layout.addWidget(grp1)

        grp2 = QGroupBox("Step 2 - GMT file")
        f2 = QFormLayout(grp2)
        self.edit_gmt = QLineEdit()
        self.edit_gmt.setPlaceholderText("Please select.gmt file")
        self.btn_browse_gmt = QPushButton("Browse...")
        self.btn_browse_gmt.clicked.connect(self._browse_gmt)
        row_gmt = QHBoxLayout()
        row_gmt.addWidget(self.edit_gmt, 1)
        row_gmt.addWidget(self.btn_browse_gmt)
        wrap_gmt = QWidget()
        wrap_gmt.setLayout(row_gmt)
        f2.addRow("GMT file:", wrap_gmt)
        layout.addWidget(grp2)

        grp3 = QGroupBox("Step 3 - GSEA Parameters")
        f3 = QFormLayout(grp3)
        self.spn_gsea_topn = QSpinBox()
        self.spn_gsea_topn.setRange(3, 50)
        self.spn_gsea_topn.setValue(10)
        f3.addRow("Top pathways for bubble plot:", self.spn_gsea_topn)

        self.spn_gsea_min_size = QSpinBox()
        self.spn_gsea_min_size.setRange(5, 500)
        self.spn_gsea_min_size.setValue(10)
        f3.addRow("Minimum genes per pathway:", self.spn_gsea_min_size)

        self.spn_gsea_max_size = QSpinBox()
        self.spn_gsea_max_size.setRange(20, 5000)
        self.spn_gsea_max_size.setValue(500)
        f3.addRow("Maximum genes per pathway:", self.spn_gsea_max_size)
        layout.addWidget(grp3)

        grp4 = QGroupBox("Step 4 - Single Pathway")
        f4 = QFormLayout(grp4)
        self.btn_run_gsea = QPushButton("▶ GSEA")
        self.btn_run_gsea.setProperty("role", "primary")
        self.btn_run_gsea.clicked.connect(self._run_gsea)
        f4.addRow("", self.btn_run_gsea)

        path_wrap = QWidget()
        path_layout = QHBoxLayout(path_wrap)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.edit_gsea_search = QLineEdit()
        self.edit_gsea_search.setPlaceholderText("pathway")
        self.edit_gsea_search.textChanged.connect(self._filter_pathways)
        self.cmb_gsea_pathway = QComboBox()
        self.cmb_gsea_pathway.setMinimumWidth(280)
        self.btn_plot_pathway = QPushButton("Single Pathway")
        self.btn_plot_pathway.clicked.connect(self._plot_selected_pathway)
        path_layout.addWidget(self.edit_gsea_search, 1)
        path_layout.addWidget(self.cmb_gsea_pathway, 1)
        path_layout.addWidget(self.btn_plot_pathway)
        f4.addRow("Single Pathway:", path_wrap)

        self.lbl_gsea_status = QLabel("GSEA has not been run yet.")
        self.lbl_gsea_status.setWordWrap(True)
        self.lbl_gsea_status.setStyleSheet("color:#666;")
        f4.addRow("", self.lbl_gsea_status)

        self.btn_export_gsea_csv = QPushButton("Export GSEA CSV")
        self.btn_export_gsea_csv.clicked.connect(self._export_current_gsea_csv)
        f4.addRow("", self.btn_export_gsea_csv)
        layout.addWidget(grp4)

        self.gsea_table = QTableWidget()
        self.gsea_table.setColumnCount(5)
        self.gsea_table.setHorizontalHeaderLabels(["Pathway", "NES", "padj", "pval", ""])
        self.gsea_table.horizontalHeader().setStretchLastSection(True)
        self.gsea_table.setMaximumHeight(240)
        layout.addWidget(self.gsea_table)

        self.bind_help_refresh(
            self.cmb_deg_result,
            self.edit_gmt,
            self.spn_gsea_topn,
            self.spn_gsea_min_size,
            self.spn_gsea_max_size,
            self.edit_gsea_search,
        )
        return container

    def _gsea_cache_dir(self) -> str:
        return self.project.cache_subdir("gsea") if self.project else ""

    def _deg_cache_dir(self) -> str:
        return self.project.cache_subdir("deg") if self.project else ""

    def _gsea_config_path(self) -> str:
        return os.path.join(self._gsea_cache_dir(), "gsea_config.json")

    def _deg_context_path(self) -> str:
        return os.path.join(self._deg_cache_dir(), "deg_context.json")

    def _write_json(self, path: str, data: dict[str, Any]):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def _read_json(self, path: str) -> dict[str, Any]:
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def get_params(self) -> dict:
        return {
            "deg_result": self.cmb_deg_result.currentText(),
            "gmt_file": self.edit_gmt.text().strip(),
            "gsea_topn": self.spn_gsea_topn.value(),
            "gsea_min_size": self.spn_gsea_min_size.value(),
            "gsea_max_size": self.spn_gsea_max_size.value(),
            "seed": self.app_config.default_seed,
        }

    def reset_params(self):
        self.edit_gmt.clear()
        self.spn_gsea_topn.setValue(10)
        self.spn_gsea_min_size.setValue(10)
        self.spn_gsea_max_size.setValue(500)
        self.edit_gsea_search.clear()
        self._refresh_deg_results()
        self._clear_gsea_results_table()

    def get_help_html(self) -> str:
        return build_step_help("gsea", {
            "deg_result": self.cmb_deg_result.currentText() or "Not selected",
            "gmt_file": self.edit_gmt.text().strip() or "Not selected",
            "gsea_topn": self.spn_gsea_topn.value(),
            "gsea_min_size": self.spn_gsea_min_size.value(),
            "gsea_max_size": self.spn_gsea_max_size.value(),
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._load_gsea_config()
        self._refresh_deg_results()
        self._restore_gsea_context()
        self.refresh_help()

    def on_page_entered(self):
        self._load_gsea_config()
        self._refresh_deg_results()
        self._restore_gsea_context()
        self.refresh_help()

    def _load_deg_options(self) -> list[tuple[str, str]]:
        if not self.project:
            return []
        items: list[tuple[str, str]] = []
        seen: set[str] = set()

        for entry in sorted(getattr(self.project, "deg_results", []) or [], key=lambda item: (str(item.get("created_at", "")), str(item.get("result_id", "")))):
            rel_dir = str(entry.get("cache_dir_rel", "") or "").replace("/", os.sep)
            if not rel_dir:
                continue
            abs_dir = os.path.join(self.project.directory, rel_dir)
            if not os.path.isdir(abs_dir):
                continue
            for name in sorted(os.listdir(abs_dir)):
                if name.endswith('.csv') and name.startswith('deg_results_full_'):
                    full_path = os.path.join(abs_dir, name)
                    if full_path not in seen:
                        label = str(entry.get('display_name', '') or entry.get('result_id', '') or name.replace('deg_results_full_', '').replace('.csv', ''))
                        items.append((label, full_path))
                        seen.add(full_path)
                    break

        cache = self._deg_cache_dir()
        for root, _dirs, files in os.walk(cache):
            for name in sorted(files):
                if name.endswith('.csv') and (name.startswith('deg_results_full_') or name.startswith('DEG_full_')):
                    full_path = os.path.join(root, name)
                    if full_path in seen:
                        continue
                    label = os.path.relpath(full_path, cache).replace('deg_results_full_', '').replace('DEG_full_', '').replace('.csv', '')
                    items.append((label, full_path))
                    seen.add(full_path)
        return items

    def _refresh_deg_results(self):
        if not self.project:
            return
        current_path = self.current_deg_full_csv or self.cmb_deg_result.currentData()
        options = self._load_deg_options()
        self.cmb_deg_result.clear()
        for label, path in options:
            self.cmb_deg_result.addItem(label, path)
        if current_path:
            idx = self.cmb_deg_result.findData(current_path)
            if idx >= 0:
                self.cmb_deg_result.setCurrentIndex(idx)
        if self.cmb_deg_result.count() == 0:
            self.cmb_deg_result.addItem("No available DEG result", "")
        self.refresh_help()

    def _save_gsea_config(self):
        if not self.project:
            return
        self._write_json(self._gsea_config_path(), {
            "gmt_file": self.edit_gmt.text().strip(),
            "top_n": self.spn_gsea_topn.value(),
            "min_size": self.spn_gsea_min_size.value(),
            "max_size": self.spn_gsea_max_size.value(),
        })

    def _load_gsea_config(self):
        if not self.project:
            return
        data = self._read_json(self._gsea_config_path())
        if data.get("gmt_file"):
            self.edit_gmt.setText(str(data["gmt_file"]))
        if data.get("top_n"):
            self.spn_gsea_topn.setValue(int(data["top_n"]))
        if data.get("min_size"):
            self.spn_gsea_min_size.setValue(int(data["min_size"]))
        if data.get("max_size"):
            self.spn_gsea_max_size.setValue(int(data["max_size"]))

    def _save_gsea_context(self):
        if not self.project:
            return
        self._write_json(os.path.join(self._gsea_cache_dir(), "gsea_context.json"), {
            "comparison_name": self.current_comparison_name,
            "deg_full_csv": self.current_deg_full_csv,
            "gsea_results_csv": self.current_gsea_results_csv,
            "gsea_context_rds": self.current_gsea_context_rds,
        })

    def _restore_gsea_context(self):
        if not self.project:
            return
        deg_data = self._read_json(self._deg_context_path())
        self.current_comparison_name = str(deg_data.get("comparison_name", ""))
        self.current_deg_full_csv = str(deg_data.get("deg_full_csv", ""))
        if self.current_deg_full_csv:
            idx = self.cmb_deg_result.findData(self.current_deg_full_csv)
            if idx >= 0:
                self.cmb_deg_result.setCurrentIndex(idx)

        gsea_data = self._read_json(os.path.join(self._gsea_cache_dir(), "gsea_context.json"))
        self.current_gsea_results_csv = str(gsea_data.get("gsea_results_csv", ""))
        self.current_gsea_context_rds = str(gsea_data.get("gsea_context_rds", ""))
        if self.current_gsea_results_csv and os.path.isfile(self.current_gsea_results_csv):
            self._load_gsea_results_table(self.current_gsea_results_csv)
        else:
            self._clear_gsea_results_table()

    def _browse_gmt(self):
        path, _ = QFileDialog.getOpenFileName(self, " GMT file", "", "GMT Files (*.gmt);;All Files (*)")
        if not path:
            return
        self.edit_gmt.setText(path)
        self._save_gsea_config()
        self.refresh_help()

    def _selected_deg_csv(self) -> str:
        path = str(self.cmb_deg_result.currentData() or "")
        if path and os.path.isfile(path):
            return path
        return ""

    def _run_gsea(self):
        if not self.require_project():
            return

        gmt_file = self.edit_gmt.text().strip()
        if not gmt_file:
            QMessageBox.warning(self, "Notice", " GMT file.")
            return
        if not os.path.isfile(gmt_file):
            QMessageBox.warning(self, "Notice", "Selected GMT file does not exist,.")
            return
        if not gmt_file.lower().endswith(".gmt"):
            QMessageBox.warning(self, "Notice", "Please select a .gmt pathway file.")
            return

        deg_csv = self._selected_deg_csv()
        if not deg_csv:
            QMessageBox.warning(self, "Notice", "No current DEG Results.finished 8 Differential Expression.")
            return

        comparison = (
            self.cmb_deg_result.currentText().strip()
            or os.path.basename(deg_csv).replace("deg_results_full_", "").replace("DEG_full_", "").replace(".csv", "")
        )
        self.current_comparison_name = comparison
        self.current_deg_full_csv = deg_csv
        self._save_gsea_config()
        self.main_window.preview_panel.clear_items("GSEA")
        self.append_log(f"=== GSEA: {comparison} ===")

        params = {
            "action": "run_gsea",
            "deg_csv": deg_csv.replace("\\", "/"),
            "comparison_name": comparison,
            "gmt_file": gmt_file.replace("\\", "/"),
            "top_n": self.spn_gsea_topn.value(),
            "min_size": self.spn_gsea_min_size.value(),
            "max_size": self.spn_gsea_max_size.value(),
            "seed": self.app_config.default_seed,
            "cache_dir": self._gsea_cache_dir().replace("\\", "/"),
        }
        self.register_task_owner()
        self.task_runner.run_r_script("07_gsea.R", params, self._gsea_cache_dir(), "GSEA")

    def _plot_selected_pathway(self):
        if not self.require_project():
            return

        pathway_name = self.cmb_gsea_pathway.currentText().strip()
        if not pathway_name:
            QMessageBox.warning(self, "Notice", "Please select a pathway.")
            return
        if not self.current_gsea_context_rds or not os.path.isfile(self.current_gsea_context_rds):
            QMessageBox.warning(self, "Notice", "No current GSEA, GSEA.")
            return

        params = {
            "action": "plot_pathway",
            "context_rds": self.current_gsea_context_rds.replace("\\", "/"),
            "pathway_name": pathway_name,
            "comparison_name": self.current_comparison_name,
            "cache_dir": self._gsea_cache_dir().replace("\\", "/"),
        }
        self.register_task_owner()
        self.task_runner.run_r_script("07_gsea.R", params, self._gsea_cache_dir(), "GSEA Single Pathway")

    def _export_current_gsea_csv(self):
        if not self.current_gsea_results_csv or not os.path.isfile(self.current_gsea_results_csv):
            QMessageBox.information(self, "Notice", "No GSEA result is available for export.")
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Export GSEA Results", os.path.basename(self.current_gsea_results_csv), "CSV (*.csv)")
        if not out_path:
            return
        if not out_path.lower().endswith(".csv"):
            out_path += ".csv"
        import shutil
        shutil.copy2(self.current_gsea_results_csv, out_path)
        QMessageBox.information(self, "finished", f"exported:\n{out_path}")

    def run_step(self):
        self._run_gsea()

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        action = summary.get("action", "")
        if action == "plot_pathway":
            self._handle_gsea_pathway_finished(result, summary)
            return
        self._handle_gsea_finished(result, summary)

    def _handle_gsea_finished(self, result, summary: dict[str, Any]):
        cache = self._gsea_cache_dir()
        comparison = str(summary.get("comparison_name", self.current_comparison_name))
        self.current_comparison_name = comparison
        self.current_gsea_results_csv = str(summary.get("results_csv", ""))
        if self.current_gsea_results_csv and not os.path.isabs(self.current_gsea_results_csv):
            self.current_gsea_results_csv = os.path.join(cache, self.current_gsea_results_csv)

        self.current_gsea_context_rds = str(summary.get("context_rds", ""))
        if self.current_gsea_context_rds and not os.path.isabs(self.current_gsea_context_rds):
            self.current_gsea_context_rds = os.path.join(cache, self.current_gsea_context_rds)

        top_pathway = str(summary.get("top_pathway", ""))
        n_pathways = summary.get("n_pathways", 0)
        self.append_log(f"=== GSEA finished: {comparison} (Pathway={n_pathways}) ===")

        figures = getattr(result, "figures", None) or summary.get("figures", [])
        if isinstance(figures, str):
            figures = [figures]
        bubble_positive_path = ""
        top_path_fig = ""
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache, fig)
            if os.path.isfile(fig_path):
                name = os.path.splitext(os.path.basename(fig_path))[0]
                self.main_window.add_preview_item(name, fig_path, "figure", "GSEA")
                if name.startswith("gsea_bubble_positive_"):
                    bubble_positive_path = fig_path
                if name.startswith("gsea_pathway_top_"):
                    top_path_fig = fig_path

        tables = summary.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        for tbl in tables:
            tbl_path = tbl if os.path.isabs(tbl) else os.path.join(cache, tbl)
            if os.path.isfile(tbl_path):
                name = os.path.splitext(os.path.basename(tbl_path))[0]
                self.main_window.add_preview_item(name, tbl_path, "table", "GSEA")

        pathways = summary.get("pathways", []) or []
        if isinstance(pathways, str):
            pathways = [pathways]
        self.available_pathways = [str(x) for x in pathways]
        self._filter_pathways()
        if top_pathway:
            idx = self.cmb_gsea_pathway.findText(top_pathway)
            if idx >= 0:
                self.cmb_gsea_pathway.setCurrentIndex(idx)

        if self.current_gsea_results_csv and os.path.isfile(self.current_gsea_results_csv):
            self._load_gsea_results_table(self.current_gsea_results_csv)
        else:
            self._clear_gsea_results_table()

        if top_path_fig:
            self.main_window.show_preview_image(top_path_fig, f"GSEA Single Pathway - {top_pathway}")
        elif bubble_positive_path:
            self.main_window.show_preview_image(bubble_positive_path, f"GSEA Bubble Plot - {comparison}")

        self.lbl_gsea_status.setText(f"GSEA completed: {comparison}. Bubble plots were added to preview results; single-pathway plots can be generated separately.")
        self.lbl_gsea_status.setStyleSheet("color:#2E7D32; font-weight:600;")
        self._save_gsea_context()
        self.project.step_status["gsea"] = "done"
        idx = self.main_window.get_step_index("gsea")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

    def _handle_gsea_pathway_finished(self, result, summary: dict[str, Any]):
        cache = self._gsea_cache_dir()
        pathway_name = str(summary.get("pathway_name", ""))
        figures = getattr(result, "figures", None) or summary.get("figures", [])
        if isinstance(figures, str):
            figures = [figures]

        latest_fig = ""
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache, fig)
            if os.path.isfile(fig_path):
                name = os.path.splitext(os.path.basename(fig_path))[0]
                self.main_window.add_preview_item(name, fig_path, "figure", "GSEA")
                latest_fig = fig_path

        if latest_fig:
            self.main_window.show_preview_image(latest_fig, f"GSEA Single Pathway - {pathway_name}")

        self.lbl_gsea_status.setText(f"Updated single pathway: {pathway_name}")
        self.lbl_gsea_status.setStyleSheet("color:#2E7D32; font-weight:600;")
        self.append_log(f"=== GSEA single-pathway plot updated: {pathway_name} ===")

    def _load_gsea_results_table(self, csv_path: str):
        rows = []
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(row)

        self.available_pathways = [str(row.get("pathway", "")) for row in rows if row.get("pathway")]
        self._filter_pathways()
        rows = rows[: min(len(rows), 30)]
        self.gsea_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row.get("pathway", ""),
                row.get("NES", ""),
                row.get("padj", ""),
                row.get("pval", ""),
                row.get("size", ""),
            ]
            for c, value in enumerate(values):
                self.gsea_table.setItem(r, c, QTableWidgetItem(str(value)))

    def _clear_gsea_results_table(self):
        self.gsea_table.clearContents()
        self.gsea_table.setRowCount(0)
        self.available_pathways = []
        self.cmb_gsea_pathway.clear()

    def _filter_pathways(self):
        keyword = self.edit_gsea_search.text().strip().lower()
        self.cmb_gsea_pathway.clear()
        if keyword:
            filtered = [p for p in self.available_pathways if keyword in p.lower()]
        else:
            filtered = list(self.available_pathways)
        self.cmb_gsea_pathway.addItems(filtered[:500])

    def on_step_error(self, step, summary, detail):
        QMessageBox.warning(self, "GSEA Failed", summary)
