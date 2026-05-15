import csv
import json
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.runtime_paths import get_app_root, get_resource_path
from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


REF_OPTIONS = [
    ("HumanPrimaryCellAtlas", "Human | Human Primary Cell Atlas", "Human", "General human cell annotation."),
    ("BlueprintEncode", "Human | Blueprint/ENCODE | blood/immune", "Human", "Blood and immune cell annotation."),
    ("MonacoImmune", "Human | Monaco immune reference", "Human", "Immune cell annotation."),
    ("NovershternHematopoietic", "Human | Novershtern hematopoietic reference", "Human", "Hematopoietic cell annotation."),
    ("DatabaseImmuneCellExpression", "Human | DICE", "Human", "Immune-cell annotation."),
    ("MouseRNAseq", "Mouse | Mouse RNA-seq reference", "Mouse", "General mouse cell annotation."),
    ("ImmGen", "Mouse | ImmGen", "Mouse", "Mouse immune-cell annotation."),
]


class AnnotationPage(BasePage):
    STEP_ID = "annotation"
    STEP_NAME = "⑥ Main Annotation"
    MANUAL_METHODS = [
        (
            "manual",
            "Manual marker annotation",
            "Use a cell type + marker panel; marker overlap proposes cluster labels for manual annotation.",
        ),
        (
            "scina",
            "SCINA",
            "Semi-supervised marker-based annotation. The marker panel is converted to SCINA signature lists.",
        ),
        (
            "cellassign",
            "CellAssign",
            "Probabilistic marker-based annotation. The marker panel is converted to a marker gene by cell type matrix.",
        ),
    ]
    ANNOTATION_PRESETS = {
        "Conservative": {"min_pct": 0.25, "logfc": 0.25, "only_pos": True},
        "Relaxed": {"min_pct": 0.05, "logfc": 0.10, "only_pos": True},
        "Force assignment": {"min_pct": 0.05, "logfc": 0.10, "only_pos": True},
    }

    def __init__(self, **kwargs):
        self._gene_list = []
        self._custom_markers = {}
        self._markers_found = False
        super().__init__(**kwargs)

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp1 = QGroupBox("Step 1 - Main Markers")
        f1 = QFormLayout(grp1)
        self.cmb_annotation_profile = QComboBox()
        self.cmb_annotation_profile.addItem("Conservative", "Conservative")
        self.cmb_annotation_profile.addItem("Relaxed (reduce Unknown)", "Relaxed")
        self.cmb_annotation_profile.addItem("Force assignment (avoid Unknown)", "Force assignment")
        saved_profile = getattr(self.app_config, "annotation_profile", "Conservative")
        saved_index = self.cmb_annotation_profile.findData(
            saved_profile if saved_profile in self.ANNOTATION_PRESETS else "Conservative"
        )
        self.cmb_annotation_profile.setCurrentIndex(saved_index if saved_index >= 0 else 0)
        self.cmb_annotation_profile.currentIndexChanged.connect(self._on_annotation_profile_changed)
        self.spn_min_pct = QDoubleSpinBox()
        self.spn_min_pct.setRange(0, 1)
        self.spn_min_pct.setDecimals(2)
        self.spn_min_pct.setValue(self.app_config.annotation_min_pct)
        self.spn_logfc = QDoubleSpinBox()
        self.spn_logfc.setRange(0, 5)
        self.spn_logfc.setDecimals(2)
        self.spn_logfc.setValue(self.app_config.annotation_logfc)
        self.chk_only_pos = QCheckBox("Positive markers only (only.pos)")
        self.chk_only_pos.setChecked(True)
        self.cmb_test = QComboBox()
        self.cmb_test.addItems(["wilcox", "bimod", "t", "MAST"])
        self.chk_filter = QCheckBox("Filter technical/low-confidence genes (LOC / RGD / ENSRNOG / AABR / Gm)")
        self.chk_filter.setChecked(True)
        self.lbl_filter_hint = QLabel(
            "Filtering can remove technical or low-confidence gene names from marker tables."
        )
        self.lbl_filter_hint.setWordWrap(True)
        self.lbl_filter_hint.setStyleSheet("color:#666; font-size:11px;")
        self.btn_find = QPushButton("Find Cluster Markers")
        self.btn_find.clicked.connect(self._find_markers)
        self.lbl_profile_hint = QLabel("")
        self.lbl_profile_hint.setWordWrap(True)
        self.lbl_profile_hint.setStyleSheet("color:#666; font-size:11px;")
        self.lbl_step1 = QLabel("Run Step 1 to find main cluster markers.")
        self.lbl_step1.setStyleSheet("color:#FF9800;")
        f1.addRow("Annotation:", self.cmb_annotation_profile)
        f1.addRow("Marker min.pct:", self.spn_min_pct)
        f1.addRow("Marker logfc.threshold:", self.spn_logfc)
        f1.addRow("", self.chk_only_pos)
        f1.addRow("Differential Expression:", self.cmb_test)
        f1.addRow("", self.chk_filter)
        f1.addRow("", self.lbl_filter_hint)
        f1.addRow("", self.lbl_profile_hint)
        f1.addRow("", self.btn_find)
        f1.addRow("", self.lbl_step1)
        layout.addWidget(grp1)

        grp2 = QGroupBox("Step 2 - Annotation")
        v2 = QVBoxLayout(grp2)
        self.radio_auto = QRadioButton("Automatic Annotation")
        self.radio_manual = QRadioButton("Manual Annotation")
        self.radio_manual.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_auto, 0)
        self.mode_group.addButton(self.radio_manual, 1)
        self.mode_group.idToggled.connect(self._on_mode_changed)
        v2.addWidget(self.radio_auto)

        row2 = QHBoxLayout()
        row2.addSpacing(24)
        row2.addWidget(QLabel("Annotation method:"))
        self.cmb_auto_algo = QComboBox()
        self.cmb_auto_algo.addItems(["SingleR"])
        self.cmb_auto_algo.currentTextChanged.connect(self._refresh_auto_ui)
        row2.addWidget(self.cmb_auto_algo)
        row2.addWidget(QLabel("Reference database:"))
        self.cmb_builtin = QComboBox()
        self.cmb_builtin.currentTextChanged.connect(self._refresh_ref_hint)
        row2.addWidget(self.cmb_builtin, 1)
        v2.addLayout(row2)

        self.lbl_auto_info = QLabel(
            "Automatic annotation uses SingleR with the selected celldex reference.\n"
            "The current object will be annotated using the local/reference cache."
        )
        self.lbl_auto_info.setWordWrap(True)
        self.lbl_auto_info.setStyleSheet("color:#5F6B7A; font-size:11px;")
        self.lbl_ref_hint = QLabel("")
        self.lbl_ref_hint.setWordWrap(True)
        self.lbl_ref_hint.setStyleSheet("color:#1565C0; font-size:11px;")
        v2.addWidget(self.lbl_auto_info)
        v2.addWidget(self.lbl_ref_hint)
        v2.addWidget(self.radio_manual)
        layout.addWidget(grp2)

        self.grp_manual = QGroupBox("Step 3 - Marker-Based Annotation")
        v3 = QVBoxLayout(self.grp_manual)
        tool_row = QHBoxLayout()
        self.btn_import = QPushButton("Import CSV / XLSX")
        self.btn_import.clicked.connect(self._import_file)
        self.btn_export = QPushButton("Export CSV")
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_template = QPushButton("Save Template")
        self.btn_template.clicked.connect(self._download_template)
        self.btn_save_project = QPushButton("Save to Project")
        self.btn_save_project.clicked.connect(self._save_markers_to_project)
        self.btn_restore_project = QPushButton("Load from Project")
        self.btn_restore_project.clicked.connect(self._restore_markers_from_project)
        self.btn_clear_markers = QPushButton("Clear Markers")
        self.btn_clear_markers.clicked.connect(lambda: self._clear_custom_markers(confirm=True))
        for btn in [
            self.btn_import,
            self.btn_export,
            self.btn_template,
            self.btn_save_project,
            self.btn_restore_project,
            self.btn_clear_markers,
        ]:
            tool_row.addWidget(btn)
        tool_row.addStretch()
        v3.addLayout(tool_row)

        self.lbl_manual_state = QLabel(
            "Manual marker panel is empty. Import a marker file or add cell types and genes manually."
        )
        self.lbl_manual_state.setWordWrap(True)
        self.lbl_manual_state.setStyleSheet("color:#666; font-size:11px;")
        v3.addWidget(self.lbl_manual_state)

        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Annotation method:"))
        self.cmb_manual_method = QComboBox()
        for method_key, label, _desc in self.MANUAL_METHODS:
            self.cmb_manual_method.addItem(label, method_key)
        self.cmb_manual_method.currentIndexChanged.connect(self._refresh_manual_method_ui)
        method_row.addWidget(self.cmb_manual_method, 1)
        v3.addLayout(method_row)

        self.lbl_manual_method_info = QLabel("")
        self.lbl_manual_method_info.setWordWrap(True)
        self.lbl_manual_method_info.setStyleSheet("color:#5F6B7A; font-size:11px;")
        v3.addWidget(self.lbl_manual_method_info)

        cols = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Cell type list:"))
        self.lst_ct = QListWidget()
        self.lst_ct.setMinimumHeight(180)
        self.lst_ct.currentRowChanged.connect(self._on_ct_selected)
        left.addWidget(self.lst_ct)
        row_ct = QHBoxLayout()
        self.btn_add_ct = QPushButton("Add Cell Type")
        self.btn_add_ct.clicked.connect(self._add_ct)
        self.btn_del_ct = QPushButton("Delete Cell Type")
        self.btn_del_ct.clicked.connect(self._del_ct)
        row_ct.addWidget(self.btn_add_ct)
        row_ct.addWidget(self.btn_del_ct)
        left.addLayout(row_ct)
        cols.addLayout(left, 2)

        mid = QVBoxLayout()
        self.lbl_ct_name = QLabel("Please select a cell type")
        self.lbl_ct_name.setStyleSheet("font-weight:bold;")
        mid.addWidget(self.lbl_ct_name)
        self.lst_markers = QListWidget()
        self.lst_markers.setMinimumHeight(180)
        mid.addWidget(self.lst_markers)
        self.btn_rm_marker = QPushButton("Remove Marker")
        self.btn_rm_marker.clicked.connect(self._rm_marker)
        mid.addWidget(self.btn_rm_marker)
        cols.addLayout(mid, 2)

        right = QVBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("genes, Gfap, Mbp, Pdgfra")
        self.txt_search.textChanged.connect(self._on_search)
        self.lbl_search = QLabel("Enter one marker gene per line or paste a comma-separated gene list.")
        self.lbl_search.setStyleSheet("color:#888; font-size:11px;")
        self.lst_cand = QListWidget()
        self.lst_cand.setMinimumHeight(180)
        self.lst_cand.itemDoubleClicked.connect(self._add_gene)
        self.btn_add_gene = QPushButton("Add Gene")
        self.btn_add_gene.clicked.connect(self._add_gene_btn)
        right.addWidget(self.txt_search)
        right.addWidget(self.lbl_search)
        right.addWidget(self.lst_cand)
        right.addWidget(self.btn_add_gene)
        cols.addLayout(right, 3)
        v3.addLayout(cols)

        grp4 = QGroupBox("Step 4 - Cluster Cell Type")
        v4 = QVBoxLayout(grp4)
        self.lbl_mapping_hint = QLabel(
            "Cluster-to-cell-type annotation results will be shown here."
        )
        self.lbl_mapping_hint.setWordWrap(True)
        self.lbl_mapping_hint.setStyleSheet("color:#666; font-size:11px;")
        v4.addWidget(self.lbl_mapping_hint)
        self.mapping_table = QTableWidget()
        self.mapping_table.setColumnCount(2)
        self.mapping_table.setHorizontalHeaderLabels(["Cluster", "Cell Type"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.mapping_table.setMinimumHeight(280)
        self.mapping_table.verticalHeader().setDefaultSectionSize(28)
        v4.addWidget(self.mapping_table, 1)

        self.manual_splitter = QSplitter(Qt.Vertical)
        self.manual_splitter.setChildrenCollapsible(False)
        self.manual_splitter.addWidget(self.grp_manual)
        self.manual_splitter.addWidget(grp4)
        self.manual_splitter.setStretchFactor(0, 3)
        self.manual_splitter.setStretchFactor(1, 2)
        self.manual_splitter.setSizes([420, 320])
        layout.addWidget(self.manual_splitter, 1)

        row5 = QHBoxLayout()
        self.btn_execute = QPushButton("🏷 Run Annotation")
        self.btn_execute.setProperty("role", "accent")
        self.btn_execute.clicked.connect(self._execute)
        self.btn_reapply = QPushButton("📝 Apply Annotation")
        self.btn_reapply.setProperty("role", "primary")
        self.btn_reapply.clicked.connect(self._apply_annotation)
        self.btn_regen = QPushButton("🖼 Generate Annotation Plots")
        self.btn_regen.setProperty("role", "ghost")
        self.btn_regen.clicked.connect(self._gen_plots)
        row5.addWidget(self.btn_execute)
        row5.addWidget(self.btn_reapply)
        row5.addWidget(self.btn_regen)
        layout.addLayout(row5)

        self.bind_help_refresh(
            self.spn_min_pct,
            self.spn_logfc,
            self.cmb_annotation_profile,
            self.chk_only_pos,
            self.cmb_test,
            self.chk_filter,
            self.radio_auto,
            self.radio_manual,
            self.cmb_auto_algo,
            self.cmb_manual_method,
            self.cmb_builtin,
        )
        self._populate_refs()
        self._apply_annotation_profile(
            self.cmb_annotation_profile.currentData(),
            force=False,
            sync_config=False,
        )
        self._refresh_auto_ui()
        return container

    def _cache_dir(self):
        return self.project.cache_subdir("annotation")

    def _reference_cache_dir(self):
        candidates = [
            get_app_root() / "celldex_cache",
            get_resource_path("celldex_cache"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _saved_marker_path(self) -> str:
        if not self.project:
            return ""
        return os.path.join(self.project.directory, "custom_markers.json")

    def _project_species(self):
        if not self.project or not self.project.samples:
            return "Unknown"
        species = (self.project.samples[0].species or "").strip().lower()
        if species.startswith("human"):
            return "Human"
        if species.startswith("mouse"):
            return "Mouse"
        if species.startswith("rat"):
            return "Rat"
        return "Unknown"

    def _reduction(self):
        if not self.project:
            return "umap"
        path = os.path.join(self.project.cache_subdir("clustering"), "primary_reduction.txt")
        if os.path.exists(path):
            try:
                return open(path, "r", encoding="utf-8").read().strip() or "umap"
            except Exception:
                pass
        return "umap"

    def _selected_ref(self):
        rid = self.cmb_builtin.currentData()
        for item in REF_OPTIONS:
            if item[0] == rid:
                return item
        return REF_OPTIONS[0]

    def _populate_refs(self):
        current = self.cmb_builtin.currentData()
        species = self._project_species()
        preferred_species = "Human" if species == "Human" else "Mouse"
        ordered = [x for x in REF_OPTIONS if x[2] == preferred_species] + [x for x in REF_OPTIONS if x[2] != preferred_species]
        self.cmb_builtin.blockSignals(True)
        self.cmb_builtin.clear()
        for rid, label, _, _ in ordered:
            self.cmb_builtin.addItem(label, rid)
        self.cmb_builtin.blockSignals(False)
        idx = self.cmb_builtin.findData(current)
        if idx < 0:
            idx = self.cmb_builtin.findData("HumanPrimaryCellAtlas" if species == "Human" else "MouseRNAseq")
        self.cmb_builtin.setCurrentIndex(idx if idx >= 0 else 0)
        self._refresh_ref_hint()

    def _refresh_ref_hint(self):
        _, _, ref_species, desc = self._selected_ref()
        species = self._project_species()
        extra = ""
        if species == "Human" and ref_species != "Human":
            extra = "The selected reference species differs from the project species. Review labels carefully."
        elif species == "Mouse" and ref_species != "Mouse":
            extra = "The selected reference species differs from the project species. Review labels carefully."
        elif species == "Rat" and ref_species == "Mouse":
            extra = "Rat projects can use mouse references, but predicted labels should be reviewed carefully."
        self.lbl_ref_hint.setText(desc + ("\n" + extra if extra else ""))

    def _refresh_auto_ui(self):
        is_manual = self.radio_manual.isChecked()
        self.grp_manual.setVisible(is_manual)
        self.cmb_auto_algo.setEnabled(not is_manual)
        self.cmb_builtin.setEnabled(not is_manual)
        self.lbl_auto_info.setVisible(not is_manual)
        self.lbl_ref_hint.setVisible(not is_manual)
        if is_manual:
            self.manual_splitter.setSizes([420, 320])
        else:
            self.manual_splitter.setSizes([0, 520])
        self._refresh_manual_method_ui()
        self.refresh_help()

    def _manual_method_key(self) -> str:
        return str(self.cmb_manual_method.currentData() or "manual")

    def _manual_method_label(self) -> str:
        return str(self.cmb_manual_method.currentText() or "Manual marker annotation")

    def _refresh_manual_method_ui(self):
        if not hasattr(self, "cmb_manual_method"):
            return
        method_key = self._manual_method_key()
        method_desc = ""
        for key, _label, desc in self.MANUAL_METHODS:
            if key == method_key:
                method_desc = desc
                break
        if method_key == "manual":
            extra = "Manual marker mode uses your marker panel and cluster marker overlap."
        elif method_key == "scina":
            extra = "SCINA requires the local R runtime to provide the SCINA package and a valid current object."
        else:
            extra = "CellAssign requires the local R/Python runtime and a valid current object."
        self.lbl_manual_method_info.setText(method_desc + "\n" + extra)

    def _on_mode_changed(self, _idx, checked):
        if checked:
            self._refresh_auto_ui()

    def _apply_annotation_profile(self, profile_name: str, force: bool = False, sync_config: bool = True):
        profile = self.ANNOTATION_PRESETS.get(profile_name, self.ANNOTATION_PRESETS["Conservative"])
        if force or abs(self.spn_min_pct.value() - profile["min_pct"]) < 1e-9:
            self.spn_min_pct.setValue(profile["min_pct"])
        if force or abs(self.spn_logfc.value() - profile["logfc"]) < 1e-9:
            self.spn_logfc.setValue(profile["logfc"])
        if force:
            self.chk_only_pos.setChecked(profile["only_pos"])

        if profile_name == "Force assignment":
            self.lbl_profile_hint.setText(
                "Force assignment avoids Unknown labels when marker evidence is weak. "
                "Please review labels carefully before applying the annotation."
            )
        elif profile_name == "Relaxed":
            self.lbl_profile_hint.setText(
                "Relaxed mode uses marker evidence to reduce Unknown labels in annotation results."
            )
        else:
            self.lbl_profile_hint.setText(
                "Conservative mode keeps uncertain clusters as Unknown unless marker evidence is sufficient."
            )

        if sync_config and hasattr(self, "app_config"):
            self.app_config.annotation_profile = profile_name

    def _on_annotation_profile_changed(self, _index: int):
        self._apply_annotation_profile(self.cmb_annotation_profile.currentData(), force=True, sync_config=True)
        self.refresh_help()

    def get_params(self) -> dict:
        mapping = {}
        for row in range(self.mapping_table.rowCount()):
            c0 = self.mapping_table.item(row, 0)
            c1 = self.mapping_table.item(row, 1)
            if c0 and c1 and c1.text().strip():
                mapping[c0.text()] = c1.text().strip()
        ref_id, ref_label, _, _ = self._selected_ref()
        return {
            "annotation_profile": self.cmb_annotation_profile.currentData(),
            "min_pct": self.spn_min_pct.value(),
            "logfc_threshold": self.spn_logfc.value(),
            "only_pos": self.chk_only_pos.isChecked(),
            "test_use": self.cmb_test.currentText(),
            "filter_genes": self.chk_filter.isChecked(),
            "cluster_mapping": mapping,
            "custom_markers": self._custom_markers,
            "manual_method": self._manual_method_key(),
            "group_order": self.main_window.get_group_order() if hasattr(self.main_window, "get_group_order") else [],
            "reduction": self._reduction(),
            "auto_algo": self.cmb_auto_algo.currentText(),
            "builtin_ref": ref_label,
            "singler_ref_id": ref_id,
            "species": self._project_species(),
            "seed": self.app_config.default_seed,
            "color_scheme": getattr(self.project, "plot_theme", self.app_config.color_scheme) if self.project else self.app_config.color_scheme,
            "reference_cache_dir": self._reference_cache_dir().as_posix(),
        }

    def reset_params(self):
        profile_name = getattr(self.app_config, "annotation_profile", "Conservative")
        if profile_name not in self.ANNOTATION_PRESETS:
            profile_name = "Conservative"
        profile_index = self.cmb_annotation_profile.findData(profile_name)
        self.cmb_annotation_profile.setCurrentIndex(profile_index if profile_index >= 0 else 0)
        self._apply_annotation_profile(profile_name, force=True, sync_config=False)
        self.cmb_test.setCurrentText("wilcox")
        self.chk_filter.setChecked(True)
        self.radio_manual.setChecked(True)
        self.cmb_manual_method.setCurrentIndex(0)
        self.txt_search.clear()
        self._clear_custom_markers(confirm=False)
        self._populate_refs()
        self._refresh_auto_ui()

    def get_help_html(self) -> str:
        return build_step_help("annotation", {
            "annotation_profile": self.cmb_annotation_profile.currentData(),
            "min_pct": self.spn_min_pct.value(),
            "logfc_threshold": self.spn_logfc.value(),
            "only_pos": self.chk_only_pos.isChecked(),
            "test_use": self.cmb_test.currentText(),
            "auto_algo": self.cmb_auto_algo.currentText(),
            "manual_method": self._manual_method_label(),
            "builtin_ref": self.cmb_builtin.currentText(),
            "reduction": self._reduction(),
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._restore_task_buttons_if_idle()
        self._clear_custom_markers(confirm=False)
        self._load_clusters()
        self._load_genes()
        self._check_ready()
        self._populate_refs()

    def on_page_entered(self):
        self._restore_task_buttons_if_idle()
        self._load_clusters()
        self._load_genes()
        self._check_ready()
        self._populate_refs()
        self._clear_custom_markers(confirm=False)

    def _check_ready(self):
        if not self.project:
            return
        self._markers_found = os.path.exists(os.path.join(self._cache_dir(), "all_markers.csv"))
        if self._markers_found:
            self.lbl_step1.setText("Main marker results detected. Continue annotation.")
            self.lbl_step1.setStyleSheet("color:#4CAF50; font-weight:bold;")
        else:
            self.lbl_step1.setText("Run Step 1 to find main cluster markers.")
            self.lbl_step1.setStyleSheet("color:#FF9800;")

    def _load_clusters(self):
        if not self.project:
            return
        for loc in ["annotation", "clustering"]:
            path = os.path.join(self.project.cache_subdir(loc), "summary.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        cluster_ids = json.load(handle).get("cluster_ids", [])
                    if cluster_ids:
                        self._populate_mapping(cluster_ids)
                        return
                except Exception:
                    pass

    def _load_genes(self):
        if not self.project:
            return
        for loc in ["annotation", "clustering"]:
            path = os.path.join(self.project.cache_subdir(loc), "gene_list.txt")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        self._gene_list = [line.strip() for line in handle if line.strip()]
                    self.lbl_search.setText(f"Loaded {len(self._gene_list)} genes.")
                    return
                except Exception:
                    pass
        self._gene_list = []
        self.lbl_search.setText("No gene list loaded.")

    def _populate_mapping(self, cluster_ids):
        old = {}
        for row in range(self.mapping_table.rowCount()):
            a = self.mapping_table.item(row, 0)
            b = self.mapping_table.item(row, 1)
            if a and b:
                old[a.text()] = b.text()
        self.mapping_table.setRowCount(len(cluster_ids))
        for row, cid in enumerate(cluster_ids):
            item = QTableWidgetItem(str(cid))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.mapping_table.setItem(row, 0, item)
            self.mapping_table.setItem(row, 1, QTableWidgetItem(old.get(str(cid), f"Cluster_{cid}")))

    def _find_markers(self):
        if not self.require_project():
            return
        input_rds = os.path.join(self.project.cache_subdir("clustering"), "clustered.rds").replace("\\", "/")
        if not os.path.isfile(input_rds):
            QMessageBox.warning(self, "Notice", "Please finish clustering before finding main markers.")
            return
        self.clear_log()
        self.btn_find.setEnabled(False)
        self.btn_find.setText("⏳ Finding markers...")
        params = self.get_params()
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        params["action"] = "find_markers"
        self.register_task_owner()
        self.task_runner.run_r_script("06_annotation.R", params, self._cache_dir(), "Main Markers")

    def _restore_find(self):
        self.btn_find.setEnabled(True)
        self.btn_find.setText("Find Cluster Markers")

    def _set_execute_busy(self, busy: bool, text: str | None = None):
        self.btn_execute.setEnabled(not busy)
        self.btn_reapply.setEnabled(not busy)
        self.btn_regen.setEnabled(not busy)
        if text is not None:
            self.btn_execute.setText(text)
        elif busy:
            self.btn_execute.setText("⏳ Running main annotation...")
        else:
            self.btn_execute.setText("🏷 Run Annotation")

    def _restore_task_buttons_if_idle(self):
        if getattr(self.task_runner, "is_running", False):
            return
        self._restore_find()
        self._set_execute_busy(False)

    def _apply_singler_mapping(self, cluster_ids, mapping):
        if not cluster_ids:
            return
        mapping = mapping or {}
        existing = {}
        for row in range(self.mapping_table.rowCount()):
            c0 = self.mapping_table.item(row, 0)
            c1 = self.mapping_table.item(row, 1)
            if c0 and c1:
                existing[c0.text()] = c1.text().strip()

        self.mapping_table.setRowCount(len(cluster_ids))
        for row, cid in enumerate(cluster_ids):
            cluster_id = str(cid)
            cluster_item = QTableWidgetItem(cluster_id)
            cluster_item.setFlags(cluster_item.flags() & ~Qt.ItemIsEditable)
            self.mapping_table.setItem(row, 0, cluster_item)

            suggested = str(mapping.get(cluster_id, "")).strip()
            current = str(existing.get(cluster_id, "")).strip()
            final_label = suggested or current or f"Cluster_{cluster_id}"
            self.mapping_table.setItem(row, 1, QTableWidgetItem(final_label))

    def _add_ct(self):
        text, ok = QInputDialog.getText(self, "Cell Type", "Cell type name:")
        label = text.strip() if ok else ""
        if label and label not in self._custom_markers:
            self._custom_markers[label] = []
            self._refresh_ct()
            self.lbl_manual_state.setText("Manual annotation cell type added.")

    def _del_ct(self):
        row = self.lst_ct.currentRow()
        if row >= 0:
            self._custom_markers.pop(self.lst_ct.item(row).text(), None)
            self._refresh_ct()
            self.lbl_manual_state.setText("Selected cell type deleted.")

    def _refresh_ct(self):
        self.lst_ct.clear()
        for name in self._custom_markers:
            self.lst_ct.addItem(name)

    def _on_ct_selected(self, row):
        self.lst_markers.clear()
        if row < 0:
            self.lbl_ct_name.setText("Please select a cell type")
            return
        name = self.lst_ct.item(row).text()
        self.lbl_ct_name.setText(name)
        for gene in self._custom_markers.get(name, []):
            self.lst_markers.addItem(gene)

    def _rm_marker(self):
        ct_row = self.lst_ct.currentRow()
        mk_row = self.lst_markers.currentRow()
        if ct_row >= 0 and mk_row >= 0:
            ct = self.lst_ct.item(ct_row).text()
            gene = self.lst_markers.item(mk_row).text()
            if gene in self._custom_markers.get(ct, []):
                self._custom_markers[ct].remove(gene)
            self.lst_markers.takeItem(mk_row)

    def _on_search(self, text):
        self.lst_cand.clear()
        keyword = text.strip().lower()
        if not keyword:
            return
        hits = [g for g in self._gene_list if keyword in g.lower()][:100]
        for gene in hits:
            self.lst_cand.addItem(gene)
        self.lbl_search.setText(f"Found {len(hits)} matching genes.")

    def _add_gene(self, item):
        row = self.lst_ct.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Notice", "Please select a cell type first.")
            return
        ct = self.lst_ct.item(row).text()
        gene = item.text()
        self._custom_markers.setdefault(ct, [])
        if gene not in self._custom_markers[ct]:
            self._custom_markers[ct].append(gene)
            self.lst_markers.addItem(gene)
            self.lbl_manual_state.setText("Marker added to the selected cell type.")

    def _add_gene_btn(self):
        item = self.lst_cand.currentItem()
        if item:
            self._add_gene(item)

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Marker File", "", "CSV/XLSX (*.csv *.xlsx)")
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                import openpyxl
                wb = openpyxl.load_workbook(path, read_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))[1:]
                wb.close()
            else:
                with open(path, "r", encoding="utf-8-sig") as handle:
                    rows = list(csv.reader(handle))[1:]
            for row in rows:
                if len(row) >= 2 and row[0] and row[1]:
                    cell_type = str(row[0]).strip()
                    gene = str(row[1]).strip()
                    self._custom_markers.setdefault(cell_type, [])
                    if gene not in self._custom_markers[cell_type]:
                        self._custom_markers[cell_type].append(gene)
            self._refresh_ct()
            self.lbl_manual_state.setText("Marker file imported. You can save it to the project.")
            QMessageBox.information(self, "Finished", "Marker file imported.")
        except Exception as exc:
            QMessageBox.critical(self, "Failed", f"File format error: {exc}")

    def _export_csv(self):
        if not self._custom_markers:
            QMessageBox.warning(self, "Notice", "No marker panel is available for export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Marker CSV", "markers.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["cell_type", "gene"])
            for ct, genes in self._custom_markers.items():
                for gene in genes:
                    writer.writerow([ct, gene])

    def _download_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save", "marker_template.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["cell_type", "gene"])
            writer.writerow(["Astrocytes", "Gfap"])
            writer.writerow(["Myeloid", "Lyz2"])

    def _clear_custom_markers(self, confirm: bool = False):
        if confirm and self._custom_markers:
            if QMessageBox.question(self, "Notice", "Clear the current marker panel?") != QMessageBox.Yes:
                return
        self._custom_markers = {}
        self.lst_ct.clear()
        self.lst_markers.clear()
        self.lst_cand.clear()
        self.lbl_ct_name.setText("Please select a cell type")
        self.lbl_manual_state.setText("Marker panel is empty.")

    def _save_markers_to_project(self):
        if not self.project:
            return
        if not self._custom_markers:
            QMessageBox.information(self, "Notice", "No marker panel is available to save.")
            return
        path = self._saved_marker_path()
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self._custom_markers, handle, ensure_ascii=False, indent=2)
        self.lbl_manual_state.setText("Marker panel saved to the project.")
        QMessageBox.information(self, "Save Finished", f"Project marker saved:\n{path}")

    def _restore_markers_from_project(self):
        if not self.project:
            return
        path = self._saved_marker_path()
        if not os.path.exists(path):
            QMessageBox.information(self, "Notice", "No project marker panel was found.")
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                self._custom_markers = json.load(handle)
            self._refresh_ct()
            self.lbl_manual_state.setText("Project marker panel loaded.")
            QMessageBox.information(self, "Finished", "Project marker panel loaded.")
        except Exception as exc:
            QMessageBox.warning(self, "Failed", f"Failed to load the project marker panel: {exc}")

    def _do_overlap(self):
        marker_csv = os.path.join(self._cache_dir(), "all_markers.csv")
        if not os.path.exists(marker_csv):
            QMessageBox.warning(self, "Notice", "Please run Step 1 (Find Cluster Markers) first.")
            return False
        cluster_genes = {}
        with open(marker_csv, "r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                cid = str(row.get("cluster", ""))
                cluster_genes.setdefault(cid, []).append(row.get("gene", ""))

        profile_name = self.cmb_annotation_profile.currentData() or "Conservative"
        relaxed_mode = profile_name == "Relaxed"
        force_assign_mode = profile_name == "Force assignment"
        for row in range(self.mapping_table.rowCount()):
            item = self.mapping_table.item(row, 0)
            if not item:
                continue
            cid = item.text()
            genes = cluster_genes.get(cid, [])
            overlap_scores = []
            for ct, markers in self._custom_markers.items():
                overlap = len(set(genes) & set(markers))
                overlap_scores.append((ct, overlap))
            if not overlap_scores:
                best_ct = sorted(self._custom_markers.keys())[0] if force_assign_mode and self._custom_markers else "Unknown"
            else:
                overlap_scores.sort(key=lambda x: (-x[1], x[0]))
                best_ct, best_n = overlap_scores[0]
                if best_n <= 0 and not relaxed_mode and not force_assign_mode:
                    best_ct = "Unknown"
            self.mapping_table.setItem(row, 1, QTableWidgetItem(best_ct))
        if force_assign_mode:
            self.append_log("Force assignment generated candidate cell-type labels. Please review them before applying annotation.")
        else:
            self.append_log("Marker overlap generated candidate cell-type labels.")
        return True

    def _run_singler(self):
        input_rds = os.path.join(self.project.cache_subdir("clustering"), "clustered.rds").replace("\\", "/")
        if not os.path.isfile(input_rds):
            QMessageBox.warning(self, "Notice", "Please finish clustering before automatic annotation.")
            return
        species = self._project_species()
        _, _, ref_species, _ = self._selected_ref()
        if species == "Human" and ref_species != "Human":
            if QMessageBox.question(self, "Notice", "The selected reference species differs from the project species. Continue automatic annotation?") != QMessageBox.Yes:
                return
        if species == "Mouse" and ref_species != "Mouse":
            if QMessageBox.question(self, "Notice", "The selected reference species differs from the project species. Continue automatic annotation?") != QMessageBox.Yes:
                return
        params = self.get_params()
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        params["action"] = "singler_annotate"
        self._set_execute_busy(True, "Running SingleR automatic annotation...")
        self.register_task_owner()
        self.task_runner.run_r_script("06_annotation.R", params, self._cache_dir(), "SingleR Automatic Annotation")

    def _run_manual_r_method(self, method_key: str):
        input_rds = os.path.join(self.project.cache_subdir("clustering"), "clustered.rds").replace("\\", "/")
        if not os.path.isfile(input_rds):
            QMessageBox.warning(self, "Notice", "Please finish clustering before marker-based annotation.")
            return
        if not self._custom_markers:
            QMessageBox.warning(self, "Notice", "Please provide at least one cell type and marker gene.")
            return
        params = self.get_params()
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        params["action"] = "scina_annotate" if method_key == "scina" else "cellassign_annotate"
        method_label = "SCINA" if method_key == "scina" else "CellAssign"
        self._set_execute_busy(True, f"Running {method_label} annotation...")
        self.register_task_owner()
        self.task_runner.run_r_script("06_annotation.R", params, self._cache_dir(), f"{method_label} Manual Annotation")

    def _execute(self):
        if not self.require_project():
            return
        if not self._markers_found:
            QMessageBox.warning(self, "Notice", "Please run Step 1 (Find Cluster Markers) first.")
            return
        if self.radio_auto.isChecked():
            self._run_singler()
            return
        method_key = self._manual_method_key()
        if method_key in {"scina", "cellassign"}:
            self._run_manual_r_method(method_key)
            return
        current_mapping = self.get_params()["cluster_mapping"]
        if self._custom_markers:
            if self._do_overlap():
                self._apply_annotation()
            return
        if current_mapping:
            self._apply_annotation()
            return
        QMessageBox.warning(self, "Notice", "Please assign cluster labels in Step 4 or provide a marker panel.")

    def _apply_annotation(self):
        params = self.get_params()
        if not params["cluster_mapping"]:
            QMessageBox.warning(self, "Notice", "Cluster-to-cell-type mapping is empty. Please assign cell types first.")
            return
        input_rds = os.path.join(self.project.cache_subdir("clustering"), "clustered.rds").replace("\\", "/")
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        params["action"] = "apply_annotation"
        self._set_execute_busy(True, "Applying main annotation...")
        self.register_task_owner()
        self.task_runner.run_r_script("06_annotation.R", params, self._cache_dir(), "Apply Main Annotation")

    def _gen_plots(self):
        input_rds = os.path.join(self._cache_dir(), "annotated.rds").replace("\\", "/")
        if not os.path.isfile(input_rds):
            QMessageBox.warning(self, "Notice", "Please finish main annotation before generating annotation plots.")
            return
        params = self.get_params()
        params["input_rds"] = input_rds
        params["cache_dir"] = self._cache_dir().replace("\\", "/")
        params["action"] = "generate_plots"
        self._set_execute_busy(True, "Generating main annotation plots...")
        self.register_task_owner()
        self.task_runner.run_r_script("06_annotation.R", params, self._cache_dir(), "Generate Main Annotation Plots")

    def _apply_method_mapping(self, cluster_ids, mapping, method_label: str):
        if cluster_ids:
            self._apply_singler_mapping(cluster_ids, mapping)
        self.append_log(f"{method_label} completed. Please review suggested labels, then apply main annotation.")
        QTimer.singleShot(200, self._apply_annotation)

    def _load_gene_list(self):
        self._load_genes()

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        action = summary.get("action", "")
        if action in {"find_markers", "singler_annotate", "scina_annotate", "cellassign_annotate", "apply_annotation", "generate_plots"}:
            self._load_gene_list()

        if action == "find_markers":
            self._restore_find()
            self._markers_found = True
            self.lbl_step1.setText("Main marker results detected. Continue annotation.")
            self.lbl_step1.setStyleSheet("color:#4CAF50; font-weight:bold;")

        if action == "singler_annotate":
            cluster_ids = [str(x) for x in summary.get("cluster_ids", [])]
            singler_mapping = {str(k): str(v) for k, v in (summary.get("singler_mapping", {}) or {}).items()}
            self._apply_method_mapping(cluster_ids, singler_mapping, "SingleR")
            return

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

        if action == "apply_annotation":
            self.append_log("Main annotation object is ready. Generating annotation plots...")
            QTimer.singleShot(200, self._gen_plots)
            return

        summary_figures = summary.get("figures", [])
        if isinstance(summary_figures, str):
            summary_figures = [summary_figures]
        figures = [
            os.path.join(self._cache_dir(), fig)
            for fig in summary_figures
            if isinstance(fig, str)
        ]

        last_fig = ""
        figure_name_map = {
            "marker_heatmap": "Top Marker Heatmap",
            "marker_bubble_plot_compact": "Top Markers Bubble Plot (Compact)",
            "marker_bubble_plot_full": "Top Markers Bubble Plot (Full)",
            "manual_marker_dotplot_compact": "Manual Marker DotPlot (Compact)",
            "manual_marker_dotplot_full": "Manual Marker DotPlot (Full)",
            "umap_celltype": "UMAP by Cell Type",
            "umap_celltype_split": "UMAP by Group",
            "tsne_celltype": "t-SNE by Cell Type",
            "tsne_celltype_split": "t-SNE by Group",
            "composition_bar": "Main Cell Type Composition",
        }
        compact_preferred = {
            "marker_bubble_plot_compact",
            "manual_marker_dotplot_compact",
            "marker_heatmap",
            "umap_celltype",
            "umap_celltype_split",
            "tsne_celltype",
            "tsne_celltype_split",
            "composition_bar",
        }
        for fig in figures:
            path = fig if os.path.isabs(fig) else os.path.join(self._cache_dir(), fig)
            if os.path.isfile(path):
                stem = os.path.splitext(os.path.basename(path))[0]
                self.main_window.add_preview_item(figure_name_map.get(stem, stem), path, "figure", "Main Annotation")
                last_fig = path

        tables = summary.get("tables", [])
        if isinstance(tables, str):
            tables = [tables]
        table_name_map = {
            "all_markers": "All Markers",
            "top_markers": "Top Markers",
            "composition_main_percent": "Main Composition Percent",
            "singler_mapping": "SingleR Mapping",
            "scina_mapping": "SCINA Mapping",
            "scina_cell_predictions": "SCINA Cell Predictions",
            "cellassign_mapping": "CellAssign Mapping",
            "cellassign_cell_predictions": "CellAssign Cell Predictions",
        }
        for tbl in tables:
            path = tbl if os.path.isabs(tbl) else os.path.join(self._cache_dir(), tbl)
            if os.path.isfile(path):
                stem = os.path.splitext(os.path.basename(path))[0]
                self.main_window.add_preview_item(table_name_map.get(stem, stem), path, "table", "Main Annotation")

        manual_marker_message = str(summary.get("manual_marker_plot_message", "") or "").strip()
        if manual_marker_message:
            self.append_log(manual_marker_message)

        if action == "generate_plots":
            self._set_execute_busy(False)
            preferred = ""
            for fig in figures:
                path = fig if os.path.isabs(fig) else os.path.join(self._cache_dir(), fig)
                name = os.path.splitext(os.path.basename(path))[0]
                if name in compact_preferred:
                    preferred = path
                    break
            if preferred:
                self.main_window.show_preview_image(preferred, f"Main Annotation - {self._reduction().upper()}")
            elif last_fig:
                self.main_window.show_preview_image(last_fig, f"Main Annotation - {self._reduction().upper()}")
            self.project.step_status["annotation"] = "done"
            idx = self.main_window.get_step_index("annotation")
            if idx >= 0:
                self.main_window.sidebar.set_step_status(idx, "done")

    def on_step_error(self, step, summary, detail):
        self._restore_find()
        self._set_execute_busy(False)
        if "SingleR" in step:
            QMessageBox.warning(self, "SingleR automatic annotation failed", summary)
        elif "SCINA" in step:
            QMessageBox.warning(self, "SCINA annotation failed", summary)
        elif "CellAssign" in step:
            QMessageBox.warning(self, "CellAssign annotation failed", summary)
        else:
            QMessageBox.warning(self, "Main annotation failed", summary)

    def run_step(self):
        self._find_markers()
