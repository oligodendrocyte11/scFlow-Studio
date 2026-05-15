from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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


class GeneAnalysisPage(BasePage):
    STEP_ID = "gene_analysis"
    STEP_NAME = "⑩ Single-Gene Analysis"

    def __init__(self, main_window, app_config, r_bridge, task_runner):
        self._gene_list: list[str] = []
        super().__init__(main_window, app_config, r_bridge, task_runner)

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp1 = QGroupBox("Step 1:Object")
        f1 = QFormLayout(grp1)
        self.cmb_object = QComboBox()
        self.cmb_object.currentIndexChanged.connect(self._on_object_changed)
        self.cmb_label_col = QComboBox()
        self.cmb_label_col.currentIndexChanged.connect(lambda _idx: self._refresh_compare_options())
        f1.addRow("Object:", self.cmb_object)
        f1.addRow("Group:", self.cmb_label_col)
        layout.addWidget(grp1)

        grp2 = QGroupBox("Step 2 - Target Gene")
        f2 = QFormLayout(grp2)
        gene_row = QHBoxLayout()
        self.cmb_gene = QComboBox()
        self.cmb_gene.setEditable(True)
        self.cmb_gene.setMinimumWidth(320)
        self.btn_refresh_genes = QPushButton("Refresh Gene List")
        self.btn_refresh_genes.clicked.connect(self._load_gene_list)
        gene_row.addWidget(self.cmb_gene, 1)
        gene_row.addWidget(self.btn_refresh_genes)
        gene_wrap = QWidget()
        gene_wrap.setLayout(gene_row)
        f2.addRow("Target Gene:", gene_wrap)
        self.lbl_gene_hint = QLabel("Select an object and one or more genes for visualization and comparison.")
        self.lbl_gene_hint.setWordWrap(True)
        self.lbl_gene_hint.setStyleSheet("color:#666; font-size:11px;")
        f2.addRow("", self.lbl_gene_hint)
        layout.addWidget(grp2)

        grp3 = QGroupBox("Step 3: Gene DotPlot")
        f3 = QFormLayout(grp3)
        self.edit_multi_genes = QLineEdit()
        self.edit_multi_genes.setPlaceholderText("Enter genes, e.g. Mbp, Plp1, Mog")
        f3.addRow("Multiple Genes:", self.edit_multi_genes)
        self.lbl_multi_hint = QLabel("Choose genes to generate expression dot plots.")
        self.lbl_multi_hint.setWordWrap(True)
        self.lbl_multi_hint.setStyleSheet("color:#666; font-size:11px;")
        f3.addRow("", self.lbl_multi_hint)
        layout.addWidget(grp3)

        grp4 = QGroupBox("Step 4 - Comparison")
        f4 = QFormLayout(grp4)
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
        f4.addRow("Comparison Mode:", self.cmb_compare_mode)
        f4.addRow("Group 1:", self.cmb_group1)
        f4.addRow("Group 2:", self.cmb_group2)
        f4.addRow("Target cell type/Subcluster 1:", self.cmb_target_label)
        self.cmb_target_label_2 = QComboBox()
        self.cmb_target_label_2.setEditable(True)
        f4.addRow("Target cell type/Subcluster 2:", self.cmb_target_label_2)
        f4.addRow("Statistical Method:", self.cmb_stat_method)
        self.lbl_compare_hint = QLabel("Choose a comparison mode to generate statistical results.")
        self.lbl_compare_hint.setWordWrap(True)
        self.lbl_compare_hint.setStyleSheet("color:#666; font-size:11px;")
        f4.addRow("", self.lbl_compare_hint)
        layout.addWidget(grp4)

        grp5 = QGroupBox("Step 5 - Run Analysis")
        f5 = QFormLayout(grp5)
        self.btn_run = QPushButton("Start Single-Gene Analysis")
        self.btn_run.setProperty("role", "primary")
        self.btn_run.clicked.connect(self._run_analysis)
        f5.addRow("", self.btn_run)
        self.lbl_status = QLabel("Generate violin plots, dot plots, FeaturePlots, and multi-gene dot plots.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#666;")
        f5.addRow("", self.lbl_status)
        layout.addWidget(grp5)

        self.bind_help_refresh(
            self.cmb_object,
            self.cmb_label_col,
            self.cmb_gene,
            self.edit_multi_genes,
            self.cmb_compare_mode,
            self.cmb_group1,
            self.cmb_group2,
            self.cmb_target_label,
            self.cmb_target_label_2,
            self.cmb_stat_method,
        )
        self._refresh_label_cols()
        self._refresh_compare_options()
        self._update_compare_ui()
        return container

    def _cache_dir(self) -> str:
        return self.project.cache_subdir("gene_analysis") if self.project else ""

    def _on_object_changed(self, _idx: int):
        if self.cmb_object.currentData():
            self.save_object_source_selection("gene_analysis", str(self.cmb_object.currentData()))
        self._refresh_label_cols()
        self._load_gene_list()
        self._refresh_compare_options()

    def _refresh_object_sources(self):
        current_key = self.cmb_object.currentData() or self.get_saved_object_source("gene_analysis", default="main")
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

    def _gene_file_path(self) -> str:
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main"))
        if source and source.get("object_level") == "subcluster":
            return str(source.get("gene_list", "") or "")
        if not self.project:
            return ""
        return self._main_object_paths().get("gene_list", "")

    def _load_gene_list(self):
        self._gene_list = []
        self.cmb_gene.clear()
        gene_file = self._gene_file_path()
        if gene_file and os.path.isfile(gene_file):
            with open(gene_file, "r", encoding="utf-8") as handle:
                self._gene_list = [line.strip() for line in handle if line.strip()]
        if self._gene_list:
            self.cmb_gene.addItems(self._gene_list)
            self.lbl_gene_hint.setText(f"Loaded {len(self._gene_list)} genes.")
        else:
            self.lbl_gene_hint.setText("Gene list is available after main or subcluster annotation.")

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
            "gene": self.cmb_gene.currentText().strip(),
            "multi_genes": self.edit_multi_genes.text().strip(),
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
        self._load_gene_list()
        self._refresh_compare_options()
        self.edit_multi_genes.clear()
        self.cmb_compare_mode.setCurrentIndex(0)
        self.cmb_stat_method.setCurrentText("wilcox")
        if self.cmb_gene.count() > 0:
            self.cmb_gene.setCurrentIndex(0)
        self._update_compare_ui()

    def get_help_html(self) -> str:
        return build_step_help("gene_analysis", {
            "object_level": self.cmb_object.currentText(),
            "label_col": self.cmb_label_col.currentText(),
            "gene": self.cmb_gene.currentText().strip() or "Not selected",
            "preferred_reduction": self._preferred_reduction().upper(),
            "comparison_mode": self.cmb_compare_mode.currentText(),
            "group_1": self.cmb_group1.currentText().strip() or "Not selected",
            "group_2": self.cmb_group2.currentText().strip() or "Not selected",
            "selected_label": self.cmb_target_label.currentText().strip() or "Not selected",
            "stat_method": self.cmb_stat_method.currentText(),
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_object_sources()
        self._refresh_label_cols()
        self._load_gene_list()
        self._refresh_compare_options()
        self._update_compare_ui()

    def on_page_entered(self):
        self._refresh_object_sources()
        self._refresh_label_cols()
        self._load_gene_list()
        self._refresh_compare_options()
        self._update_compare_ui()

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
            self.lbl_compare_hint.setText("Gene expression will be summarized across the selected object.")
        elif is_within:
            self.lbl_compare_hint.setText("Compare group 1 vs group 2 within the selected cell type or subtype.")
        elif is_cross:
            self.lbl_compare_hint.setText("Compare group 1 + cell type 1 against group 2 + cell type 2.")
        else:
            self.lbl_compare_hint.setText("Compare group 1 vs group 2 across all cells.")
        self.refresh_help()

    def _run_analysis(self):
        if not self.require_project():
            return
        gene = self.cmb_gene.currentText().strip()
        if not gene:
            QMessageBox.warning(self, "Notice", "Target Gene.")
            return
        input_rds = self._input_rds()
        if not input_rds:
            QMessageBox.warning(self, "Notice", "Cannot find an object for single-gene analysis. Please finish clustering, annotation, or subcluster analysis first.")
            return

        params = self.get_params()
        if params["comparison_mode"] != "basic":
            if not params["group_1"] or not params["group_2"]:
                QMessageBox.warning(self, "Notice", " group.")
                return
            if params["comparison_mode"] == "within_label" and not params["selected_label"]:
                QMessageBox.warning(self, "Notice", "Please select a target cell type or subcluster.")
                return

        self.clear_log()
        self.append_log(f"=== Start Single-Gene Analysis: {gene} ===")
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        self.register_task_owner()
        self.task_runner.run_r_script("09_gene_analysis.R", params, self._cache_dir(), "Single-Gene Analysis")

    def run_step(self):
        self._run_analysis()

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        cache = self._cache_dir()
        figures = getattr(result, "figures", None) or summary.get("figures", [])
        if isinstance(figures, str):
            figures = [figures]
        last_fig = ""
        fig_name_map = {
            "single_gene_violin_plot": "Single-Gene Violin Plot",
            "single_gene_expression_dotplot": "Single-Gene Expression DotPlot",
            "single_gene_featureplot": "Single-Gene FeaturePlot",
            "single_gene_featureplot_by_group": "Single-Gene FeaturePlot by Group",
            "single_gene_multi_dotplot": "Multi-Gene DotPlot",
            "single_gene_group_comparison_plot": "Single-Gene Group Comparison DotPlot",
            "single_gene_group_comparison_violin_plot": "Single-Gene Group Comparison Plot",
            "single_gene_dotplot_grouped": "Single-Gene DotPlot by Group",
            "violin_all_celltypes": "Single-Gene Violin Plot Across All Cell Types",
            "gene_violin_celltypes": "Single-Gene Violin Plot",
            "gene_dotplot": "Single-Gene Expression DotPlot",
            "gene_featureplot": "Single-Gene FeaturePlot",
            "gene_multi_dotplot": "Multi-Gene DotPlot",
            "gene_comparison_plot": "Single-Gene Group Comparison Plot",
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
                self.main_window.add_preview_item(preview_name, fig_path, "figure", "Gene Analysis")
                if not last_fig or stem.endswith(("single_gene_featureplot", "single_gene_featureplot_by_group", "single_gene_group_comparison_violin_plot", "single_gene_group_comparison_plot", "gene_featureplot", "gene_comparison_plot")):
                    last_fig = fig_path

        tables = summary.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        table_name_map = {
            "single_gene_pairwise_celltype_stats": "Single-Gene Cell Type Pairwise Statistics",
            "single_gene_pairwise_group_stats": "Single-Gene Group Pairwise Statistics",
            "single_gene_expression_summary": "Single-Gene Expression Summary",
            "single_gene_group_comparison_stats": "Single-Gene Group Comparison Statistics",
            "single_gene_expression_values": "Single-Gene Expression Values",
            "single_gene_violin_plot_data": "Single-Gene Violin Plot Data",
            "single_gene_dotplot_data": "Single-Gene DotPlot Data",
            "single_gene_grouped_dotplot_data": "Single-Gene Grouped DotPlot Data",
            "single_gene_group_comparison_values": "Single-Gene Comparison Raw Values",
            "single_gene_expression_matrix": "Single-Gene Expression Matrix",
            "multi_gene_expression_matrix": "Multi-Gene Expression Matrix",
            "single_gene_multi_dotplot_data": "Multi-Gene DotPlot Data",
            "gene_pairwise_celltype_stats": "Single-Gene Cell Type Pairwise Statistics",
            "gene_pairwise_group_stats": "Single-Gene Group Pairwise Statistics",
            "gene_expression_summary": "Single-Gene Expression Summary",
            "gene_comparison_stats": "Single-Gene Group Comparison Statistics",
        }
        for tbl in tables:
            tbl_path = tbl if os.path.isabs(tbl) else os.path.join(cache, tbl)
            if os.path.isfile(tbl_path):
                stem = os.path.splitext(os.path.basename(tbl_path))[0]
                preview_name = _match_name(stem, table_name_map)
                self.main_window.add_preview_item(preview_name, tbl_path, "table", "Gene Analysis")

        reduction_used = str(summary.get("reduction_used", "") or "").upper()
        if last_fig:
            preview_title = f"Gene Analysis - {summary.get('gene', '')}"
            fig_base = os.path.basename(last_fig)
            if reduction_used and fig_base.startswith(("single_gene_featureplot", "gene_featureplot")):
                preview_title = f"{summary.get('gene', '')} on {reduction_used}"
            elif str(summary.get("comparison_name", "") or ""):
                preview_title = f"Single-Gene Comparison - {summary.get('comparison_name', '')}"
            self.main_window.show_preview_image(last_fig, preview_title)
        status_tail = f", {reduction_used}" if reduction_used else ""
        comparison_name = str(summary.get("comparison_name", "") or "")
        comparison_tail = f", comparison: {comparison_name}" if comparison_name else ""
        self.lbl_status.setText(f"Single-gene analysis finished: {summary.get('gene', '')}. Results were added to preview{status_tail}{comparison_tail}.")
        self.lbl_status.setStyleSheet("color:#2E7D32; font-weight:600;")
        self.project.step_status["gene_analysis"] = "done"
        idx = self.main_window.get_step_index("gene_analysis")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

    def on_step_error(self, step, summary, detail):
        QMessageBox.warning(self, "Single-Gene Analysis Failed", summary)
