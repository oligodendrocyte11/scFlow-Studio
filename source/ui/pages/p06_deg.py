from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


class DEGPage(BasePage):
    STEP_ID = "deg"
    STEP_NAME = "⑧ Differential Expression"

    def __init__(self, main_window, app_config, r_bridge, task_runner):
        self.current_comparison_name = ""
        self.current_deg_full_csv = ""
        self.current_deg_sig_csv = ""
        self.current_deg_result_id = ""
        super().__init__(main_window, app_config, r_bridge, task_runner)

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp1 = QGroupBox("Step 1 - Object")
        f1 = QFormLayout(grp1)
        self.cmb_object = QComboBox()
        self.cmb_object.currentIndexChanged.connect(self._on_object_changed)
        f1.addRow("Object:", self.cmb_object)
        layout.addWidget(grp1)

        grp2 = QGroupBox("Step 2 - Comparison Mode")
        s2 = QVBoxLayout(grp2)
        self.radio_A = QRadioButton("A. Same cell type between groups")
        self.radio_B = QRadioButton("B. Different cell types within one group")
        self.radio_C = QRadioButton("C. Cross-group + cross-cell-type comparison")
        self.radio_D = QRadioButton("D. Custom group/cell-type comparison")
        self.radio_A.setChecked(True)

        self.btn_mode = QButtonGroup(self)
        self.btn_mode.addButton(self.radio_A, 0)
        self.btn_mode.addButton(self.radio_B, 1)
        self.btn_mode.addButton(self.radio_C, 2)
        self.btn_mode.addButton(self.radio_D, 3)
        self.btn_mode.idToggled.connect(self._on_mode_changed)
        for radio in [self.radio_A, self.radio_B, self.radio_C, self.radio_D]:
            s2.addWidget(radio)
        layout.addWidget(grp2)

        grp3 = QGroupBox("Step 3 - Define Comparison")
        f3 = QFormLayout(grp3)
        self.cmb_celltype_col = QComboBox()
        self.cmb_celltype_col.setMinimumWidth(220)
        self.lbl_celltype_col_hint = QLabel("Choose the annotation column used for DEG, such as cell.type, subtype, or seurat_clusters.")
        self.lbl_celltype_col_hint.setStyleSheet("color:#666; font-size:11px;")
        self.lbl_celltype_col_hint.setWordWrap(True)
        celltype_col_wrap = QWidget()
        celltype_col_layout = QVBoxLayout(celltype_col_wrap)
        celltype_col_layout.setContentsMargins(0, 0, 0, 0)
        celltype_col_layout.setSpacing(4)
        celltype_col_layout.addWidget(self.cmb_celltype_col)
        celltype_col_layout.addWidget(self.lbl_celltype_col_hint)
        f3.addRow("Annotation:", celltype_col_wrap)

        f3.addRow(QLabel("Set 1"), QLabel("Select the first group and cell type."))
        self.cmb_group1 = QComboBox()
        self.cmb_group1.setEditable(True)
        self.cmb_group1.setMinimumWidth(220)
        f3.addRow("Group:", self.cmb_group1)
        self.cmb_ct1 = QComboBox()
        self.cmb_ct1.setEditable(True)
        self.cmb_ct1.setMinimumWidth(220)
        f3.addRow("Cell Type:", self.cmb_ct1)

        f3.addRow(QLabel("Set 2"), QLabel("Select the second group and cell type."))
        self.cmb_group2 = QComboBox()
        self.cmb_group2.setEditable(True)
        self.cmb_group2.setMinimumWidth(220)
        f3.addRow("Group:", self.cmb_group2)
        self.cmb_ct2 = QComboBox()
        self.cmb_ct2.setEditable(True)
        self.cmb_ct2.setMinimumWidth(220)
        f3.addRow("Cell Type:", self.cmb_ct2)

        self.lbl_compare_desc = QLabel("")
        self.lbl_compare_desc.setStyleSheet("color:#2196F3; font-size:11px;")
        self.lbl_compare_desc.setWordWrap(True)
        f3.addRow("", self.lbl_compare_desc)

        self.edit_result_name = QLineEdit()
        self.edit_result_name.setPlaceholderText("Optional DEG result name")
        f3.addRow("Result name:", self.edit_result_name)
        self.lbl_multi_compare_hint = QLabel("Each DEG run is saved as a separate result and can be selected later.")
        self.lbl_multi_compare_hint.setWordWrap(True)
        self.lbl_multi_compare_hint.setStyleSheet("color:#666; font-size:11px;")
        f3.addRow("", self.lbl_multi_compare_hint)
        layout.addWidget(grp3)

        grp4 = QGroupBox("Step 4 - DEG Parameters")
        f4 = QFormLayout(grp4)
        self.cmb_test = QComboBox()
        self.cmb_test.addItems(["MAST", "wilcox", "bimod", "t"])
        f4.addRow("Test method:", self.cmb_test)

        self.spn_min_pct = QDoubleSpinBox()
        self.spn_min_pct.setRange(0, 1)
        self.spn_min_pct.setDecimals(2)
        self.spn_min_pct.setValue(self.app_config.deg_min_pct)
        f4.addRow("min.pct:", self.spn_min_pct)

        self.spn_logfc = QDoubleSpinBox()
        self.spn_logfc.setRange(0, 5)
        self.spn_logfc.setDecimals(2)
        self.spn_logfc.setValue(self.app_config.deg_logfc_threshold)
        f4.addRow("logfc.threshold:", self.spn_logfc)

        self.spn_padj = QDoubleSpinBox()
        self.spn_padj.setRange(0.0001, 1)
        self.spn_padj.setDecimals(4)
        self.spn_padj.setValue(self.app_config.deg_padj_cutoff)
        f4.addRow("p_adj:", self.spn_padj)
        layout.addWidget(grp4)

        self.lbl_gsea_next = QLabel("Tip: after differential expression finishes, continue to GSEA Enrichment for pathway analysis.")
        self.lbl_gsea_next.setWordWrap(True)
        self.lbl_gsea_next.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(self.lbl_gsea_next)

        run_row = QHBoxLayout()
        self.btn_run_deg = QPushButton("▶ Run DEG Analysis")
        self.btn_run_deg.setProperty("role", "primary")
        self.btn_run_deg.clicked.connect(self._run_deg)
        run_row.addWidget(self.btn_run_deg)
        run_row.addStretch()
        layout.addLayout(run_row)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Result", "Up", "Down", "Status"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setMaximumHeight(160)
        layout.addWidget(self.history_table)

        self.bind_help_refresh(
            self.cmb_object,
            self.radio_A,
            self.radio_B,
            self.radio_C,
            self.radio_D,
            self.cmb_celltype_col,
            self.cmb_group1,
            self.cmb_ct1,
            self.cmb_group2,
            self.cmb_ct2,
            self.edit_result_name,
            self.cmb_test,
            self.spn_min_pct,
            self.spn_logfc,
            self.spn_padj,
        )
        self._on_mode_changed(0, True)
        return container

    def _on_mode_changed(self, bid, checked):
        if not checked:
            return
        descs = {
            0: "A: compare the same cell type between two groups, for example MCAO Astrocytes vs Sham Astrocytes.",
            1: "B: compare two cell types within the same group, for example Sham Astrocytes vs Sham Myeloid.",
            2: "C: compare different cell types across groups, for example Sham Astrocytes vs MCAO Myeloid.",
            3: "D: custom group/cell-type comparison using the two selected sets.",
        }
        self.lbl_compare_desc.setText(descs.get(self.btn_mode.checkedId(), ""))

    def _on_object_changed(self, _idx):
        if self.cmb_object.currentData():
            self.save_object_source_selection("deg", str(self.cmb_object.currentData()))
        self._refresh_options()

    def _refresh_object_sources(self):
        current_key = self.cmb_object.currentData() or self.get_saved_object_source("deg", default="main")
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

    def get_params(self) -> dict:
        group_order = self.main_window.get_group_order() if hasattr(self.main_window, "get_group_order") else []
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main")) or {}
        return {
            "object_level": source.get("label", self.cmb_object.currentText()),
            "object_source_key": source.get("key", "main"),
            "object_source_label": source.get("display_name", source.get("label", self.cmb_object.currentText())),
            "compare_mode": self.btn_mode.checkedId(),
            "comparison_mode": self._comparison_mode_key(),
            "celltype_col": self.cmb_celltype_col.currentText(),
            "group_1": self.cmb_group1.currentText().strip(),
            "ct_1": self.cmb_ct1.currentText().strip(),
            "group_2": self.cmb_group2.currentText().strip(),
            "ct_2": self.cmb_ct2.currentText().strip(),
            "result_id": self.current_deg_result_id,
            "result_name": self.edit_result_name.text().strip(),
            "test_use": self.cmb_test.currentText(),
            "min_pct": self.spn_min_pct.value(),
            "logfc_threshold": self.spn_logfc.value(),
            "padj_cutoff": self.spn_padj.value(),
            "group_order": group_order,
            "seed": self.app_config.default_seed,
        }

    def reset_params(self):
        c = self.app_config
        self._refresh_object_sources()
        self.cmb_object.setCurrentIndex(0)
        self.radio_A.setChecked(True)
        self.cmb_test.setCurrentText(c.deg_test_use)
        self.spn_min_pct.setValue(c.deg_min_pct)
        self.spn_logfc.setValue(c.deg_logfc_threshold)
        self.spn_padj.setValue(c.deg_padj_cutoff)
        self.edit_result_name.clear()
        self._refresh_options()

    def get_help_html(self) -> str:
        return build_step_help("deg", {
            "object_level": self.cmb_object.currentText(),
            "compare_mode": self._get_compare_mode_label(),
            "celltype_col": self.cmb_celltype_col.currentText(),
            "test_use": self.cmb_test.currentText(),
            "min_pct": self.spn_min_pct.value(),
            "logfc_threshold": self.spn_logfc.value(),
            "padj_cutoff": self.spn_padj.value(),
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_object_sources()
        self._refresh_options()
        self._restore_deg_context()
        self._refresh_deg_history_table()
        self.refresh_help()

    def on_page_entered(self):
        self._refresh_object_sources()
        self._refresh_options()
        self._restore_deg_context()
        self._refresh_deg_history_table()
        self.refresh_help()

    def _refresh_options(self):
        if not self.project:
            self.refresh_help()
            return

        group_order = self.main_window.get_group_order() if hasattr(self.main_window, "get_group_order") else []
        if not group_order:
            seen = set()
            group_order = []
            for sample in self.project.samples:
                if sample.group and sample.group not in seen:
                    seen.add(sample.group)
                    group_order.append(sample.group)

        for cmb in [self.cmb_group1, self.cmb_group2]:
            current = cmb.currentText()
            cmb.clear()
            cmb.addItem("(All)")
            for group in group_order:
                cmb.addItem(group)
            idx = cmb.findText(current)
            cmb.setCurrentIndex(idx if idx >= 0 else 0)

        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main")) or {}
        is_sub = source.get("object_level") == "subcluster"
        cell_types = self._load_celltypes()
        for cmb in [self.cmb_ct1, self.cmb_ct2]:
            current = cmb.currentText()
            cmb.clear()
            cmb.addItem("(All)")
            for ct in cell_types:
                cmb.addItem(ct)
            idx = cmb.findText(current)
            cmb.setCurrentIndex(idx if idx >= 0 else 0)

        current_col = self.cmb_celltype_col.currentText()
        self.cmb_celltype_col.clear()
        if is_sub:
            self.cmb_celltype_col.addItems(["subtype", "cell.type", "seurat_clusters"])
        else:
            self.cmb_celltype_col.addItems(["cell.type", "seurat_clusters"])
        idx = self.cmb_celltype_col.findText(current_col)
        self.cmb_celltype_col.setCurrentIndex(idx if idx >= 0 else 0)
        self.refresh_help()

    def _load_celltypes(self) -> list[str]:
        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main"))
        values = (source or {}).get("label_values", []) or []
        if isinstance(values, str):
            values = [values]
        return [str(x).strip() for x in values if str(x).strip()]

    def _comparison_name_from_ui(self) -> str:
        params = self.get_params()

        def _label(group: str, cell_type: str) -> str:
            if group != "(All)" and cell_type != "(All)":
                return f"{group}_{cell_type}"
            if group != "(All)":
                return group
            if cell_type != "(All)":
                return cell_type
            return "All"

        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main")) or {}
        return f"{source.get('source_tag', 'main')}__{_label(params['group_1'], params['ct_1'])}_vs_{_label(params['group_2'], params['ct_2'])}"

    def _get_compare_mode_label(self) -> str:
        mode_map = {
            0: "A. Same cell type between groups",
            1: "B. Different cell types within one group",
            2: "C. Cross-group + cross-cell-type comparison",
            3: "D. Custom group/cell-type comparison",
        }
        return mode_map.get(self.btn_mode.checkedId(), "A. Same cell type between groups")

    def _deg_cache_dir(self) -> str:
        return self.project.cache_subdir("deg") if self.project else ""

    def _deg_results_root(self) -> str:
        root = os.path.join(self._deg_cache_dir(), "results") if self.project else ""
        if root:
            os.makedirs(root, exist_ok=True)
        return root

    def _slugify(self, text: str) -> str:
        value = re.sub(r"[^A-Za-z0-9]+", "_", str(text or "").strip())
        value = re.sub(r"_+", "_", value).strip("_")
        return value.lower() or "deg"

    def _next_deg_sequence(self) -> int:
        max_seq = 0
        for item in list(getattr(self.project, "deg_results", []) or []):
            tail = str(item.get("result_id", "")).split("_")[-1]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))
        return max_seq + 1

    def _create_deg_result_entry(self, comparison_name: str, source: dict) -> dict:
        sequence = self._next_deg_sequence()
        base_slug = self._slugify(comparison_name)[:48]
        result_id = f"deg_{base_slug}_{sequence:03d}"
        display_name = self.edit_result_name.text().strip() or comparison_name or result_id
        return {
            "result_id": result_id,
            "display_name": display_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cache_dir_rel": f"cache/deg/results/{result_id}",
            "object_source_key": str(source.get("key", "main")),
            "object_source_label": str(source.get("display_name", source.get("label", self.cmb_object.currentText()))),
            "comparison_mode": self._comparison_mode_key(),
            "group_1": self._normalize_choice(self.cmb_group1.currentText()),
            "ct_1": self._normalize_choice(self.cmb_ct1.currentText()),
            "group_2": self._normalize_choice(self.cmb_group2.currentText()),
            "ct_2": self._normalize_choice(self.cmb_ct2.currentText()),
            "status": "running",
            "n_up": 0,
            "n_down": 0,
            "n_genes_tested": 0,
        }

    def _register_deg_result(self, entry: dict):
        if not self.project:
            return
        results = [item for item in list(getattr(self.project, "deg_results", []) or []) if str(item.get("result_id", "")) != str(entry.get("result_id", ""))]
        results.append(entry)
        self.project.deg_results = results
        self.main_window.project_manager.save_project(self.project)

    def _deg_result_dir(self, result_id: str, ensure: bool = False) -> str:
        if not self.project:
            return ""
        for item in list(getattr(self.project, "deg_results", []) or []):
            if str(item.get("result_id", "")) == str(result_id):
                rel = str(item.get("cache_dir_rel", "") or "").replace("/", os.sep)
                path = os.path.join(self.project.directory, rel)
                if ensure:
                    os.makedirs(path, exist_ok=True)
                return path
        return ""

    def _refresh_deg_history_table(self):
        self.history_table.setRowCount(0)
        results = sorted(list(getattr(self.project, "deg_results", []) or []), key=lambda item: (str(item.get("created_at", "")), str(item.get("result_id", ""))))
        for entry in results:
            row = self.history_table.rowCount()
            self.history_table.setRowCount(row + 1)
            self.history_table.setItem(row, 0, QTableWidgetItem(str(entry.get("display_name", "") or entry.get("result_id", ""))))
            self.history_table.setItem(row, 1, QTableWidgetItem(str(entry.get("n_up", 0))))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(entry.get("n_down", 0))))
            self.history_table.setItem(row, 3, QTableWidgetItem(str(entry.get("status", "ready"))))


    def _comparison_mode_key(self) -> str:
        return {0: "same_celltype", 1: "same_group", 2: "cross_celltype", 3: "custom"}.get(self.btn_mode.checkedId(), "same_celltype")

    def _normalize_choice(self, value: str) -> str:
        text = (value or "").strip()
        return "" if text in {"", "(All)", "All", "all", "ALL", "*"} else text

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

    def _save_deg_context(self):
        if not self.project or not self.current_comparison_name:
            return
        self._write_json(self._deg_context_path(), {
            "comparison_name": self.current_comparison_name,
            "deg_full_csv": self.current_deg_full_csv,
            "deg_sig_csv": self.current_deg_sig_csv,
            "deg_result_id": self.current_deg_result_id,
        })

    def _restore_deg_context(self):
        if not self.project:
            return
        data = self._read_json(self._deg_context_path())
        self.current_comparison_name = str(data.get("comparison_name", ""))
        self.current_deg_full_csv = str(data.get("deg_full_csv", ""))
        self.current_deg_sig_csv = str(data.get("deg_sig_csv", ""))
        self.current_deg_result_id = str(data.get("deg_result_id", ""))

    def _run_deg(self):
        if not self.require_project():
            return

        params = self.get_params()
        comparison = self._comparison_name_from_ui()
        self.current_comparison_name = comparison
        self.current_deg_full_csv = ""
        self.current_deg_sig_csv = ""

        source = self.resolve_object_source(str(self.cmb_object.currentData() or "main")) or {}
        input_rds = str(source.get("input_rds", "") or "")
        if not os.path.isfile(input_rds):
            QMessageBox.warning(self, "Notice", "Cannot find an object for DEG analysis. Please finish clustering, annotation, or subcluster analysis first.")
            return

        entry = self._create_deg_result_entry(comparison, source)
        self.current_deg_result_id = str(entry.get("result_id", ""))
        self._register_deg_result(entry)
        result_dir = self._deg_result_dir(self.current_deg_result_id, ensure=True)

        self.clear_log()
        self.append_log(f"=== DEG: {comparison} ===")
        self.append_log(f"Results saved as: {entry.get('display_name', comparison)} ({self.current_deg_result_id})")

        params["input_rds"] = input_rds
        params["comparison_name"] = comparison
        params["result_id"] = self.current_deg_result_id
        params["result_name"] = str(entry.get("display_name", ""))
        params["object_source_key"] = source.get("key", "main")
        params["object_source_label"] = source.get("display_name", source.get("label", "Object"))
        params["cache_dir"] = result_dir.replace(chr(92), "/")

        for key in ["group_1", "group_2", "ct_1", "ct_2"]:
            if params[key] == "(All)":
                params[key] = ""

        if self.project:
            obj_sel = self.project.analysis_settings.setdefault("object_selection", {})
            obj_sel["deg_current_result_id"] = self.current_deg_result_id
            self.main_window.project_manager.save_project(self.project)

        self.register_task_owner()
        self.task_runner.run_r_script("07_deg.R", params, result_dir, "Differential Expression")

    def run_step(self):
        self._run_deg()

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        self._handle_deg_finished(result, summary)

    def _handle_deg_finished(self, result, summary: dict[str, Any]):
        comparison_entries = summary.get("comparisons", []) or []
        if isinstance(comparison_entries, dict):
            comparison_entries = [comparison_entries]
        if not comparison_entries:
            comparison_entries = [{
                "comparison_name": str(summary.get("comparison_name", self.current_comparison_name)),
                "n_up": summary.get("n_up", 0),
                "n_down": summary.get("n_down", 0),
            }]
        self.current_comparison_name = str(comparison_entries[-1].get("comparison_name", self.current_comparison_name))
        self.append_log(f"=== DEG finished: {len(comparison_entries)} ===")

        cache = self._deg_result_dir(self.current_deg_result_id) or self._deg_cache_dir()
        figures = getattr(result, "figures", None) or summary.get("figures", [])
        if isinstance(figures, str):
            figures = [figures]
        preview_image = ""
        fig_name_map = {
            "deg_volcano_plot": "DEG Volcano Plot",
            "volcano": "DEG Volcano Plot",
        }
        table_name_map = {
            "deg_results_full": "DEG Full Results",
            "deg_results_significant": "DEG Significant Results",
            "deg_summary_statistics": "DEG Summary Statistics",
            "DEG_full": "DEG Full Results",
            "DEG_sig": "DEG Significant Results",
        }
        def _match_name(stem: str, mapping: dict[str, str]) -> str:
            for key, value in mapping.items():
                if stem == key or stem.startswith(f"{key}_") or stem.endswith(f"_{key}"):
                    return value
            return stem
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache, fig)
            if os.path.isfile(fig_path):
                name = os.path.splitext(os.path.basename(fig_path))[0]
                preview_name = _match_name(name, fig_name_map)
                self.main_window.add_preview_item(preview_name, fig_path, "figure", "DEG")
                if name.startswith("deg_volcano_plot_") or name.startswith("volcano_"):
                    preview_image = fig_path

        tables = summary.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        self.current_deg_full_csv = ""
        self.current_deg_sig_csv = ""
        for tbl in tables:
            tbl_path = tbl if os.path.isabs(tbl) else os.path.join(cache, tbl)
            if os.path.isfile(tbl_path):
                name = os.path.splitext(os.path.basename(tbl_path))[0]
                preview_name = _match_name(name, table_name_map)
                self.main_window.add_preview_item(preview_name, tbl_path, "table", "DEG")
                if name.startswith("deg_results_full_") or name.startswith("DEG_full_"):
                    self.current_deg_full_csv = tbl_path
                if name.startswith("deg_results_significant_") or name.startswith("DEG_sig_"):
                    self.current_deg_sig_csv = tbl_path

        if preview_image:
            self.main_window.show_preview_image(preview_image, f"DEG Volcano Plot - {self.current_comparison_name}")

        for item in list(getattr(self.project, "deg_results", []) or []):
            if str(item.get("result_id", "")) == str(self.current_deg_result_id):
                item["status"] = "done"
                item["display_name"] = str(summary.get("result_name", item.get("display_name", comparison)) or comparison)
                item["n_up"] = int(summary.get("n_up", 0) or 0)
                item["n_down"] = int(summary.get("n_down", 0) or 0)
                item["n_genes_tested"] = int(summary.get("n_genes_tested", 0) or 0)
                break
        self.main_window.project_manager.save_project(self.project)
        self._refresh_deg_history_table()
        self._save_deg_context()
        self.project.step_status["deg"] = "done"
        idx = self.main_window.get_step_index("deg")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

    def on_step_error(self, step, summary, detail):
        for item in list(getattr(self.project, "deg_results", []) or []):
            if str(item.get("result_id", "")) == str(self.current_deg_result_id):
                item["status"] = "failed"
                break
        if self.project:
            self.main_window.project_manager.save_project(self.project)
            self._refresh_deg_history_table()
        QMessageBox.warning(self, "Differential Expression Failed", summary)
