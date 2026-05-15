"""
BasePage - all workflow pages inherit from this class.
Provides the common tabs, logs, help panel, and bottom action bar.
"""
import os
import shutil
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTextEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QScrollArea, QHeaderView, QTextBrowser, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt


class BasePage(QWidget):
    """
    Base workflow page. Subclasses should implement:
      - setup_params_ui() -> QWidget
      - get_params() -> dict
      - reset_params()
      - get_help_html() -> str
      - run_step()
      - on_step_finished(result)
    """

    STEP_ID = ""
    STEP_NAME = ""

    def __init__(self, main_window, app_config, r_bridge, task_runner):
        super().__init__()
        self.main_window = main_window
        self.app_config = app_config
        self.r_bridge = r_bridge
        self.task_runner = task_runner
        self.project = None

        self._build_layout()

    def _build_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.page_title = QLabel(self.STEP_NAME)
        self.page_title.setObjectName("page_title")
        layout.addWidget(self.page_title)

        self.workflow_tip = QLabel(self.get_workflow_tip())
        self.workflow_tip.setObjectName("workflow_tip")
        self.workflow_tip.setWordWrap(True)
        layout.addWidget(self.workflow_tip)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("page_tabs")
        layout.addWidget(self.tabs, 1)

        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        params_widget = self.setup_params_ui()
        if params_widget:
            self.params_scroll.setWidget(params_widget)
        self.tabs.addTab(self.params_scroll, "Parameters")

        self.result_table = QTableWidget()
        self.result_table.setAlternatingRowColors(True)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.result_table, "Results")

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        self.tabs.addTab(self.log_text, "Log")

        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)
        self.refresh_help()
        self.tabs.addTab(self.help_browser, "Help")

        self.action_bar = QFrame()
        self.action_bar.setObjectName("page_action_bar")
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(12, 10, 12, 10)
        btn_layout.setSpacing(10)
        self.action_bar.setLayout(btn_layout)

        self.action_hint = QLabel("Suggested workflow: check parameters, preview results when available, run the step, then continue.")
        self.action_hint.setObjectName("action_hint")
        btn_layout.addWidget(self.action_hint, 1)

        self.btn_reset = QPushButton("Restore Defaults")
        self.btn_clear_step = QPushButton("Clear Step Results")
        self.btn_preview = QPushButton("Preview")
        self.btn_run = QPushButton("▶ Run Current Step")
        self.btn_next = QPushButton("Confirm and Continue →")

        self.btn_reset.setProperty("role", "ghost")
        self.btn_clear_step.setProperty("role", "warning")
        self.btn_preview.setProperty("role", "ghost")
        self.btn_run.setProperty("role", "primary")
        self.btn_next.setProperty("role", "success")

        for btn in (self.btn_reset, self.btn_clear_step, self.btn_preview, self.btn_run, self.btn_next):
            btn.setMinimumWidth(128)

        self.btn_reset.clicked.connect(self._handle_reset)
        self.btn_clear_step.clicked.connect(self._handle_clear_step)
        self.btn_preview.clicked.connect(self.preview)
        self.btn_run.clicked.connect(self.run_step)
        self.btn_next.clicked.connect(self.go_next)

        btn_layout.addWidget(self.btn_reset)
        btn_layout.addWidget(self.btn_clear_step)
        btn_layout.addStretch()
        if self.__class__.preview is not BasePage.preview:
            btn_layout.addWidget(self.btn_preview)
        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_next)
        layout.addWidget(self.action_bar)

    def setup_params_ui(self) -> QWidget | None:
        return QWidget()

    def get_params(self) -> dict:
        return {}

    def reset_params(self):
        pass

    def _handle_reset(self):
        try:
            self.reset_params()
            self.refresh_help()
            if self.main_window and hasattr(self.main_window, "statusbar_mgr"):
                self.main_window.statusbar_mgr.set_status("Restore Defaults")
            self.append_log("Default parameters restored.")
        except Exception as e:
            QMessageBox.warning(self, "Failed", f"Failed to restore defaults: {e}")

    def _handle_clear_step(self):
        if not self.require_project():
            return

        reply = QMessageBox.question(
            self,
            "Clear Step Results",
            "This will clear the current step results and reset its status.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.clear_step_results()
            self._reset_step_chain_status()
            self._clear_related_previews()
            self.clear_log()
            if self.main_window and hasattr(self.main_window, "statusbar_mgr"):
                self.main_window.statusbar_mgr.set_status("Current step results cleared")
            self.append_log("Current step results have been cleared. Please rerun this step if needed.")
        except Exception as e:
            QMessageBox.warning(self, "Failed", f"Failed to clear current step results: {e}")

    def _get_step_result_dirs(self) -> list[str]:
        if not self.project:
            return []
        step_dir_map = {
            "project": [self.project.cache_subdir("raw_index")],
            "qc": [self.project.cache_subdir("qc")],
            "doublet": [self.project.cache_subdir("doublet")],
            "batch": [self.project.cache_subdir("batch")],
            "merge_cluster": [self.project.cache_subdir("merged"), self.project.cache_subdir("clustering")],
            "annotation": [self.project.cache_subdir("annotation")],
            "subcluster": [self.project.cache_subdir("subcluster")],
            "deg": [self.project.cache_subdir("deg")],
            "gsea": [self.project.cache_subdir("gsea")],
            "gene_analysis": [self.project.cache_subdir("gene_analysis")],
            "module_score": [self.project.cache_subdir("module_score")],
            "export": [os.path.join(self.project.results_dir, "exports")],
        }
        return step_dir_map.get(self.STEP_ID, [])

    def _get_preview_steps(self) -> list[str]:
        preview_step_map = {
            "qc": ["QC"],
            "doublet": ["Doublet"],
            "batch": ["Batch"],
            "merge_cluster": ["Cluster"],
            "annotation": ["Annotation"],
            "subcluster": ["Subcluster"],
            "deg": ["DEG"],
            "gsea": ["GSEA"],
            "gene_analysis": ["Single-Gene Analysis"],
            "module_score": ["Gene Set Scoring"],
        }
        return preview_step_map.get(self.STEP_ID, [])

    def clear_step_results(self):
        for path in self._get_step_result_dirs():
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                os.makedirs(path, exist_ok=True)

        if self.STEP_ID == "project" and self.project:
            for sample in self.project.samples:
                sample.status = "unchecked"
            if hasattr(self, "_refresh_sample_table"):
                self._refresh_sample_table()

        if self.project:
            self.main_window.project_manager.save_project(self.project)

    def _reset_step_chain_status(self):
        if not self.project:
            return
        steps = list(self.project.step_status.keys())
        if self.STEP_ID not in steps:
            return
        start_idx = steps.index(self.STEP_ID)
        for idx in range(start_idx, len(steps)):
            step_id = steps[idx]
            self.project.step_status[step_id] = "pending"
            self.main_window.sidebar.set_step_status(idx, "pending")
        self.main_window.project_manager.save_project(self.project)

    def _clear_related_previews(self):
        if not hasattr(self.main_window, "preview_panel"):
            return
        for step_name in self._get_preview_steps():
            self.main_window.preview_panel.clear_items(step_name)

    def get_help_html(self) -> str:
        return f"<h3>{self.STEP_NAME}</h3><p>Help.</p>"

    def get_workflow_tip(self) -> str:
        return "Review the page settings, run the step, and inspect the results before continuing."

    def run_step(self):
        pass

    def preview(self):
        pass

    def on_step_finished(self, result):
        pass

    def on_step_error(self, step: str, summary: str, detail: str):
        pass

    def on_project_loaded(self, project):
        self.project = project
        self.refresh_help()

    def on_page_entered(self):
        pass

    def refresh_help(self):
        if hasattr(self, "help_browser"):
            self.help_browser.setHtml(self.get_help_html())

    def bind_help_refresh(self, *widgets):
        signal_names = (
            "valueChanged",
            "textChanged",
            "currentTextChanged",
            "currentIndexChanged",
            "toggled",
            "editingFinished",
            "itemSelectionChanged",
            "itemChanged",
        )
        for widget in widgets:
            if widget is None:
                continue
            for signal_name in signal_names:
                signal = getattr(widget, signal_name, None)
                if signal is None:
                    continue
                try:
                    signal.connect(self.refresh_help)
                except Exception:
                    pass

    def append_log(self, text: str):
        self.log_text.append(text)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self):
        self.log_text.clear()

    def set_result_table(self, data: list[list], headers: list[str]):
        self.result_table.clear()
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        self.result_table.setRowCount(len(data))
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.result_table.setItem(r, c, QTableWidgetItem(str(val)))
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

    def go_next(self):
        if not self.project:
            return
        self.project.step_status[self.STEP_ID] = "done"
        self.main_window.project_manager.save_project(self.project)

        steps = list(self.project.step_status.keys())
        idx = steps.index(self.STEP_ID) if self.STEP_ID in steps else -1
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")
            if idx + 1 < len(steps):
                next_step = steps[idx + 1]
                self.main_window.navigate_to_step(next_step)

    def require_project(self) -> bool:
        if not self.project:
            QMessageBox.warning(self, "Notice", "Please create or open a project first.")
            return False
        return True

    def register_task_owner(self):
        if self.main_window and hasattr(self.main_window, "register_task_page"):
            self.main_window.register_task_page(self.STEP_ID)

    def _object_selection_settings(self) -> dict:
        if not self.project:
            return {}
        settings = self.project.analysis_settings.setdefault("object_selection", {})
        settings.setdefault("subcluster_current_result_id", "")
        settings.setdefault("deg", "main")
        settings.setdefault("gene_analysis", "main")
        settings.setdefault("module_score", "main")
        settings.setdefault("export", "main")
        return settings

    def get_saved_object_source(self, page_key: str, default: str = "main") -> str:
        settings = self._object_selection_settings()
        return str(settings.get(page_key, default) or default)

    def save_object_source_selection(self, page_key: str, source_key: str):
        if not self.project:
            return
        settings = self._object_selection_settings()
        settings[page_key] = str(source_key or "main")
        self.project.analysis_settings["object_selection"] = settings
        self.main_window.project_manager.save_project(self.project)

    def get_subcluster_results(self) -> list[dict]:
        if not self.project:
            return []
        results = list(getattr(self.project, "subcluster_results", []) or [])
        return sorted(results, key=lambda item: (str(item.get("created_at", "")), str(item.get("result_id", ""))))

    def get_subcluster_result_by_id(self, result_id: str) -> dict | None:
        result_id = str(result_id or "").strip()
        for item in self.get_subcluster_results():
            if str(item.get("result_id", "")).strip() == result_id:
                return item
        return None

    def get_subcluster_result_dir(self, result_id: str, ensure: bool = False) -> str:
        if not self.project:
            return ""
        entry = self.get_subcluster_result_by_id(result_id)
        if not entry:
            return ""
        rel_path = str(entry.get("cache_dir_rel", "") or "").replace("/", os.sep)
        if not rel_path:
            return ""
        abs_path = os.path.join(self.project.directory, rel_path)
        if ensure:
            os.makedirs(abs_path, exist_ok=True)
        return abs_path

    def get_current_subcluster_result_id(self) -> str:
        return self.get_saved_object_source("subcluster_current_result_id", default="")

    def save_current_subcluster_result_id(self, result_id: str):
        self.save_object_source_selection("subcluster_current_result_id", result_id)

    def _main_object_paths(self) -> dict:
        if not self.project:
            return {}
        annotation_dir = self.project.cache_subdir("annotation")
        clustering_dir = self.project.cache_subdir("clustering")
        return {
            "annotated_rds": os.path.join(annotation_dir, "annotated.rds"),
            "clustered_rds": os.path.join(clustering_dir, "clustered.rds"),
            "celltype_file": os.path.join(annotation_dir, "cell_types.txt"),
            "summary_json": os.path.join(annotation_dir, "summary.json"),
            "gene_list": os.path.join(annotation_dir, "gene_list.txt"),
            "primary_reduction": os.path.join(clustering_dir, "primary_reduction.txt"),
        }

    def _read_summary_json(self, path: str) -> dict:
        if not path or not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _read_text_lines(self, path: str) -> list[str]:
        if not path or not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return [line.strip() for line in handle if line.strip()]
        except Exception:
            return []

    def get_object_sources(self, include_main: bool = True, include_subclusters: bool = True) -> list[dict]:
        if not self.project:
            return []
        options = []
        main_paths = self._main_object_paths()
        if include_main:
            main_rds = ""
            label = "Object"
            if os.path.isfile(main_paths["annotated_rds"]):
                main_rds = main_paths["annotated_rds"]
            elif os.path.isfile(main_paths["clustered_rds"]):
                main_rds = main_paths["clustered_rds"]
                label = "Object(Annotation)"
            if main_rds:
                reduction_lines = self._read_text_lines(main_paths["primary_reduction"])
                options.append({
                    "key": "main",
                    "label": label,
                    "object_level": "main",
                    "result_id": "",
                    "display_name": label,
                    "input_rds": main_rds.replace("\\", "/"),
                    "label_values": self._read_text_lines(main_paths["celltype_file"]) or self._read_summary_json(main_paths["summary_json"]).get("cell_types", []),
                    "label_columns": ["cell.type", "seurat_clusters"],
                    "preferred_reduction": reduction_lines[0].lower() if reduction_lines else "umap",
                    "summary_json": main_paths["summary_json"].replace("\\", "/"),
                    "source_tag": "main",
                })

        if include_subclusters:
            for item in self.get_subcluster_results():
                result_id = str(item.get("result_id", "")).strip()
                result_dir = self.get_subcluster_result_dir(result_id)
                if not result_dir:
                    continue
                annotated = os.path.join(result_dir, "sub_annotated.rds")
                clustered = os.path.join(result_dir, "subclustered.rds")
                summary_json = os.path.join(result_dir, "summary.json")
                subtypes_txt = os.path.join(result_dir, "subtypes.txt")
                gene_list = os.path.join(result_dir, "gene_list.txt")
                input_rds = annotated if os.path.isfile(annotated) else clustered
                if not os.path.isfile(input_rds):
                    continue
                summary_data = self._read_summary_json(summary_json)
                subtype_values = self._read_text_lines(subtypes_txt) or summary_data.get("subtypes", []) or []
                display_name = str(item.get("display_name", "") or result_id)
                target_display = "+".join(item.get("target_celltypes", []) or [])
                label = f"Subcluster result: {display_name}"
                if target_display and target_display not in display_name:
                    label = f"Subcluster result: {display_name} ({target_display})"
                preferred_reduction = str(item.get("primary_reduction", "") or summary_data.get("primary_reduction", "") or "umap").lower()
                options.append({
                    "key": f"subcluster:{result_id}",
                    "label": label,
                    "object_level": "subcluster",
                    "result_id": result_id,
                    "display_name": display_name,
                    "target_celltypes": item.get("target_celltypes", []),
                    "input_rds": input_rds.replace("\\", "/"),
                    "label_values": subtype_values,
                    "label_columns": ["subtype", "cell.type", "seurat_clusters"],
                    "preferred_reduction": preferred_reduction if preferred_reduction in {"umap", "tsne"} else "umap",
                    "summary_json": summary_json.replace("\\", "/"),
                    "gene_list": gene_list.replace("\\", "/"),
                    "cache_dir": result_dir.replace("\\", "/"),
                    "source_tag": f"subcluster_{result_id}",
                })
        return options

    def resolve_object_source(self, source_key: str) -> dict | None:
        for item in self.get_object_sources():
            if item["key"] == source_key:
                return item
        if source_key != "main":
            for item in self.get_object_sources():
                if item["object_level"] == "subcluster":
                    return item
        return next(iter(self.get_object_sources()), None)
