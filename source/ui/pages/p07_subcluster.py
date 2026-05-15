"""Subcluster analysis: extract selected main cell types, recluster them, and annotate subtypes."""
import os
import json
import csv
import time
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox,
    QFileDialog, QHeaderView, QLabel, QListWidget, QInputDialog,
    QListWidgetItem, QToolButton, QComboBox,
)
from PySide6.QtCore import Qt, QTimer
from ui.pages.base_page import BasePage
from ui.help_content import build_step_help


class SubclusterPage(BasePage):
    STEP_ID = "subcluster"
    STEP_NAME = "⑦ Subcluster Analysis"
    MANUAL_METHODS = [
        (
            "manual",
            "Manual marker annotation",
            "Manual marker annotation based on subtype marker panels and marker-overlap cluster mapping.",
        ),
        (
            "scina",
            "SCINA",
            "Semi-supervised marker-based annotation. marker panel automatically converted SCINA signature lists.",
        ),
        (
            "cellassign",
            "CellAssign",
            "Probabilistic marker-based annotation. marker panel automatically converted marker gene × subtype matrix, counts.",
        ),
    ]

    DEFAULT_SUB_HVG = 2000
    DEFAULT_SUB_NPCS = 30
    DEFAULT_SUB_DIMS = "1:10"
    DEFAULT_SUB_RESOLUTION = 0.3
    ANNOTATION_PRESETS = {
        "Conservative": {"min_pct": 0.25, "logfc": 0.25},
        "Relaxed": {"min_pct": 0.05, "logfc": 0.10},
        "Force assignment": {"min_pct": 0.05, "logfc": 0.10},
    }

    def __init__(self, **kwargs):
        self._gene_list = []
        self._custom_markers = {}
        self._markers_found = False
        self._subset_done = False
        self._auto_plot_after_annotation = False
        super().__init__(**kwargs)

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp_manage = QGroupBox("Subcluster Results")
        fm = QFormLayout(grp_manage)
        self.cmb_result = QComboBox()
        self.cmb_result.currentIndexChanged.connect(self._on_result_changed)
        self.btn_refresh_results = QPushButton("Result List")
        self.btn_refresh_results.clicked.connect(self._refresh_result_list)
        self.btn_delete_result = QPushButton("Delete Result")
        self.btn_delete_result.clicked.connect(self._delete_current_result)
        result_row = QHBoxLayout()
        result_row.addWidget(self.cmb_result, 1)
        result_row.addWidget(self.btn_refresh_results)
        result_row.addWidget(self.btn_delete_result)
        result_wrap = QWidget()
        result_wrap.setLayout(result_row)
        fm.addRow("Results:", result_wrap)

        self.edit_result_name = QLineEdit()
        self.edit_result_name.setPlaceholderText("Subcluster result name (optional)")
        fm.addRow("Result name:", self.edit_result_name)

        self.lbl_result_status = QLabel("No subcluster result is available for this project yet.")
        self.lbl_result_status.setWordWrap(True)
        self.lbl_result_status.setStyleSheet("color:#666; font-size:11px;")
        fm.addRow("", self.lbl_result_status)
        layout.addWidget(grp_manage)

        grp_a = QGroupBox("Step A — Cell Type")
        fa = QFormLayout(grp_a)

        cell_sel_wrap = QVBoxLayout()
        self.txt_celltype_filter = QLineEdit()
        self.txt_celltype_filter.setPlaceholderText("Filter cell types, e.g. astro / oligo...")
        self.txt_celltype_filter.textChanged.connect(self._filter_target_celltypes)
        cell_sel_wrap.addWidget(self.txt_celltype_filter)

        self.lst_celltype = QListWidget()
        self.lst_celltype.setSelectionMode(QListWidget.MultiSelection)
        self.lst_celltype.setMinimumHeight(220)
        self.lst_celltype.setMaximumHeight(320)
        self.lst_celltype.itemSelectionChanged.connect(self._update_target_summary)
        cell_sel_wrap.addWidget(self.lst_celltype)

        self.lbl_target_summary = QLabel("0 cell types selected")
        cell_sel_wrap.addWidget(self.lbl_target_summary)
        fa.addRow("Target cell types:", cell_sel_wrap)

        self.spn_res = QDoubleSpinBox()
        self.spn_res.setRange(0.05, 3.0)
        self.spn_res.setDecimals(2)
        self.spn_res.setSingleStep(0.1)
        self.spn_res.setValue(self.DEFAULT_SUB_RESOLUTION)
        fa.addRow("Subcluster clustering resolution:", self.spn_res)

        self.lbl_subcluster_reco = QLabel(
            "Recommended defaults: HVG 2000, PCA 30, dims 1:10. "
            "Adjust these settings after reviewing subcluster marker results."
        )
        self.lbl_subcluster_reco.setWordWrap(True)
        self.lbl_subcluster_reco.setStyleSheet("color:#5F6B7A; font-size:11px;")
        fa.addRow("", self.lbl_subcluster_reco)

        self.btn_toggle_advanced = QToolButton()
        self.btn_toggle_advanced.setText("Advanced Parameters")
        self.btn_toggle_advanced.setCheckable(True)
        self.btn_toggle_advanced.setChecked(False)
        self.btn_toggle_advanced.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_toggle_advanced.setArrowType(Qt.RightArrow)
        self.btn_toggle_advanced.toggled.connect(self._toggle_advanced_params)
        fa.addRow("", self.btn_toggle_advanced)

        self.advanced_box = QGroupBox("Advanced Parameters")
        self.advanced_box.setVisible(False)
        form_adv = QFormLayout(self.advanced_box)

        self.spn_hvg = QSpinBox()
        self.spn_hvg.setRange(500, 10000)
        self.spn_hvg.setValue(self.DEFAULT_SUB_HVG)

        self.spn_npcs = QSpinBox()
        self.spn_npcs.setRange(5, 100)
        self.spn_npcs.setValue(self.DEFAULT_SUB_NPCS)

        self.txt_dims = QLineEdit(self.DEFAULT_SUB_DIMS)
        self.txt_dims.editingFinished.connect(self._sync_npcs_with_dims)

        self.lbl_advanced_hint = QLabel(
            "Increase HVGs or PCs for larger subclusters; adjust dims to control the PCs used for clustering."
        )
        self.lbl_advanced_hint.setWordWrap(True)
        self.lbl_advanced_hint.setStyleSheet("color:#5F6B7A; font-size:11px;")

        self.btn_restore_advanced = QPushButton("Restore Advanced Defaults")
        self.btn_restore_advanced.clicked.connect(self._restore_advanced_defaults)

        form_adv.addRow("HVG (nfeatures):", self.spn_hvg)
        form_adv.addRow("PCA (npcs):", self.spn_npcs)
        form_adv.addRow("PCs for clustering (dims):", self.txt_dims)
        form_adv.addRow("", self.lbl_advanced_hint)
        form_adv.addRow("", self.btn_restore_advanced)
        fa.addRow("", self.advanced_box)

        a_p3 = QHBoxLayout()
        self.chk_umap = QCheckBox("UMAP")
        self.chk_umap.setChecked(True)
        self.chk_tsne = QCheckBox("t-SNE")
        self.chk_tsne.setChecked(False)
        self.chk_umap.setEnabled(False)
        self.chk_tsne.setEnabled(False)
        a_p3.addWidget(QLabel("Embeddings:"))
        a_p3.addWidget(self.chk_umap)
        a_p3.addWidget(self.chk_tsne)
        a_p3.addStretch()
        fa.addRow("", a_p3)

        self.lbl_reduction_hint = QLabel("")
        self.lbl_reduction_hint.setStyleSheet("color:#666; font-size:11px;")
        self.lbl_reduction_hint.setWordWrap(True)
        fa.addRow("", self.lbl_reduction_hint)

        self.btn_subset = QPushButton("🔬 Run Subcluster Clustering")
        self.btn_subset.setProperty("role", "accent")
        self.btn_subset.clicked.connect(self._run_subset)

        self.lbl_subset_status = QLabel("Please finish main annotation first.")
        self.lbl_subset_status.setStyleSheet("color: #FF9800;")

        fa.addRow("", self.btn_subset)
        fa.addRow("", self.lbl_subset_status)
        layout.addWidget(grp_a)

        grp_b = QGroupBox("Step B — Subcluster Markers")
        fb = QFormLayout(grp_b)

        self.cmb_annotation_profile = QComboBox()
        self.cmb_annotation_profile.addItems(list(self.ANNOTATION_PRESETS.keys()))
        self.cmb_annotation_profile.currentTextChanged.connect(self._on_annotation_profile_changed)
        fb.addRow("Annotation:", self.cmb_annotation_profile)

        self.spn_min_pct = QDoubleSpinBox()
        self.spn_min_pct.setRange(0, 1)
        self.spn_min_pct.setDecimals(2)
        self.spn_min_pct.setValue(0.25)
        fb.addRow("min.pct:", self.spn_min_pct)

        self.spn_logfc = QDoubleSpinBox()
        self.spn_logfc.setRange(0, 5)
        self.spn_logfc.setDecimals(2)
        self.spn_logfc.setValue(0.25)
        fb.addRow("logfc:", self.spn_logfc)

        self.btn_find = QPushButton("🔍 Subcluster Markers")
        self.btn_find.setProperty("role", "primary")
        self.btn_find.clicked.connect(self._find_markers)
        fb.addRow("", self.btn_find)

        self.lbl_profile_hint = QLabel("")
        self.lbl_profile_hint.setWordWrap(True)
        self.lbl_profile_hint.setStyleSheet("color:#666; font-size:11px;")
        fb.addRow("", self.lbl_profile_hint)

        self.lbl_markers = QLabel("")
        self.lbl_markers.setStyleSheet("color: #888;")
        fb.addRow("", self.lbl_markers)
        layout.addWidget(grp_b)

        grp_c = QGroupBox("Step C — Subcluster Annotation")
        sc = QVBoxLayout(grp_c)

        imp_row = QHBoxLayout()
        self.btn_import = QPushButton("📥 CSV/XLSX")
        self.btn_import.clicked.connect(self._import_file)
        self.btn_export = QPushButton("📤 Export CSV")
        self.btn_export.clicked.connect(self._export_csv)
        imp_row.addWidget(self.btn_import)
        imp_row.addWidget(self.btn_export)
        imp_row.addStretch()
        sc.addLayout(imp_row)

        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Annotation method:"))
        self.cmb_manual_method = QComboBox()
        for method_key, label, _desc in self.MANUAL_METHODS:
            self.cmb_manual_method.addItem(label, method_key)
        self.cmb_manual_method.currentIndexChanged.connect(self._refresh_manual_method_ui)
        method_row.addWidget(self.cmb_manual_method, 1)
        sc.addLayout(method_row)

        self.lbl_manual_method_info = QLabel("")
        self.lbl_manual_method_info.setWordWrap(True)
        self.lbl_manual_method_info.setStyleSheet("color:#5F6B7A; font-size:11px;")
        sc.addWidget(self.lbl_manual_method_info)

        cols = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Subtype Lists:"))
        self.lst_ct = QListWidget()
        self.lst_ct.currentRowChanged.connect(self._on_ct_sel)
        left.addWidget(self.lst_ct)
        ct_btns = QHBoxLayout()
        btn_add = QPushButton("➕")
        btn_del = QPushButton("🗑")
        btn_add.clicked.connect(self._add_ct)
        btn_del.clicked.connect(self._del_ct)
        ct_btns.addWidget(btn_add)
        ct_btns.addWidget(btn_del)
        left.addLayout(ct_btns)
        cols.addLayout(left, 2)

        mid = QVBoxLayout()
        self.lbl_ct = QLabel("← Subtype")
        self.lbl_ct.setStyleSheet("font-weight: bold;")
        mid.addWidget(self.lbl_ct)
        self.lst_markers = QListWidget()
        mid.addWidget(self.lst_markers)
        btn_rm = QPushButton("Remove")
        btn_rm.clicked.connect(self._rm_marker)
        mid.addWidget(btn_rm)
        cols.addLayout(mid, 2)

        right = QVBoxLayout()
        right.addWidget(QLabel("genes:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search genes, e.g. Mbp, Pdgfra...")
        self.txt_search.textChanged.connect(self._on_search)
        right.addWidget(self.txt_search)
        self.lbl_search = QLabel("")
        self.lbl_search.setStyleSheet("color:#888;font-size:11px;")
        right.addWidget(self.lbl_search)
        self.lst_cand = QListWidget()
        self.lst_cand.itemDoubleClicked.connect(self._add_gene)
        right.addWidget(self.lst_cand)
        cols.addLayout(right, 3)

        sc.addLayout(cols)
        layout.addWidget(grp_c)

        grp_d = QGroupBox("Step D — Results")
        sd = QVBoxLayout(grp_d)
        self.mapping_table = QTableWidget()
        self.mapping_table.setColumnCount(2)
        self.mapping_table.setHorizontalHeaderLabels(["Cluster", "Subtype"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.mapping_table.setMinimumHeight(280)
        self.mapping_table.setMaximumHeight(420)
        self.mapping_table.verticalHeader().setDefaultSectionSize(28)
        self.lbl_mapping_hint = QLabel("Notice:Subcluster cluster subtype Results,.")
        self.lbl_mapping_hint.setWordWrap(True)
        self.lbl_mapping_hint.setStyleSheet("color:#666; font-size:11px;")
        sd.addWidget(self.lbl_mapping_hint)
        sd.addWidget(self.mapping_table, 1)
        layout.addWidget(grp_d)

        ex_row = QHBoxLayout()
        self.btn_execute = QPushButton("🏷 Run Annotation + Plot")
        self.btn_execute.setProperty("role", "accent")
        self.btn_execute.clicked.connect(lambda: self._execute(plot_after=True))
        ex_row.addWidget(self.btn_execute)

        self.btn_annotation_only = QPushButton("📝 Annotation Only")
        self.btn_annotation_only.setProperty("role", "primary")
        self.btn_annotation_only.clicked.connect(lambda: self._execute(plot_after=False))
        ex_row.addWidget(self.btn_annotation_only)

        self.btn_generate_plots = QPushButton("🖼 Plot Only")
        self.btn_generate_plots.setProperty("role", "ghost")
        self.btn_generate_plots.clicked.connect(self._gen_umap)
        ex_row.addWidget(self.btn_generate_plots)
        ex_row.addStretch()
        layout.addLayout(ex_row)

        self.bind_help_refresh(
            self.txt_celltype_filter,
            self.lst_celltype,
            self.spn_res,
            self.btn_toggle_advanced,
            self.spn_hvg,
            self.spn_npcs,
            self.txt_dims,
            self.cmb_annotation_profile,
            self.spn_min_pct,
            self.spn_logfc,
            self.cmb_manual_method,
        )
        self._apply_annotation_profile(self.cmb_annotation_profile.currentText(), force=True)
        self._refresh_manual_method_ui()
        return container

    def _apply_annotation_profile(self, profile_name: str, force: bool = False):
        preset = self.ANNOTATION_PRESETS.get(profile_name, self.ANNOTATION_PRESETS["Conservative"])
        if force or abs(self.spn_min_pct.value() - preset["min_pct"]) < 1e-9:
            self.spn_min_pct.setValue(preset["min_pct"])
        if force or abs(self.spn_logfc.value() - preset["logfc"]) < 1e-9:
            self.spn_logfc.setValue(preset["logfc"])

        if profile_name == "Force assignment":
            self.lbl_profile_hint.setText(
                "Force-assignment mode tries to assign the closest subtype to every subcluster and avoids Unknown labels. "
                "Please review marker evidence and the subcluster UMAP carefully because this mode can over-assign labels."
            )
        elif profile_name == "Relaxed":
            self.lbl_profile_hint.setText("Relaxed mode uses lower marker thresholds to reduce Unknown subtype labels.")
        else:
            self.lbl_profile_hint.setText("Conservative mode uses more stringent marker thresholds and is recommended as the default.")

    def _on_annotation_profile_changed(self, profile_name: str):
        self._apply_annotation_profile(profile_name, force=True)
        self.refresh_help()

    def _manual_method_key(self) -> str:
        return str(self.cmb_manual_method.currentData() or "manual")

    def _manual_method_label(self) -> str:
        return str(self.cmb_manual_method.currentText() or "Manual marker annotation")

    def _refresh_manual_method_ui(self):
        method_key = self._manual_method_key()
        method_desc = ""
        for key, _label, desc in self.MANUAL_METHODS:
            if key == method_key:
                method_desc = desc
                break
        if method_key == "manual":
            extra = "Manual marker mode uses your marker panel and cluster marker overlap."
        elif method_key == "scina":
            extra = "SCINA requires the local R runtime to provide the SCINA package and a valid subcluster object."
        else:
            extra = "CellAssign requires the local R/Python runtime and a valid subcluster object."
        self.lbl_manual_method_info.setText(method_desc + "\n" + extra)
        self.refresh_help()

    def _toggle_advanced_params(self, checked: bool):
        self.advanced_box.setVisible(checked)
        self.btn_toggle_advanced.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.btn_toggle_advanced.setText(
            "Parameters / " if checked else "Parameters / "
        )
        self.refresh_help()

    def _restore_advanced_defaults(self):
        self.spn_hvg.setValue(self.DEFAULT_SUB_HVG)
        self.spn_npcs.setValue(self.DEFAULT_SUB_NPCS)
        self.txt_dims.setText(self.DEFAULT_SUB_DIMS)
        self.refresh_help()

    def _parse_dims_upper(self, dims_text: str) -> int:
        text = (dims_text or "").strip()
        if not text:
            raise ValueError("dims is empty")
        if ":" in text:
            start_text, end_text = text.split(":", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start <= 0 or end < start:
                raise ValueError("dims must be positive and ordered")
            return end
        values = [int(token.strip()) for token in text.replace(";", ",").split(",") if token.strip()]
        if not values:
            raise ValueError("dims is empty")
        if min(values) <= 0:
            raise ValueError("dims ")
        return max(values)

    def _sync_npcs_with_dims(self):
        try:
            dims_upper = self._parse_dims_upper(self.txt_dims.text())
        except ValueError:
            return
        if self.spn_npcs.value() < dims_upper:
            self.spn_npcs.setValue(dims_upper)

    def get_params(self) -> dict:
        mapping = {}
        relaxed_mode = self.cmb_annotation_profile.currentText() == "Relaxed"
        for row in range(self.mapping_table.rowCount()):
            cluster_item = self.mapping_table.item(row, 0)
            subtype_item = self.mapping_table.item(row, 1)
            if cluster_item and subtype_item and subtype_item.text().strip():
                mapping[cluster_item.text()] = subtype_item.text().strip()
        group_order = self.main_window.get_group_order() if hasattr(self.main_window, "get_group_order") else []
        reduction = self._get_primary_reduction()
        try:
            dims_upper = self._parse_dims_upper(self.txt_dims.text())
        except ValueError:
            dims_upper = self.spn_npcs.value()
        safe_npcs = max(self.spn_npcs.value(), dims_upper)
        return {
            "target_celltype": [item.text() for item in self.lst_celltype.selectedItems()],
            "resolution": self.spn_res.value(),
            "hvg_number": self.spn_hvg.value(),
            "npcs": safe_npcs,
            "dims": self.txt_dims.text().strip(),
            "run_umap": reduction == "umap",
            "run_tsne": reduction == "tsne",
            "annotation_profile": self.cmb_annotation_profile.currentText(),
            "min_pct": self.spn_min_pct.value(),
            "logfc_threshold": self.spn_logfc.value(),
            "filter_genes": True,
            "cluster_mapping": mapping,
            "custom_markers": self._custom_markers,
            "manual_method": self._manual_method_key(),
            "group_order": group_order,
            "reduction": reduction,
            "result_id": str(self.cmb_result.currentData() or self.get_current_subcluster_result_id() or ""),
            "result_name": self.edit_result_name.text().strip(),
            "seed": self.app_config.default_seed,
            "color_scheme": getattr(self.project, "plot_theme", self.app_config.color_scheme) if self.project else self.app_config.color_scheme,
        }

    def reset_params(self):
        self.spn_res.setValue(self.DEFAULT_SUB_RESOLUTION)
        self.cmb_annotation_profile.setCurrentText("Conservative")
        self._apply_annotation_profile("Conservative", force=True)
        self.cmb_manual_method.setCurrentIndex(0)
        self.txt_celltype_filter.clear()
        self.lst_celltype.clearSelection()
        self.lbl_target_summary.setText("0 cell types selected")
        self._clear_custom_markers()
        self._restore_advanced_defaults()
        self._sync_inherited_reduction()

    def get_help_html(self) -> str:
        return build_step_help("subcluster", {
            "resolution": self.spn_res.value(),
            "hvg_number": self.spn_hvg.value(),
            "npcs": self.spn_npcs.value(),
            "dims": self.txt_dims.text().strip() or self.DEFAULT_SUB_DIMS,
            "annotation_profile": self.cmb_annotation_profile.currentText(),
            "min_pct": self.spn_min_pct.value(),
            "logfc_threshold": self.spn_logfc.value(),
            "manual_method": self._manual_method_label(),
            "reduction": self._get_primary_reduction(),
        })

    def _slugify_targets(self, targets: list[str]) -> str:
        cleaned = []
        for item in targets:
            text = "".join(ch if ch.isalnum() else "_" for ch in str(item or "").strip().lower())
            text = "_".join(filter(None, text.split("_")))
            if text:
                cleaned.append(text)
        if not cleaned:
            return "subcluster"
        return "_".join(cleaned[:2])[:40]

    def _next_result_sequence(self) -> int:
        existing = self.get_subcluster_results()
        max_seq = 0
        for item in existing:
            result_id = str(item.get("result_id", ""))
            tail = result_id.split("_")[-1]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))
        return max_seq + 1

    def _create_subcluster_result_entry(self, selected_targets: list[str]) -> dict:
        sequence = self._next_result_sequence()
        target_slug = self._slugify_targets(selected_targets)
        result_id = f"subcluster_{target_slug}_{sequence:03d}"
        display_name = self.edit_result_name.text().strip() or "+".join(selected_targets) or result_id
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "result_id": result_id,
            "display_name": display_name,
            "target_celltypes": list(selected_targets),
            "created_at": created_at,
            "cache_dir_rel": f"cache/subcluster/results/{result_id}",
            "primary_reduction": self._get_primary_reduction(),
            "status": "running",
            "n_cells": 0,
            "n_clusters": 0,
            "n_subtypes": 0,
            "legacy_root": False,
        }

    def _register_subcluster_result(self, entry: dict):
        if not self.project:
            return
        results = [item for item in self.get_subcluster_results() if str(item.get("result_id", "")) != str(entry.get("result_id", ""))]
        results.append(entry)
        self.project.subcluster_results = results
        self.save_current_subcluster_result_id(str(entry.get("result_id", "")))
        self.main_window.project_manager.save_project(self.project)

    def _delete_current_result(self):
        if not self.require_project():
            return
        entry = self._current_result_entry()
        if not entry:
            QMessageBox.information(self, "Notice", "No current subcluster result is selected.")
            return

        result_id = str(entry.get("result_id", "")).strip()
        display_name = str(entry.get("display_name", "") or result_id).strip() or result_id
        result_dir = self.get_subcluster_result_dir(result_id, ensure=False)

        reply = QMessageBox.question(
            self,
            "Subcluster Results",
            f"Delete the current subcluster result?\n\n"
            f"Result: {display_name}\n"
            f"Result ID: {result_id}\n\n"
            "This will delete the selected subcluster result, including its annotation files and cached object.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if result_dir and os.path.isdir(result_dir):
                shutil.rmtree(result_dir)
        except Exception as exc:
            QMessageBox.warning(self, "Failed", f"Unable to delete the result folder:\n{result_dir}\n\n{exc}")
            return

        remaining = [
            item for item in self.get_subcluster_results()
            if str(item.get("result_id", "")).strip() != result_id
        ]
        self.project.subcluster_results = remaining
        next_id = str(remaining[-1].get("result_id", "")).strip() if remaining else ""
        self.save_current_subcluster_result_id(next_id)
        self.main_window.project_manager.save_project(self.project)

        self.append_log(f"Deleted subcluster result: {display_name} ({result_id})")
        self._refresh_result_list()
        self.refresh_help()
        QMessageBox.information(self, "Finished", f"Deleted subcluster result:\n{display_name}")

    def _current_result_entry(self) -> dict | None:
        result_id = str(self.cmb_result.currentData() or self.get_current_subcluster_result_id() or "")
        return self.get_subcluster_result_by_id(result_id)

    def _current_result_dir(self, ensure: bool = False) -> str:
        entry = self._current_result_entry()
        if not entry:
            return ""
        return self.get_subcluster_result_dir(str(entry.get("result_id", "")), ensure=ensure)

    def _current_result_paths(self) -> dict:
        result_dir = self._current_result_dir()
        if not result_dir:
            return {}
        return {
            "dir": result_dir,
            "summary": os.path.join(result_dir, "summary.json"),
            "subclustered_rds": os.path.join(result_dir, "subclustered.rds"),
            "annotated_rds": os.path.join(result_dir, "sub_annotated.rds"),
            "gene_list": os.path.join(result_dir, "gene_list.txt"),
            "markers_csv": os.path.join(result_dir, "sub_all_markers.csv"),
            "mapping_csv": os.path.join(result_dir, "sub_cluster_mapping.csv"),
            "subtypes_txt": os.path.join(result_dir, "subtypes.txt"),
            "metadata_csv": os.path.join(result_dir, "sub_metadata.csv"),
            "custom_markers_json": os.path.join(result_dir, "custom_markers.json"),
        }

    def _refresh_result_list(self):
        current_id = str(self.get_current_subcluster_result_id() or self.cmb_result.currentData() or "")
        self.cmb_result.blockSignals(True)
        self.cmb_result.clear()
        for entry in self.get_subcluster_results():
            label = str(entry.get("display_name", "") or entry.get("result_id", ""))
            targets = "+".join(entry.get("target_celltypes", []) or [])
            if targets and targets not in label:
                label = f"{label} ({targets})"
            self.cmb_result.addItem(label, str(entry.get("result_id", "")))
        self.cmb_result.blockSignals(False)
        if self.cmb_result.count() == 0:
            self.lbl_result_status.setText("No subcluster result is available for this project yet.")
            self.lbl_result_status.setStyleSheet("color:#666; font-size:11px;")
            self.btn_delete_result.setEnabled(False)
            return
        idx = self.cmb_result.findData(current_id)
        if idx < 0:
            idx = self.cmb_result.count() - 1
        self.cmb_result.setCurrentIndex(idx)
        self.btn_delete_result.setEnabled(True)
        self._on_result_changed(idx)

    def _load_mapping_from_current_result(self):
        paths = self._current_result_paths()
        self.mapping_table.setRowCount(0)
        if not paths or not os.path.isfile(paths["mapping_csv"]):
            return
        try:
            with open(paths["mapping_csv"], "r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.mapping_table.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                cluster_value = str(row.get("cluster", "") or row.get("Cluster", "")).strip()
                subtype_value = str(row.get("subtype", "") or row.get("Subtype", "") or row.get("label", "")).strip()
                cluster_item = QTableWidgetItem(cluster_value)
                cluster_item.setFlags(cluster_item.flags() & ~Qt.ItemIsEditable)
                self.mapping_table.setItem(row_idx, 0, cluster_item)
                self.mapping_table.setItem(row_idx, 1, QTableWidgetItem(subtype_value))
        except Exception:
            self.mapping_table.setRowCount(0)

    def _on_result_changed(self, _idx: int):
        result_id = str(self.cmb_result.currentData() or "")
        if result_id:
            self.save_current_subcluster_result_id(result_id)
        entry = self._current_result_entry()
        if not entry:
            self._clear_custom_markers()
            self.mapping_table.setRowCount(0)
            self.lbl_result_status.setText("No subcluster result is available for this project yet.")
            self.lbl_result_status.setStyleSheet("color:#666; font-size:11px;")
            self.btn_delete_result.setEnabled(False)
            return
        self.btn_delete_result.setEnabled(True)
        self._load_custom()
        self._load_mapping_from_current_result()
        self._try_genes()
        n_cells = int(entry.get("n_cells", 0) or 0)
        n_clusters = int(entry.get("n_clusters", 0) or 0)
        n_subtypes = int(entry.get("n_subtypes", 0) or 0)
        reduction = str(entry.get("primary_reduction", "") or "").upper() or "UMAP"
        self.lbl_result_status.setText(
            f"Result: {entry.get('display_name', result_id)} | cells {n_cells} | clusters {n_clusters} | subtypes {n_subtypes} | {reduction}"
        )
        self.lbl_result_status.setStyleSheet("color:#2E7D32; font-size:11px;")
        self.refresh_help()

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._restore_task_buttons_if_idle()
        self._clear_custom_markers()
        self._refresh_celltypes()
        self._refresh_result_list()
        self._sync_inherited_reduction()
        self.refresh_help()

    def on_page_entered(self):
        self._restore_task_buttons_if_idle()
        self._refresh_celltypes()
        self._refresh_result_list()
        self._try_genes()
        self._sync_inherited_reduction()
        self.refresh_help()

    def _get_primary_reduction(self):
        if not self.project:
            return "umap"
        current_entry = self._current_result_entry()
        if current_entry:
            reduction = str(current_entry.get("primary_reduction", "") or "").strip().lower()
            if reduction in ("umap", "tsne"):
                return reduction
        reduction_file = os.path.join(self.project.cache_subdir("clustering"), "primary_reduction.txt")
        if os.path.exists(reduction_file):
            try:
                with open(reduction_file, "r", encoding="utf-8") as handle:
                    reduction = handle.read().strip().lower()
                if reduction in ("umap", "tsne"):
                    return reduction
            except Exception:
                pass
        return "umap"

    def _sync_inherited_reduction(self):
        reduction = self._get_primary_reduction()
        use_umap = reduction == "umap"
        self.chk_umap.setChecked(use_umap)
        self.chk_tsne.setChecked(not use_umap)
        self.lbl_reduction_hint.setText(
            f"Using inherited reduction: {reduction.upper()}. Continue with subcluster clustering and annotation."
        )
        self.refresh_help()

    def _refresh_celltypes(self):
        self.lst_celltype.clear()
        if not self.project:
            self.refresh_help()
            return
        cache = self.project.cache_subdir("annotation")
        cell_types = []

        cell_type_file = os.path.join(cache, "cell_types.txt")
        if os.path.exists(cell_type_file):
            try:
                with open(cell_type_file, "r", encoding="utf-8") as handle:
                    cell_types = [line.strip() for line in handle if line.strip()]
            except Exception:
                pass

        if not cell_types:
            summary_path = os.path.join(cache, "summary.json")
            if os.path.exists(summary_path):
                try:
                    with open(summary_path, "r", encoding="utf-8") as handle:
                        summary = json.load(handle)
                    cell_types = summary.get("cell_types", [])
                    if isinstance(cell_types, str):
                        cell_types = [cell_types]
                except Exception:
                    pass

        for cell_type in cell_types:
            item = QListWidgetItem(cell_type)
            item.setToolTip(cell_type)
            self.lst_celltype.addItem(item)
        if cell_types:
            self.lbl_subset_status.setText(f"✓ {len(cell_types)} type")
            self.lbl_subset_status.setStyleSheet("color: #4CAF50;")
        else:
            self.lbl_subset_status.setText("Please finish main annotation first.")
            self.lbl_subset_status.setStyleSheet("color: #FF9800;")
        self.refresh_help()

    def _try_genes(self):
        if not self.project:
            return
        paths = self._current_result_paths()
        gene_file = paths.get("gene_list", "") if paths else ""
        if not gene_file or not os.path.exists(gene_file):
            gene_file = os.path.join(self.project.cache_subdir("annotation"), "gene_list.txt")
        if os.path.exists(gene_file):
            try:
                with open(gene_file, "r", encoding="utf-8") as handle:
                    self._gene_list = [line.strip() for line in handle if line.strip()]
                self.lbl_search.setText(f"✓ {len(self._gene_list)} genes")
            except Exception:
                pass

    def _load_custom(self):
        if not self.project:
            return
        path = self._current_result_paths().get("custom_markers_json", "")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    self._custom_markers = json.load(handle)
                self._refresh_ct()
            except Exception:
                pass
        else:
            self._clear_custom_markers()

    def _save_custom(self):
        if not self.project:
            return
        path = self._current_result_paths().get("custom_markers_json", "")
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self._custom_markers, handle, indent=2, ensure_ascii=False)

    def _filter_target_celltypes(self, text: str):
        key = (text or "").strip().lower()
        for i in range(self.lst_celltype.count()):
            item = self.lst_celltype.item(i)
            item.setHidden(bool(key) and key not in item.text().lower())

    def _update_target_summary(self):
        selected = [item.text() for item in self.lst_celltype.selectedItems()]
        if selected:
            preview = ", ".join(selected[:3])
            if len(selected) > 3:
                preview += f" {len(selected)} "
            self.lbl_target_summary.setText(f"{len(selected)} selected: {preview}")
        else:
            self.lbl_target_summary.setText("0 cell types selected")
        self.refresh_help()

    def _run_subset(self):
        if not self.require_project():
            return
        adjust_msg = ""
        selected = [item.text() for item in self.lst_celltype.selectedItems()]
        if not selected:
            QMessageBox.warning(self, "Notice", " Cell Type().")
            return
        try:
            dims_upper = self._parse_dims_upper(self.txt_dims.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Notice", f"dims format:{exc}\nSuggestion 1:10 1,2,3 format.")
            return
        if self.spn_npcs.value() < dims_upper:
            self.spn_npcs.setValue(dims_upper)
            adjust_msg = f"PCA components were increased to {dims_upper} to match dims={self.txt_dims.text().strip()}."

        celltype_label = "+".join(selected)
        annotated_rds = os.path.join(
            self.project.cache_subdir("annotation"), "annotated.rds"
        ).replace("\\", "/")
        if not os.path.isfile(annotated_rds):
            QMessageBox.warning(self, "Notice", "Please finish main annotation first.")
            return

        self.clear_log()
        self.btn_subset.setText("⏳ Extracting subcluster...")
        self.btn_subset.setEnabled(False)
        self.append_log(f"=== Subcluster: {celltype_label} ===")
        if adjust_msg:
            self.append_log(adjust_msg)

        result_entry = self._create_subcluster_result_entry(selected)
        self._register_subcluster_result(result_entry)
        self._refresh_result_list()
        result_dir = self.get_subcluster_result_dir(result_entry["result_id"], ensure=True)
        self.append_log(f"Results will be saved as: {result_entry['display_name']} ({result_entry['result_id']})")

        params = self.get_params()
        params["input_rds"] = annotated_rds
        params["cache_dir"] = result_dir.replace("\\", "/")
        params["action"] = "subset_and_cluster"

        self.register_task_owner()
        self.task_runner.run_r_script(
            "08_subcluster.R",
            params,
            result_dir,
            "Subcluster",
        )

    def _find_markers(self):
        if not self.require_project():
            return
        paths = self._current_result_paths()
        sub_rds = paths.get("subclustered_rds", "").replace("\\", "/") if paths else ""
        if not os.path.isfile(sub_rds):
            QMessageBox.warning(self, "Notice", "finished Step A.")
            return

        self.btn_find.setText("⏳ Finding subcluster markers...")
        self.btn_find.setEnabled(False)
        self.append_log("=== Subcluster Markers ===")

        params = self.get_params()
        params["input_rds"] = sub_rds
        params["cache_dir"] = self._current_result_dir(ensure=True).replace("\\", "/")
        params["action"] = "find_markers"

        self.register_task_owner()
        self.task_runner.run_r_script(
            "08_subcluster.R",
            params,
            self._current_result_dir(ensure=True),
            "Subcluster Markers",
        )

    def _add_ct(self):
        name, ok = QInputDialog.getText(self, " Subtype", ":")
        if ok and name.strip():
            name = name.strip()
            if name in self._custom_markers:
                QMessageBox.warning(self, "Notice", f"'{name}' exists.")
                return
            self._custom_markers[name] = []
            self.lst_ct.addItem(name)
            self.lst_ct.setCurrentRow(self.lst_ct.count() - 1)

    def _del_ct(self):
        row = self.lst_ct.currentRow()
        if row < 0:
            return
        name = self.lst_ct.item(row).text()
        if QMessageBox.question(self, "Notice", f"Delete subtype '{name}'?") == QMessageBox.Yes:
            self._custom_markers.pop(name, None)
            self.lst_ct.takeItem(row)
            self.lst_markers.clear()

    def _on_ct_sel(self, row):
        if row < 0:
            self.lst_markers.clear()
            self.lbl_ct.setText("← Subtype")
            return
        subtype = self.lst_ct.item(row).text()
        self.lbl_ct.setText(subtype)
        self.lst_markers.clear()
        for gene in self._custom_markers.get(subtype, []):
            self.lst_markers.addItem(gene)

    def _rm_marker(self):
        current_row, marker_row = self.lst_ct.currentRow(), self.lst_markers.currentRow()
        if current_row < 0 or marker_row < 0:
            return
        subtype = self.lst_ct.item(current_row).text()
        gene = self.lst_markers.item(marker_row).text()
        self._custom_markers[subtype].remove(gene)
        self.lst_markers.takeItem(marker_row)

    def _on_search(self, text):
        self.lst_cand.clear()
        if not text.strip() or not self._gene_list:
            return
        query = text.strip().lower()
        prefix_hits = [gene for gene in self._gene_list if gene.lower().startswith(query)]
        contains_hits = [gene for gene in self._gene_list if query in gene.lower() and gene not in prefix_hits]
        for gene in (prefix_hits[:50] + contains_hits[:50]):
            self.lst_cand.addItem(gene)

    def _add_gene(self, item):
        current_row = self.lst_ct.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Notice", " Subtype.")
            return
        subtype = self.lst_ct.item(current_row).text()
        gene = item.text()
        if gene in self._custom_markers.get(subtype, []):
            return
        self._custom_markers[subtype].append(gene)
        self.lst_markers.addItem(gene)

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "", "", "CSV/XLSX (*.csv *.xlsx)")
        if not path:
            return
        try:
            imported, not_found = {}, []
            with open(path, "r", encoding="utf-8-sig") as handle:
                for row in csv.reader(handle):
                    if len(row) >= 2:
                        subtype, gene = row[0].strip(), row[1].strip()
                        if subtype.lower() in ("celltype", "cell_type", "subtype") and gene.lower() in ("marker", "gene"):
                            continue
                        if subtype and gene:
                            if self._gene_list and gene not in self._gene_list:
                                not_found.append(gene)
                                continue
                            imported.setdefault(subtype, [])
                            if gene not in imported[subtype]:
                                imported[subtype].append(gene)
            for subtype, genes in imported.items():
                if subtype not in self._custom_markers:
                    self._custom_markers[subtype] = []
                for gene in genes:
                    if gene not in self._custom_markers[subtype]:
                        self._custom_markers[subtype].append(gene)
            self._refresh_ct()
            message = f"Imported marker sets for {len(imported)} subtypes"
            if not_found:
                message += f"\n\n⚠ {len(not_found)} genes were not found in the current object"
            QMessageBox.information(self, "finished", message)
        except Exception as exc:
            QMessageBox.critical(self, "Failed", str(exc))

    def _export_csv(self):
        if not self._custom_markers:
            QMessageBox.warning(self, "Notice", ".")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", "sub_markers.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["subtype", "gene"])
            for subtype, genes in self._custom_markers.items():
                for gene in genes:
                    writer.writerow([subtype, gene])

    def _refresh_ct(self):
        self.lst_ct.clear()
        for subtype in self._custom_markers:
            self.lst_ct.addItem(subtype)

    def _clear_custom_markers(self):
        self._custom_markers = {}
        self.lst_ct.clear()
        self.lst_markers.clear()
        self.lst_cand.clear()
        self.lbl_ct.setText("→ Subtype")

    def _populate_map(self, cluster_ids):
        self.mapping_table.setRowCount(len(cluster_ids))
        for row, cluster_id in enumerate(cluster_ids):
            item = QTableWidgetItem(str(cluster_id))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.mapping_table.setItem(row, 0, item)
            existing = self.mapping_table.item(row, 1)
            if not existing or not existing.text().strip():
                self.mapping_table.setItem(row, 1, QTableWidgetItem(f"Sub_{cluster_id}"))

    def _restore_task_buttons_if_idle(self):
        if getattr(self.task_runner, "is_running", False):
            return
        self.btn_subset.setText("🔬 Clustering")
        self.btn_subset.setEnabled(True)
        self.btn_find.setText("🔍 Subcluster Markers")
        self.btn_find.setEnabled(True)
        self.btn_execute.setText("🏷 Run Annotation + Plot")
        self.btn_execute.setEnabled(True)
        self.btn_annotation_only.setText("📝 Annotation Only")
        self.btn_annotation_only.setEnabled(True)
        self.btn_generate_plots.setText("🖼 Plot Only")
        self.btn_generate_plots.setEnabled(True)

    def _execute(self, plot_after: bool = False):
        self._auto_plot_after_annotation = bool(plot_after)
        if not self.require_project():
            return
        if not self._custom_markers:
            QMessageBox.warning(self, "Notice", " Subtype Marker.")
            return

        markers_csv = self._current_result_paths().get("markers_csv", "")
        if not os.path.exists(markers_csv):
            QMessageBox.warning(self, "Notice", "finished Step B.")
            return

        method_key = self._manual_method_key()
        if method_key in {"scina", "cellassign"}:
            self._save_custom()
            self.btn_execute.setText(f"⏳ Running {self._manual_method_label()}...")
            self.btn_execute.setEnabled(False)
            self.btn_annotation_only.setEnabled(False)
            self.btn_generate_plots.setEnabled(False)
            self._run_manual_r_method(method_key)
            return

        cluster_genes = {}
        with open(markers_csv, "r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                cluster_id = str(row.get("cluster", ""))
                cluster_genes.setdefault(cluster_id, []).append(row.get("gene", ""))

        profile_name = self.cmb_annotation_profile.currentText()
        relaxed_mode = profile_name == "Relaxed"
        force_assign_mode = profile_name == "Force assignment"
        for row in range(self.mapping_table.rowCount()):
            item = self.mapping_table.item(row, 0)
            if not item:
                continue
            cluster_id = item.text()
            genes = cluster_genes.get(cluster_id, [])
            overlap_scores = []
            for subtype, markers in self._custom_markers.items():
                overlap = len(set(genes) & set(markers))
                overlap_scores.append((subtype, overlap))
            if not overlap_scores:
                best_name = sorted(self._custom_markers.keys())[0] if force_assign_mode and self._custom_markers else "Unknown"
            else:
                overlap_scores.sort(key=lambda x: (-x[1], x[0]))
                best_name, best_overlap = overlap_scores[0]
                if best_overlap <= 0 and not relaxed_mode and not force_assign_mode:
                    best_name = "Unknown"
            self.mapping_table.setItem(row, 1, QTableWidgetItem(best_name))

        self._save_custom()
        if force_assign_mode:
            self.append_log("Force-assignment mode generated candidate subtype labels for all available clusters.")
        self.btn_execute.setText("⏳ Applying subcluster annotation...")
        self.btn_execute.setEnabled(False)
        self.btn_annotation_only.setEnabled(False)
        self.btn_generate_plots.setEnabled(False)
        self._apply_annotation()

    def _run_manual_r_method(self, method_key: str):
        paths = self._current_result_paths()
        sub_rds = paths.get("subclustered_rds", "").replace("\\", "/") if paths else ""
        if not os.path.isfile(sub_rds):
            QMessageBox.warning(self, "Notice", "Please finish subcluster clustering first.")
            self._restore_task_buttons_if_idle()
            return
        params = self.get_params()
        params["input_rds"] = sub_rds
        params["cache_dir"] = self._current_result_dir(ensure=True).replace("\\", "/")
        params["action"] = "scina_annotate" if method_key == "scina" else "cellassign_annotate"
        method_label = "SCINA" if method_key == "scina" else "CellAssign"
        self.register_task_owner()
        self.task_runner.run_r_script(
            "08_subcluster.R",
            params,
            self._current_result_dir(ensure=True),
            f"Subcluster {method_label} Annotation",
        )

    def _apply_annotation(self):
        params = self.get_params()
        if not params["cluster_mapping"]:
            QMessageBox.warning(self, "Notice", "Cluster-to-subtype mapping is empty. Please assign subtypes first.")
            return
        paths = self._current_result_paths()
        sub_rds = paths.get("subclustered_rds", "").replace("\\", "/") if paths else ""
        params["input_rds"] = sub_rds
        params["cache_dir"] = self._current_result_dir(ensure=True).replace("\\", "/")
        params["action"] = "apply_annotation"
        self.register_task_owner()
        self.task_runner.run_r_script(
            "08_subcluster.R",
            params,
            self._current_result_dir(ensure=True),
            "Subcluster Annotation",
        )

    def _gen_umap(self):
        paths = self._current_result_paths()
        sub_rds = paths.get("annotated_rds", "").replace("\\", "/") if paths else ""
        if not os.path.isfile(sub_rds):
            return
        params = self.get_params()
        params["input_rds"] = sub_rds
        params["cache_dir"] = self._current_result_dir(ensure=True).replace("\\", "/")
        params["action"] = "generate_plots"
        reduction = params.get("reduction", "umap").upper()
        self.btn_generate_plots.setText("⏳ Generating subcluster plots...")
        self.btn_execute.setEnabled(False)
        self.btn_annotation_only.setEnabled(False)
        self.btn_generate_plots.setEnabled(False)
        self.register_task_owner()
        self.task_runner.run_r_script(
            "08_subcluster.R",
            params,
            self._current_result_dir(ensure=True),
            f"Subcluster {reduction}",
        )

    def _load_gene_list(self):
        self._try_genes()

    def _apply_method_mapping(self, cluster_ids, mapping, method_label: str):
        if cluster_ids:
            self._populate_map([str(x) for x in cluster_ids])
        mapping = {str(k): str(v) for k, v in (mapping or {}).items()}
        for row in range(self.mapping_table.rowCount()):
            cluster_item = self.mapping_table.item(row, 0)
            if not cluster_item:
                continue
            cluster_id = cluster_item.text()
            if cluster_id in mapping:
                self.mapping_table.setItem(row, 1, QTableWidgetItem(mapping[cluster_id]))
        self.append_log(f"{method_label} completed. Please review suggested labels, then apply subcluster annotation.")
        QTimer.singleShot(200, self._apply_annotation)

    def _update_current_result_entry_from_summary(self, summary: dict):
        entry = self._current_result_entry()
        if not entry or not self.project:
            return
        action = str(summary.get("action", "") or "")
        entry["primary_reduction"] = str(summary.get("primary_reduction", entry.get("primary_reduction", self._get_primary_reduction())) or self._get_primary_reduction()).lower()
        if action == "subset_and_cluster":
            entry["status"] = "clustered"
            entry["n_cells"] = int(summary.get("n_cells", entry.get("n_cells", 0)) or 0)
            entry["n_clusters"] = int(summary.get("n_clusters", entry.get("n_clusters", 0)) or 0)
        elif action == "apply_annotation":
            entry["status"] = "annotated"
            subtypes = summary.get("subtypes", []) or []
            if isinstance(subtypes, str):
                subtypes = [subtypes]
            entry["n_subtypes"] = len([x for x in subtypes if str(x).strip()])
        elif action == "generate_plots":
            entry["status"] = "ready"
        elif action in {"scina_annotate", "cellassign_annotate", "find_markers"}:
            entry["status"] = "in_progress"
        self._register_subcluster_result(entry)

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        action = summary.get("action", "")
        self._update_current_result_entry_from_summary(summary)
        if action in {"subset_and_cluster", "find_markers", "apply_annotation", "generate_plots", "scina_annotate", "cellassign_annotate"}:
            self._load_gene_list()

        if action == "subset_and_cluster":
            self.btn_subset.setText("🔬 Clustering")
            self.btn_subset.setEnabled(True)

        if action == "find_markers":
            self.btn_find.setText("🔍 Subcluster Markers")
            self.btn_find.setEnabled(True)

        if action == "apply_annotation":
            self.btn_execute.setText("🏷 Run Annotation + Plot")
            self.btn_execute.setEnabled(True)
            self.btn_annotation_only.setText("📝 Annotation Only")
            self.btn_annotation_only.setEnabled(True)
            self.btn_generate_plots.setText("🖼 Plot Only")
            self.btn_generate_plots.setEnabled(True)
            if self._auto_plot_after_annotation:
                self.append_log("Subcluster annotation object saved. Generating plots...")
                self._auto_plot_after_annotation = False
                QTimer.singleShot(200, self._gen_umap)
            else:
                self.append_log("Subcluster annotation object saved. Click Plot Only to generate figures.")

        if action == "scina_annotate":
            cluster_ids = [str(x) for x in summary.get("cluster_ids", [])]
            scina_mapping = {str(k): str(v) for k, v in (summary.get("scina_mapping", {}) or {}).items()}
            self._apply_method_mapping(cluster_ids, scina_mapping, "SCINA")
            return

        if action == "cellassign_annotate":
            cluster_ids = [str(x) for x in summary.get("cluster_ids", [])]
            cellassign_mapping = {str(k): str(v) for k, v in (summary.get("cellassign_mapping", {}) or {}).items()}
            self._apply_method_mapping(cluster_ids, cellassign_mapping, "CellAssign")
            return

        cluster_ids = summary.get("cluster_ids", [])
        if isinstance(cluster_ids, str):
            cluster_ids = [cluster_ids]
        if action in {"subset_and_cluster", "find_markers"} and cluster_ids:
            self._populate_map([str(x) for x in cluster_ids if str(x).strip()])

        summary_figures = summary.get("figures", [])
        if isinstance(summary_figures, str):
            summary_figures = [summary_figures]
        current_dir = self._current_result_dir()
        figures = [os.path.join(current_dir, fig) for fig in summary_figures if isinstance(fig, str)]
        result_label = ""
        current_entry = self._current_result_entry()
        if current_entry:
            result_label = str(current_entry.get("display_name", "") or current_entry.get("result_id", ""))

        figure_name_map = {
            "subcluster_variable_features": "Subcluster Variable Features",
            "subcluster_umap": "Subtype UMAP",
            "subcluster_tsne": "Subtype t-SNE",
            "subtype_umap": "Annotated Subtype UMAP",
            "subtype_tsne": "Annotated Subtype t-SNE",
            "subtype_umap_by_group": "Subtype UMAP by Group",
            "subtype_tsne_by_group": "Subtype t-SNE by Group",
            "subtype_composition_bar": "Subtype Composition",
            "subcluster_elbow_plot": "Subcluster Elbow Plot",
            "subcluster_umap_split": "Subcluster UMAP Split by Group",
            "subcluster_tsne_split": "Subcluster t-SNE Split by Group",
            "subcluster_marker_heatmap": "Top Subtype Marker Heatmap",
            "subcluster_marker_bubble_plot_compact": "Top Subtype Markers Bubble Plot (Compact)",
            "subcluster_marker_bubble_plot_full": "Top Subtype Markers Bubble Plot (Full)",
            "sub_manual_marker_dotplot_compact": "Manual Subtype Marker DotPlot (Compact)",
            "sub_manual_marker_dotplot_full": "Manual Subtype Marker DotPlot (Full)",
        }
        def _match_name(stem: str) -> str:
            for key, value in figure_name_map.items():
                if stem == key or stem.endswith(f"_{key}"):
                    return value
            return stem

        compact_preferred = {
            "sub_manual_marker_dotplot_compact",
            "subcluster_marker_heatmap",
            "subcluster_marker_bubble_plot_compact",
            "subtype_umap",
            "subtype_tsne",
            "subtype_umap_by_group",
            "subtype_tsne_by_group",
            "subcluster_umap",
            "subcluster_tsne",
            "subcluster_umap_split",
            "subcluster_tsne_split",
        }
        for fig in figures:
            cache = current_dir
            figure_path = fig if os.path.isabs(fig) else os.path.join(cache, fig)
            if os.path.isfile(figure_path):
                stem = os.path.splitext(os.path.basename(figure_path))[0]
                preview_name = _match_name(stem)
                if result_label:
                    preview_name = f"{result_label} - {preview_name}"
                self.main_window.add_preview_item(preview_name, figure_path, "figure", "Subcluster Analysis")

        tables = summary.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        table_name_map = {
            "sub_all_markers": "All Subtype Markers",
            "sub_top_markers": "Top Subtype Markers",
            "composition_sub_percent": "Subtype Composition Percent",
            "sub_scina_mapping": "SCINA Subtype Mapping",
            "sub_scina_cell_predictions": "SCINA Subtype Cell Predictions",
            "sub_cellassign_mapping": "CellAssign Subtype Mapping",
            "sub_cellassign_cell_predictions": "CellAssign Subtype Cell Predictions",
        }
        for tbl in tables:
            cache = current_dir
            table_path = tbl if os.path.isabs(tbl) else os.path.join(cache, tbl)
            if os.path.isfile(table_path):
                stem = os.path.splitext(os.path.basename(table_path))[0]
                preview_name = table_name_map.get(stem, stem)
                if result_label:
                    preview_name = f"{result_label} - {preview_name}"
                self.main_window.add_preview_item(preview_name, table_path, "table", "Subcluster Analysis")

        manual_marker_message = str(summary.get("manual_marker_plot_message", "") or "").strip()
        if manual_marker_message:
            self.append_log(manual_marker_message)

        if action == "generate_plots":
            if figures:
                preferred = ""
                for fig in figures:
                    candidate = fig if os.path.isabs(fig) else os.path.join(current_dir, fig)
                    name = os.path.splitext(os.path.basename(candidate))[0]
                    matched_name = stem = os.path.splitext(os.path.basename(candidate))[0]
                    if matched_name in compact_preferred or any(matched_name.endswith(f"_{item}") for item in compact_preferred):
                        preferred = candidate
                        break
                    if not preferred and (matched_name in ("subtype_umap", "subtype_tsne", "subtype_umap_by_group", "subtype_tsne_by_group") or any(matched_name.endswith(f"_{item}") for item in ("subtype_umap", "subtype_tsne", "subtype_umap_by_group", "subtype_tsne_by_group"))):
                        preferred = candidate
                last = preferred or (figures[-1] if os.path.isabs(figures[-1]) else os.path.join(current_dir, figures[-1]))
                if os.path.isfile(last):
                    fig_name = os.path.splitext(os.path.basename(last))[0]
                    if fig_name == "subcluster_marker_heatmap" or fig_name.endswith("_subcluster_marker_heatmap"):
                        title = "Subtype Marker Heatmap"
                    elif fig_name == "subcluster_marker_bubble_plot_compact" or fig_name.endswith("_subcluster_marker_bubble_plot_compact"):
                        title = "Subtype Marker Bubble Plot"
                    else:
                        title = f"Subcluster Analysis - {(current_entry or {}).get('display_name', self._get_primary_reduction().upper())}"
                    self.main_window.show_preview_image(last, title)
            else:
                QMessageBox.information(self, "Notice", "Subcluster annotation completed, but no image result is available for preview.")
            self.project.step_status["subcluster"] = "done"
            idx = self.main_window.get_step_index("subcluster")
            if idx >= 0:
                self.main_window.sidebar.set_step_status(idx, "done")
            self.btn_execute.setText("🏷 Run Annotation + Plot")
            self.btn_execute.setEnabled(True)
            self.btn_annotation_only.setText("📝 Annotation Only")
            self.btn_annotation_only.setEnabled(True)
            self.btn_generate_plots.setText("🖼 Plot Only")
            self.btn_generate_plots.setEnabled(True)

    def on_step_error(self, step, summary, detail):
        entry = self._current_result_entry()
        if entry:
            entry["status"] = "failed"
            self._register_subcluster_result(entry)
        self.btn_subset.setText("🔬 Clustering")
        self.btn_subset.setEnabled(True)
        self.btn_find.setText("🔍 Subcluster Markers")
        self.btn_find.setEnabled(True)
        self.btn_execute.setText("🏷 Run Annotation + Plot")
        self.btn_execute.setEnabled(True)
        self.btn_annotation_only.setText("📝 Annotation Only")
        self.btn_annotation_only.setEnabled(True)
        self.btn_generate_plots.setText("🖼 Plot Only")
        self.btn_generate_plots.setEnabled(True)
        if "SCINA" in step:
            QMessageBox.warning(self, "Subcluster SCINA annotation failed", summary)
        elif "CellAssign" in step:
            QMessageBox.warning(self, "Subcluster CellAssign annotation failed", summary)

    def run_step(self):
        self._run_subset()
