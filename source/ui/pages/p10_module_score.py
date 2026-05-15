from __future__ import annotations

import csv
import json
import os

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
    QVBoxLayout,
    QWidget,
)

from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


def read_gmt_pathways(path: str) -> list[str]:
    pathways: list[str] = []
    if not path or not os.path.isfile(path):
        return pathways
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.rstrip("\n\r").split("\t")
            if len(parts) >= 3 and parts[0].strip():
                pathways.append(parts[0].strip())
    return pathways


class ModuleScorePage(BasePage):
    STEP_ID = "module_score"
    STEP_NAME = "⑪ Gene Set Scoring"

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp1 = QGroupBox("Step 1 - Select Object")
        f1 = QFormLayout(grp1)
        self.cmb_object = QComboBox()
        self.cmb_object.currentIndexChanged.connect(self._on_object_changed)
        self.cmb_label_col = QComboBox()
        self.cmb_label_col.currentIndexChanged.connect(lambda _idx: self._refresh_compare_options())
        f1.addRow("Object:", self.cmb_object)
        f1.addRow("Group:", self.cmb_label_col)
        layout.addWidget(grp1)

        grp2 = QGroupBox("Step 2 - Gene Set Input")
        f2 = QFormLayout(grp2)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("GMT Pathway", "gmt")
        self.cmb_mode.addItem("Custom genes", "custom")
        self.cmb_mode.currentIndexChanged.connect(self._update_mode_ui)
        f2.addRow("Input mode:", self.cmb_mode)

        gmt_row = QHBoxLayout()
        self.edit_gmt = QLineEdit()
        self.edit_gmt.setPlaceholderText("Select a GMT file...")
        self.btn_browse_gmt = QPushButton("Browse...")
        self.btn_browse_gmt.clicked.connect(self._browse_gmt)
        gmt_row.addWidget(self.edit_gmt, 1)
        gmt_row.addWidget(self.btn_browse_gmt)
        gmt_wrap = QWidget()
        gmt_wrap.setLayout(gmt_row)
        self.cmb_gmt_pathway = QComboBox()
        self.cmb_gmt_pathway.setEditable(False)
        f2.addRow("GMT file:", gmt_wrap)
        f2.addRow("Select Pathway:", self.cmb_gmt_pathway)

        custom_row = QHBoxLayout()
        self.edit_gene_set = QLineEdit()
        self.edit_gene_set.setPlaceholderText("Select a custom gene-set CSV/TXT file...")
        self.btn_browse_gene_set = QPushButton("Browse...")
        self.btn_browse_gene_set.clicked.connect(self._browse_gene_set)
        custom_row.addWidget(self.edit_gene_set, 1)
        custom_row.addWidget(self.btn_browse_gene_set)
        custom_wrap = QWidget()
        custom_wrap.setLayout(custom_row)
        f2.addRow("Gene Set File:", custom_wrap)

        template_row = QHBoxLayout()
        self.btn_download_template = QPushButton(" CSV ")
        self.btn_download_template.clicked.connect(self._download_template)
        self.lbl_template_hint = QLabel(" gene, genes.")
        self.lbl_template_hint.setWordWrap(True)
        self.lbl_template_hint.setStyleSheet("color:#666; font-size:11px;")
        template_row.addWidget(self.btn_download_template)
        template_row.addWidget(self.lbl_template_hint, 1)
        template_wrap = QWidget()
        template_wrap.setLayout(template_row)
        f2.addRow("Help:", template_wrap)

        self.lbl_input_hint = QLabel("Use a GMT pathway or a TXT/CSV gene list.")
        self.lbl_input_hint.setWordWrap(True)
        self.lbl_input_hint.setStyleSheet("color:#666; font-size:11px;")
        f2.addRow("", self.lbl_input_hint)
        layout.addWidget(grp2)

        grp3 = QGroupBox("Step 3 - Comparison")
        f3 = QFormLayout(grp3)
        self.cmb_compare_mode = QComboBox()
        self.cmb_compare_mode.addItem("Visualization only", "basic")
        self.cmb_compare_mode.addItem("Two-group comparison", "overall_group")
        self.cmb_compare_mode.addItem("Cell Type/Subcluster", "within_label")
        self.cmb_compare_mode.addItem("Cross-group + cross-cell-type comparison", "cross_label")
        self.cmb_compare_mode.currentIndexChanged.connect(self._update_compare_ui)
        self.cmb_group1 = QComboBox()
        self.cmb_group1.setEditable(True)
        self.cmb_group2 = QComboBox()
        self.cmb_group2.setEditable(True)
        self.cmb_target_label = QComboBox()
        self.cmb_target_label.setEditable(True)
        self.cmb_stat_method = QComboBox()
        self.cmb_stat_method.addItems(["wilcox", "t", "bimod"])
        self.cmb_stat_method.setCurrentText("wilcox")
        f3.addRow("Comparison Mode:", self.cmb_compare_mode)
        f3.addRow("Group 1:", self.cmb_group1)
        f3.addRow("Group 2:", self.cmb_group2)
        f3.addRow("Target cell type/Subcluster 1:", self.cmb_target_label)
        self.cmb_target_label_2 = QComboBox()
        self.cmb_target_label_2.setEditable(True)
        f3.addRow("Target cell type/Subcluster 2:", self.cmb_target_label_2)
        f3.addRow("Statistical Method:", self.cmb_stat_method)
        self.lbl_compare_hint = QLabel("Choose a comparison mode to generate statistical results.")
        self.lbl_compare_hint.setWordWrap(True)
        self.lbl_compare_hint.setStyleSheet("color:#666; font-size:11px;")
        f3.addRow("", self.lbl_compare_hint)
        layout.addWidget(grp3)

        grp4 = QGroupBox("Step 4 - Run Analysis")
        f4 = QFormLayout(grp4)
        self.btn_run_score = QPushButton("Start Gene Set Scoring")
        self.btn_run_score.setProperty("role", "primary")
        self.btn_run_score.clicked.connect(self._run_score)
        f4.addRow("", self.btn_run_score)
        self.lbl_status = QLabel("Generate FeaturePlot, violin, and DotPlot results for gene-set scores.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#666;")
        f4.addRow("", self.lbl_status)
        layout.addWidget(grp4)

        self.bind_help_refresh(
            self.cmb_object,
            self.cmb_label_col,
            self.cmb_mode,
            self.edit_gmt,
            self.cmb_gmt_pathway,
            self.edit_gene_set,
            self.cmb_compare_mode,
            self.cmb_group1,
            self.cmb_group2,
            self.cmb_target_label,
            self.cmb_target_label_2,
            self.cmb_stat_method,
        )
        self._refresh_label_cols()
        self._refresh_compare_options()
        self._update_mode_ui()
        self._update_compare_ui()
        return container

    def _cache_dir(self) -> str:
        return self.project.cache_subdir("module_score") if self.project else ""

    def _on_object_changed(self, _idx: int):
        if self.cmb_object.currentData():
            self.save_object_source_selection("module_score", str(self.cmb_object.currentData()))
        self._refresh_label_cols()
        self._refresh_compare_options()

    def _refresh_object_sources(self):
        current_key = self.cmb_object.currentData() or self.get_saved_object_source("module_score", default="main")
        self.cmb_object.blockSignals(True)
        self.cmb_object.clear()
        for source in self.get_object_sources():
            self.cmb_object.addItem(source["label"], source["key"])
        self.cmb_object.blockSignals(False)
        if self.cmb_object.count() == 0:
            return
        idx = self.cmb_object.findData(current_key)
        if idx < 0:
            idx = 0
        self.cmb_object.setCurrentIndex(idx)

    def _refresh_label_cols(self):
        current = self.cmb_label_col.currentText()
        self.cmb_label_col.blockSignals(True)
        self.cmb_label_col.clear()
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main"))
        for col_name in (source or {}).get("label_columns", ["cell.type", "seurat_clusters"]):
            self.cmb_label_col.addItem(col_name)
        idx = self.cmb_label_col.findText(current)
        if idx >= 0:
            self.cmb_label_col.setCurrentIndex(idx)
        self.cmb_label_col.blockSignals(False)

    def _load_label_values(self) -> list[str]:
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main"))
        values = (source or {}).get("label_values", []) or []
        if isinstance(values, str):
            values = [values]
        return [str(x).strip() for x in values if str(x).strip()]

    def _refresh_compare_options(self):
        if not self.project:
            return
        group_order = self.main_window.get_group_order() if hasattr(self.main_window, "get_group_order") else []
        if not group_order:
            seen = set()
            group_order = []
            for sample in self.project.samples:
                if sample.group and sample.group not in seen:
                    seen.add(sample.group)
                    group_order.append(sample.group)
        for cmb in (self.cmb_group1, self.cmb_group2):
            current = cmb.currentText().strip()
            cmb.clear()
            for group in group_order:
                cmb.addItem(group)
            idx = cmb.findText(current)
            cmb.setCurrentIndex(idx if idx >= 0 else 0)
        label_values = self._load_label_values()
        current_label = self.cmb_target_label.currentText().strip()
        current_label_2 = self.cmb_target_label_2.currentText().strip() if hasattr(self, "cmb_target_label_2") else ""
        self.cmb_target_label.clear()
        if hasattr(self, "cmb_target_label_2"):
            self.cmb_target_label_2.clear()
        for label in label_values:
            self.cmb_target_label.addItem(label)
            if hasattr(self, "cmb_target_label_2"):
                self.cmb_target_label_2.addItem(label)
        idx = self.cmb_target_label.findText(current_label)
        self.cmb_target_label.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, "cmb_target_label_2"):
            idx2 = self.cmb_target_label_2.findText(current_label_2)
            self.cmb_target_label_2.setCurrentIndex(idx2 if idx2 >= 0 else 0)

    def _update_mode_ui(self):
        is_gmt = self.cmb_mode.currentData() == "gmt"
        self.edit_gmt.setEnabled(is_gmt)
        self.btn_browse_gmt.setEnabled(is_gmt)
        self.cmb_gmt_pathway.setEnabled(is_gmt)
        self.edit_gene_set.setEnabled(not is_gmt)
        self.btn_browse_gene_set.setEnabled(not is_gmt)
        self.btn_download_template.setEnabled(not is_gmt)
        self.refresh_help()

    def _update_compare_ui(self):
        mode = self.cmb_compare_mode.currentData() if hasattr(self, "cmb_compare_mode") else "basic"
        is_basic = mode == "basic"
        is_within = mode == "within_label"
        is_cross = mode == "cross_label"
        self.cmb_group1.setEnabled(not is_basic)
        self.cmb_group2.setEnabled(not is_basic)
        self.cmb_target_label.setEnabled(is_within or is_cross)
        if hasattr(self, "cmb_target_label_2"):
            self.cmb_target_label_2.setEnabled(is_cross)
        self.cmb_stat_method.setEnabled(not is_basic)
        if is_basic:
            self.lbl_compare_hint.setText("Gene-set scores will be summarized across the selected object.")
        elif is_within:
            self.lbl_compare_hint.setText("Compare group 1 vs group 2 within the selected cell type or subtype.")
        elif is_cross:
            self.lbl_compare_hint.setText("Compare group 1 + cell type 1 against group 2 + cell type 2.")
        else:
            self.lbl_compare_hint.setText("Compare group 1 vs group 2 across all cells.")
        self.refresh_help()

    def _browse_gmt(self):
        path, _ = QFileDialog.getOpenFileName(self, " GMT file", "", "GMT (*.gmt);;file (*)")
        if path:
            self.edit_gmt.setText(path)
            self._load_gmt_pathways(path)
            self.refresh_help()

    def _load_gmt_pathways(self, path: str):
        self.cmb_gmt_pathway.clear()
        pathways = read_gmt_pathways(path)
        if pathways:
            self.cmb_gmt_pathway.addItems(pathways)
            self.lbl_status.setText(f"Loaded {len(pathways)} pathways. Please select a pathway.")
            self.lbl_status.setStyleSheet("color:#666;")
        else:
            self.lbl_status.setText("No pathways were loaded from the GMT file. Please check the file format.")
            self.lbl_status.setStyleSheet("color:#C62828;")

    def _browse_gene_set(self):
        path, _ = QFileDialog.getOpenFileName(self, "Gene Set File", "", "file (*.csv *.txt);;file (*)")
        if path:
            self.edit_gene_set.setText(path)
            self.refresh_help()

    def _download_template(self):
        default_name = "gene_set_template.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Savegenes CSV ", default_name, "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["gene"])
                writer.writerow(["Mbp"])
                writer.writerow(["Plp1"])
                writer.writerow(["Mog"])
            QMessageBox.information(self, "Saved", f"Gene template saved:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", f"Save failed: {exc}")

    def _input_rds(self) -> str:
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main"))
        return str((source or {}).get("input_rds", "") or "")

    def _preferred_reduction(self) -> str:
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main"))
        reduction = str((source or {}).get("preferred_reduction", "") or "umap").lower()
        return reduction if reduction in {"umap", "tsne"} else "umap"

    def get_params(self) -> dict:
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main")) or {}
        return {
            "object_level": source.get("label", self.cmb_object.currentText()),
            "object_source_key": source.get("key", "main"),
            "object_source_label": source.get("display_name", source.get("label", self.cmb_object.currentText())),
            "result_prefix": source.get("source_tag", "main"),
            "label_col": self.cmb_label_col.currentText(),
            "input_mode": self.cmb_mode.currentData(),
            "gmt_file": self.edit_gmt.text().strip(),
            "selected_pathway": self.cmb_gmt_pathway.currentText().strip(),
            "gene_set_file": self.edit_gene_set.text().strip(),
            "comparison_mode": self.cmb_compare_mode.currentData(),
            "group_1": self.cmb_group1.currentText().strip(),
            "group_2": self.cmb_group2.currentText().strip(),
            "selected_label": self.cmb_target_label.currentText().strip(),
            "selected_label_2": self.cmb_target_label_2.currentText().strip() if hasattr(self, "cmb_target_label_2") else "",
            "stat_method": self.cmb_stat_method.currentText(),
            "preferred_reduction": self._preferred_reduction(),
            "group_order": self.main_window.get_group_order() if hasattr(self.main_window, "get_group_order") else [],
            "seed": self.app_config.default_seed,
            "color_scheme": getattr(self.project, "plot_theme", self.app_config.color_scheme) if self.project else self.app_config.color_scheme,
        }

    def reset_params(self):
        self._refresh_object_sources()
        self.cmb_object.setCurrentIndex(0)
        self._refresh_label_cols()
        self._refresh_compare_options()
        self.cmb_mode.setCurrentIndex(0)
        self.edit_gmt.clear()
        self.cmb_gmt_pathway.clear()
        self.edit_gene_set.clear()
        self.cmb_compare_mode.setCurrentIndex(0)
        self.cmb_stat_method.setCurrentText("wilcox")
        self._update_mode_ui()
        self._update_compare_ui()

    def get_help_html(self) -> str:
        return build_step_help("module_score", {
            "object_level": self.cmb_object.currentText(),
            "label_col": self.cmb_label_col.currentText(),
            "input_mode": self.cmb_mode.currentText(),
            "selected_pathway": self.cmb_gmt_pathway.currentText().strip() or "Not selected",
            "gene_set_file": self.edit_gene_set.text().strip() or "Not selected",
            "preferred_reduction": self._preferred_reduction().upper(),
            "comparison_mode": self.cmb_compare_mode.currentText(),
            "group_1": self.cmb_group1.currentText().strip() or "Not selected",
            "group_2": self.cmb_group2.currentText().strip() or "Not selected",
            "selected_label": self.cmb_target_label.currentText().strip() or "Not selected",
            "selected_label_2": self.cmb_target_label_2.currentText().strip() if hasattr(self, "cmb_target_label_2") else "Not selected",
            "stat_method": self.cmb_stat_method.currentText(),
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_object_sources()
        self._refresh_label_cols()
        self._refresh_compare_options()
        self._update_compare_ui()

    def on_page_entered(self):
        self._refresh_object_sources()
        self._refresh_label_cols()
        self._refresh_compare_options()
        self._update_compare_ui()

    def _run_score(self):
        if not self.require_project():
            return
        input_rds = self._input_rds()
        if not input_rds:
            QMessageBox.warning(self, "Notice", "Cannot find an object for gene set scoring. Please finish clustering, annotation, or subcluster analysis first.")
            return

        mode = self.cmb_mode.currentData()
        if mode == "gmt":
            gmt_file = self.edit_gmt.text().strip()
            pathway = self.cmb_gmt_pathway.currentText().strip()
            if not gmt_file or not os.path.isfile(gmt_file):
                QMessageBox.warning(self, "Notice", " GMT file.")
                return
            if not pathway:
                QMessageBox.warning(self, "Notice", " GMT file or pathway.")
                return
        else:
            gene_set_file = self.edit_gene_set.text().strip()
            if not gene_set_file or not os.path.isfile(gene_set_file):
                QMessageBox.warning(self, "Notice", "Gene Set File.")
                return

        params = self.get_params()
        if params["comparison_mode"] != "basic":
            if not params["group_1"] or not params["group_2"]:
                QMessageBox.warning(self, "Notice", " group.")
                return
            if params["comparison_mode"] == "within_label" and not params["selected_label"]:
                QMessageBox.warning(self, "Notice", "Please select a target cell type or subcluster.")
                return
            if params["comparison_mode"] == "cross_label" and (not params["selected_label"] or not params["selected_label_2"]):
                QMessageBox.warning(self, "Notice", "Please select a cell type or subcluster.")
                return

        self.clear_log()
        self.append_log("=== Start Gene Set Scoring ===")
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        self.register_task_owner()
        self.task_runner.run_r_script("10_module_score.R", params, self._cache_dir(), "Gene Set Scoring")

    def run_step(self):
        self._run_score()

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        cache = self._cache_dir()
        figures = getattr(result, "figures", None) or summary.get("figures", [])
        if isinstance(figures, str):
            figures = [figures]
        last_fig = ""
        fig_name_map = {
            "gene_set_featureplot": "Gene Set FeaturePlot",
            "gene_set_featureplot_by_group": "Gene Set FeaturePlot by Group",
            "gene_set_violin_plot": "Gene Set Violin Plot",
            "gene_set_dotplot": "Gene Set DotPlot",
            "gene_set_group_comparison_plot": "Gene Set Group Comparison Plot",
            "gene_set_dotplot_grouped": "Gene Set DotPlot by Group",
            "violin_all_celltypes": "Gene Set Violin Plot Across All Cell Types",
            "module_score_featureplot": "Gene Set FeaturePlot",
            "module_score_violin": "Gene Set Violin Plot",
            "module_score_dotplot": "Gene Set DotPlot",
            "module_score_comparison_plot": "Gene Set Group Comparison Plot",
        }
        def _match_name(stem: str, mapping: dict[str, str]) -> str:
            for key, value in mapping.items():
                if stem == key or stem.endswith(f"_{key}"):
                    return value
            return stem
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache, fig)
            if os.path.isfile(fig_path):
                stem = os.path.splitext(os.path.basename(fig_path))[0]
                preview_name = _match_name(stem, fig_name_map)
                self.main_window.add_preview_item(preview_name, fig_path, "figure", "Module Scoring")
                if not last_fig or stem.endswith(("gene_set_featureplot", "gene_set_featureplot_by_group", "gene_set_group_comparison_plot", "module_score_featureplot", "module_score_comparison_plot")):
                    last_fig = fig_path

        tables = summary.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        table_name_map = {
            "gene_set_pairwise_celltype_stats": "Gene Set Cell Type Pairwise Statistics",
            "gene_set_pairwise_group_stats": "Gene Set Group Pairwise Statistics",
            "gene_set_gene_status": "Gene Set Gene Usage Status",
            "gene_set_per_cell_scores": "Gene Set Per-Cell Scores",
            "gene_set_group_comparison_stats": "Gene Set Group Comparison Statistics",
            "gene_set_score_matrix": "Gene Set Score Matrix",
            "gene_set_violin_plot_data": "Gene Set Violin Plot Data",
            "gene_set_dotplot_data": "Gene Set DotPlot Data",
            "gene_set_grouped_dotplot_data": "Gene Set Grouped DotPlot Data",
            "module_score_pairwise_celltype_stats": "Gene Set Cell Type Pairwise Statistics",
            "module_score_pairwise_group_stats": "Gene Set Group Pairwise Statistics",
            "module_score_gene_status": "Gene Set Gene Usage Status",
            "module_score_per_cell": "Gene Set Per-Cell Scores",
            "module_score_comparison_stats": "Gene Set Group Comparison Statistics",
        }
        for tbl in tables:
            tbl_path = tbl if os.path.isabs(tbl) else os.path.join(cache, tbl)
            if os.path.isfile(tbl_path):
                stem = os.path.splitext(os.path.basename(tbl_path))[0]
                preview_name = _match_name(stem, table_name_map)
                self.main_window.add_preview_item(preview_name, tbl_path, "table", "Module Scoring")

        reduction_used = str(summary.get("reduction_used", "") or "").upper()
        if last_fig:
            preview_title = "Module Scoring Results"
            fig_base = os.path.basename(last_fig)
            if reduction_used and fig_base.startswith(("gene_set_featureplot", "module_score_featureplot")):
                preview_title = f"Gene Set Score on {reduction_used}"
            elif str(summary.get("comparison_name", "") or ""):
                preview_title = f"Gene Set Comparison - {summary.get('comparison_name', '')}"
            self.main_window.show_preview_image(last_fig, preview_title)
        valid_count = summary.get("valid_gene_count", 0)
        ignored_count = summary.get("ignored_gene_count", 0)
        status_tail = f", {reduction_used}" if reduction_used else ""
        comparison_name = str(summary.get("comparison_name", "") or "")
        comparison_tail = f", comparison: {comparison_name}" if comparison_name else ""
        self.lbl_status.setText(f"Gene-set scoring completed: {valid_count} valid genes, {ignored_count} ignored genes{status_tail}{comparison_tail}.")
        self.lbl_status.setStyleSheet("color:#2E7D32; font-weight:600;")
        self.project.step_status["module_score"] = "done"
        idx = self.main_window.get_step_index("module_score")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

    def on_step_error(self, step, summary, detail):
        QMessageBox.warning(self, "Gene Set Scoring Failed", summary)
