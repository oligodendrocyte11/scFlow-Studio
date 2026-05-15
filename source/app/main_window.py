from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QTimer, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter, QStackedWidget

from app.config import AppConfig, detect_rscript, load_app_config, save_app_config
from core.cache_manager import CacheManager
from core.project_manager import Project, ProjectManager
from core.r_bridge import RBridge
from core.runtime_paths import get_bundled_rscript, get_icon_path, get_r_scripts_dir, get_resource_path
from core.task_runner import TaskRunner
from ui.pages.p01_project import ProjectPage
from ui.pages.p02_qc import QCPage
from ui.pages.p03_doublet import DoubletPage
from ui.pages.p04_batch import BatchCorrectionPage
from ui.pages.p04_merge_cluster import MergeClusterPage
from ui.pages.p05_annotation import AnnotationPage
from ui.pages.p06_deg import DEGPage
from ui.pages.p06_export import ExportPage
from ui.pages.p07_subcluster import SubclusterPage
from ui.pages.p08_gsea import GSEAStandalonePage
from ui.pages.p09_gene_analysis import GeneAnalysisPage
from ui.pages.p10_module_score import ModuleScorePage
from ui.preview_panel import PreviewPanel
from ui.settings_dialog import SettingsDialog
from ui.sidebar import SideBar
from ui.statusbar import StatusBarManager
from ui.toolbar import ToolBarManager

SUBPROCESS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


STEPS = [
    ("project", "Project and Data", "① Project and Data"),
    ("qc", "Single-Sample QC", "② Single-Sample QC"),
    ("doublet", "Doublet Removal", "③ Doublet Removal"),
    ("batch", "Batch Correction", "④ Batch Correction"),
    ("merge_cluster", "Merge and Clustering", "⑤ Merge and Clustering"),
    ("annotation", "Main Annotation", "⑥ Main Annotation"),
    ("subcluster", "Subcluster Analysis", "⑦ Subcluster Analysis"),
    ("deg", "Differential Expression", "⑧ Differential Expression"),
    ("gsea", "GSEA Enrichment", "⑨ GSEA Enrichment"),
    ("gene_analysis", "Single-Gene Analysis", "⑩ Single-Gene Analysis"),
    ("module_score", "Gene Set Scoring", "⑪ Gene Set Scoring"),
    ("export", "Export Report", "⑫ Export Report"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("scFlow Studio v0.1.0-mvp")
        self.setMinimumSize(QSize(1280, 800))
        self.resize(1600, 900)

        icon_path = get_icon_path()
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.app_config: AppConfig = load_app_config()
        self.project: Project | None = None
        self.project_manager = ProjectManager()

        bundled_rscript = get_bundled_rscript()
        self._bundled_rscript = str(bundled_rscript) if bundled_rscript else ""
        self._active_r_path = self._resolve_r_path()

        self.r_bridge = RBridge(
            r_executable=self._active_r_path,
            scripts_dir=str(get_r_scripts_dir()),
        )
        self.task_runner = TaskRunner(self.r_bridge)
        self.cache_manager = CacheManager()
        self._active_task_page_id: str | None = None

        self._build_ui()
        self._connect_signals()
        self.toolbar_mgr.set_theme(self.app_config.ui_theme)
        self._apply_theme()

        os.environ["SCFLOW_COLOR_SCHEME"] = self.app_config.color_scheme
        self._set_project_state(False)

        QTimer.singleShot(500, self._startup_r_check)

    def _build_ui(self):
        self.toolbar_mgr = ToolBarManager(self)
        self.addToolBar(self.toolbar_mgr.toolbar)

        self.statusbar_mgr = StatusBarManager(self)
        self.setStatusBar(self.statusbar_mgr.statusbar)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.sidebar = SideBar(STEPS)
        self.main_splitter.addWidget(self.sidebar)

        self.page_stack = QStackedWidget()
        self._create_pages()
        self.main_splitter.addWidget(self.page_stack)

        self.preview_panel = PreviewPanel()
        self.main_splitter.addWidget(self.preview_panel)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([200, 800, 420])
        self.setCentralWidget(self.main_splitter)

    def _create_pages(self):
        self.pages = {}
        page_classes = [
            ("project", ProjectPage),
            ("qc", QCPage),
            ("doublet", DoubletPage),
            ("batch", BatchCorrectionPage),
            ("merge_cluster", MergeClusterPage),
            ("annotation", AnnotationPage),
            ("subcluster", SubclusterPage),
            ("deg", DEGPage),
            ("gsea", GSEAStandalonePage),
            ("gene_analysis", GeneAnalysisPage),
            ("module_score", ModuleScorePage),
            ("export", ExportPage),
        ]
        for step_id, page_cls in page_classes:
            page = page_cls(
                main_window=self,
                app_config=self.app_config,
                r_bridge=self.r_bridge,
                task_runner=self.task_runner,
            )
            self.pages[step_id] = page
            self.page_stack.addWidget(page)

    def _connect_signals(self):
        self.sidebar.step_clicked.connect(self._on_step_clicked)
        self.toolbar_mgr.new_project.connect(self._on_new_project)
        self.toolbar_mgr.open_project.connect(self._on_open_project)
        self.toolbar_mgr.save_project.connect(self._on_save_project)
        self.toolbar_mgr.run_step.connect(self._on_run_step)
        self.toolbar_mgr.stop_task.connect(self._on_stop_task)
        self.toolbar_mgr.open_settings.connect(self._on_open_settings)
        self.toolbar_mgr.theme_changed.connect(self._on_theme_changed)

        self.task_runner.progress.connect(self._on_task_progress)
        self.task_runner.log_output.connect(self._on_task_log)
        self.task_runner.finished.connect(self._on_task_finished)
        self.task_runner.error_occurred.connect(self._on_task_error)

    def _resolve_r_path(self) -> str:
        if self._bundled_rscript and os.path.isfile(self._bundled_rscript):
            return self._bundled_rscript

        configured = (self.app_config.r_executable or "").strip()
        if configured and configured != "Rscript" and os.path.isfile(configured):
            return configured

        detected = detect_rscript()
        if detected:
            if configured == "Rscript":
                self.app_config.r_executable = detected
                save_app_config(self.app_config)
            return detected

        return configured or "Rscript"

    def _on_step_clicked(self, index: int):
        if index >= self.page_stack.count():
            return
        self.page_stack.setCurrentIndex(index)
        step_id = STEPS[index][0]
        self.statusbar_mgr.set_status(f"Current step: {STEPS[index][1]}")
        if step_id in self.pages:
            self.pages[step_id].on_page_entered()

    def navigate_to_step(self, step_id: str):
        for i, (sid, _, _) in enumerate(STEPS):
            if sid != step_id:
                continue
            self.sidebar.set_current(i)
            self.page_stack.setCurrentIndex(i)
            if sid in self.pages:
                self.pages[sid].on_page_entered()
            break

    def get_step_index(self, step_id: str) -> int:
        for idx, (sid, _, _) in enumerate(STEPS):
            if sid == step_id:
                return idx
        return -1

    def _on_new_project(self):
        self.pages["project"].start_new_project()
        self.navigate_to_step("project")

    def _on_open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "scFlow Project (project_config.json);;file (*)",
        )
        if not path:
            return
        try:
            self.project = self.project_manager.open_project(path)
            self._set_project_state(True)
            self._restore_project_state()
            self.statusbar_mgr.set_project(self.project)
            self.apply_project_plot_theme(getattr(self.project, "plot_theme", self.app_config.color_scheme))
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _on_save_project(self):
        if self.project:
            self.project_manager.save_project(self.project)
            self.statusbar_mgr.set_status("Project saved")

    def _on_open_settings(self):
        dialog = SettingsDialog(self.app_config, parent=self)
        if dialog.exec():
            self._active_r_path = self._resolve_r_path()
            self.r_bridge.r_exec = self._active_r_path
            self.toolbar_mgr.set_theme(self.app_config.ui_theme)
            self._apply_theme()
            self.statusbar_mgr.set_status(f"Settings saved. R: {self._active_r_path}")

    def _on_theme_changed(self, _index: int):
        self.app_config.ui_theme = self.toolbar_mgr.current_theme()
        save_app_config(self.app_config)
        self._apply_theme()
        theme_name = "" if self.app_config.ui_theme == "dark" else ""
        self.statusbar_mgr.set_status(f"{theme_name}")

    def _apply_theme(self):
        qss_file = get_resource_path("styles", "dark.qss" if self.app_config.ui_theme == "dark" else "main.qss")
        if not qss_file.is_file():
            return
        with qss_file.open("r", encoding="utf-8") as handle:
            qss = handle.read()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(qss)

    def apply_project_plot_theme(self, theme_key: str):
        if not theme_key:
            theme_key = self.app_config.color_scheme
        os.environ["SCFLOW_COLOR_SCHEME"] = theme_key
        if self.project:
            self.project.plot_theme = theme_key
            self.project_manager.save_project(self.project)
        theme_name_map = {
            "publication_classic": "Nature",
            "soft_academic": "Cell",
            "professional_contrast": "Science",
            "warm_story": "Warm Story",
            "fresh_nature": "Fresh Nature",
            "pastel_muted": "Pastel Muted",
            "nordic_mist": "Ocean Mist",
            "sunset_pop": "Cancer Discovery",
            "urban_ink": "Immunity",
            "earth_clay": "Amber Bloom",
        }
        self.statusbar_mgr.set_status(f"Project Plot Theme: {theme_name_map.get(theme_key, theme_key)}")

    def set_project(self, project: Project):
        self.project = project
        self._set_project_state(True)
        self.statusbar_mgr.set_project(project)
        os.environ["SCFLOW_COLOR_SCHEME"] = getattr(project, "plot_theme", self.app_config.color_scheme)
        for page in self.pages.values():
            page.on_project_loaded(project)

    def _restore_project_state(self):
        if not self.project:
            return
        for page in self.pages.values():
            page.on_project_loaded(self.project)
        for i, (step_id, _, _) in enumerate(STEPS):
            status = self.project.step_status.get(step_id, "pending")
            self.sidebar.set_step_status(i, status)
        self._restore_preview_items()

    def _preview_step_label(self, cache_key: str) -> str:
        labels = {
            "qc": "QC",
            "doublet": "Doublet",
            "batch": "Batch",
            "merged": "Clustering",
            "clustering": "Clustering",
            "annotation": "Annotation",
            "subcluster": "Subcluster",
            "deg": "DEG",
            "gsea": "GSEA",
            "gene_analysis": "Gene Analysis",
            "module_score": "Module Scoring",
            "export": "Export",
        }
        return labels.get(cache_key, cache_key.capitalize())

    def _preview_name_from_stem(self, cache_key: str, stem: str) -> str:
        prefix_maps = {
            "deg": {
                "deg_volcano_plot": "DEG Volcano Plot",
                "volcano": "DEG Volcano Plot",
                "deg_results_full": "DEG Full Results",
                "DEG_full": "DEG Full Results",
                "deg_results_significant": "DEG Significant Results",
                "DEG_sig": "DEG Significant Results",
                "deg_summary_statistics": "DEG Summary Statistics",
            },
            "gene_analysis": {
                "single_gene_violin_plot": "Single-Gene Violin Plot",
                "gene_violin_celltypes": "Single-Gene Violin Plot",
                "single_gene_expression_dotplot": "Single-Gene Expression DotPlot",
                "gene_dotplot": "Single-Gene Expression DotPlot",
                "single_gene_featureplot": "Single-Gene FeaturePlot",
                "single_gene_featureplot_by_group": "Single-Gene FeaturePlot by Group",
                "gene_featureplot": "Single-Gene FeaturePlot",
                "single_gene_multi_dotplot": "Multi-Gene DotPlot",
                "gene_multi_dotplot": "Multi-Gene DotPlot",
                "single_gene_group_comparison_plot": "Single-Gene Group Comparison Plot",
                "gene_comparison_plot": "Single-Gene Group Comparison Plot",
                "single_gene_group_comparison_stats": "Single-Gene Group Comparison Statistics",
                "gene_comparison_stats": "Single-Gene Group Comparison Statistics",
                "single_gene_pairwise_celltype_stats": "Single-Gene Cell Type Pairwise Statistics",
                "gene_pairwise_celltype_stats": "Single-Gene Cell Type Pairwise Statistics",
                "single_gene_pairwise_group_stats": "Single-Gene Group Pairwise Statistics",
                "gene_pairwise_group_stats": "Single-Gene Group Pairwise Statistics",
                "single_gene_expression_summary": "Single-Gene Expression Summary",
                "gene_expression_summary": "Single-Gene Expression Summary",
            },
            "module_score": {
                "gene_set_featureplot": "Gene Set FeaturePlot",
                "gene_set_featureplot_by_group": "Gene Set FeaturePlot by Group",
                "module_score_featureplot": "Gene Set FeaturePlot",
                "gene_set_violin_plot": "Gene Set Violin Plot",
                "module_score_violin": "Gene Set Violin Plot",
                "gene_set_dotplot": "Gene Set DotPlot",
                "module_score_dotplot": "Gene Set DotPlot",
                "gene_set_group_comparison_plot": "Gene Set Group Comparison Plot",
                "module_score_comparison_plot": "Gene Set Group Comparison Plot",
                "gene_set_group_comparison_stats": "Gene Set Group Comparison Statistics",
                "module_score_comparison_stats": "Gene Set Group Comparison Statistics",
                "gene_set_pairwise_celltype_stats": "Gene Set Cell Type Pairwise Statistics",
                "module_score_pairwise_celltype_stats": "Gene Set Cell Type Pairwise Statistics",
                "gene_set_pairwise_group_stats": "Gene Set Group Pairwise Statistics",
                "module_score_pairwise_group_stats": "Gene Set Group Pairwise Statistics",
                "gene_set_gene_status": "Gene Set Gene Usage Status",
                "module_score_gene_status": "Gene Set Gene Usage Status",
                "gene_set_per_cell_scores": "Gene Set Per-Cell Scores",
                "module_score_per_cell": "Gene Set Per-Cell Scores",
            },
        }
        mapping = prefix_maps.get(cache_key, {})
        for key, value in mapping.items():
            if stem == key or stem.startswith(f"{key}_") or stem.endswith(f"_{key}"):
                return value
        return stem.replace("_", " ").strip()

    def _restore_preview_items(self):
        if not self.project:
            return
        self.preview_panel.clear_items()
        cache_dir = self.project.cache_dir
        if not os.path.isdir(cache_dir):
            return

        preview_exts = {
            ".png": "figure",
            ".jpg": "figure",
            ".jpeg": "figure",
            ".svg": "figure",
            ".csv": "table",
        }
        collected: list[tuple[float, str, str, str, str]] = []
        for root, _dirs, files in os.walk(cache_dir):
            for file_name in files:
                ext = os.path.splitext(file_name)[1].lower()
                item_type = preview_exts.get(ext)
                if not item_type:
                    continue
                full_path = os.path.join(root, file_name)
                try:
                    mtime = os.path.getmtime(full_path)
                except OSError:
                    mtime = 0.0
                rel_root = os.path.relpath(root, cache_dir)
                cache_key = rel_root.split(os.sep, 1)[0] if rel_root and rel_root != "." else ""
                collected.append((mtime, full_path, item_type, cache_key, os.path.splitext(file_name)[0]))

        collected.sort(key=lambda item: (item[0], item[1]))
        for _mtime, full_path, item_type, cache_key, stem in collected:
            step_label = self._preview_step_label(cache_key)
            preview_name = self._preview_name_from_stem(cache_key, stem)
            self.add_preview_item(preview_name, full_path, item_type, step_label)

    def _set_project_state(self, has_project: bool):
        self.toolbar_mgr.set_project_state(has_project)
        for step_id, page in self.pages.items():
            if step_id != "project":
                page.setEnabled(has_project)

    def _on_run_step(self):
        current_idx = self.page_stack.currentIndex()
        if current_idx < len(self.pages):
            page = list(self.pages.values())[current_idx]
            self.register_task_page(getattr(page, "STEP_ID", ""))
            page.run_step()

    def register_task_page(self, step_id: str):
        self._active_task_page_id = step_id or None

    def _task_target_page(self):
        if self._active_task_page_id and self._active_task_page_id in self.pages:
            return self.pages[self._active_task_page_id]
        return list(self.pages.values())[self.page_stack.currentIndex()]

    def _on_stop_task(self):
        self.task_runner.cancel()

    def _on_task_progress(self, percent: int, message: str):
        self.statusbar_mgr.set_progress(percent, message)

    def _on_task_log(self, text: str):
        self._task_target_page().append_log(text)
        if str(text).strip() == "[TaskRunner] Thread finished":
            self._active_task_page_id = None

    def _on_task_finished(self, result: dict):
        self.statusbar_mgr.set_status("Finished")
        current_page = self._task_target_page()
        current_page.on_step_finished(result)
        if not self.task_runner.is_running:
            self._active_task_page_id = None

    def _on_task_error(self, step: str, summary: str, detail: str):
        self.statusbar_mgr.set_status(f"Error: {summary}")
        current_page = self._task_target_page()
        if hasattr(current_page, "on_step_error"):
            current_page.on_step_error(step, summary, detail)
        if not self.task_runner.is_running:
            self._active_task_page_id = None
        QMessageBox.warning(
            self,
            f"Step Error - {step}",
            f"Error summary: {summary}\n\nDetails:\n{detail}\n\nSuggestion: Please check the parameters or review the Log tab.",
        )

    def show_preview_image(self, path: str, title: str = ""):
        self.preview_panel.show_image(path, title)

    def show_preview_table(self, data: list, headers: list, title: str = ""):
        self.preview_panel.show_table(data, headers, title)

    def add_preview_item(self, name: str, path: str, item_type: str = "figure", step: str = "", pdf_path: str = ""):
        self.preview_panel.add_item(name, path, item_type, step, pdf_path)

    def _startup_r_check(self):
        r_path = self._active_r_path
        if r_path == "Rscript":
            self._show_r_missing_warning()
            return
        if not os.path.isfile(r_path):
            self._show_r_missing_warning()
            return
        try:
            result = subprocess.run(
                [r_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
                creationflags=SUBPROCESS_NO_WINDOW,
            )
            version_text = (result.stdout + result.stderr).strip()
            if version_text:
                self.statusbar_mgr.set_status(f"R ready - {version_text.splitlines()[0]}")
            else:
                self.statusbar_mgr.set_status("R connected")
        except Exception:
            self._show_r_missing_warning()

    def _show_r_missing_warning(self):
        reply = QMessageBox.warning(
            self,
            "R Environment Not Detected",
            "scFlow Studio requires R to run the analysis backend.\n\n"
            "No valid Rscript path was detected.\n\n"
            "Please click 'Open Settings' and specify the Rscript location manually.\n"
            "Example: C:\\Program Files\\R\\R-x.x.x\\bin\\Rscript.exe",
            QMessageBox.Open | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Open:
            self._on_open_settings()

    def closeEvent(self, event):
        if self.task_runner.is_running:
            reply = QMessageBox.question(
                self,
                "Task Running",
                "A task is still running.\n\n"
                "Yes: wait for the task to finish, then exit.\n"
                "No: exit immediately.\n"
                "Cancel: stay in the application.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                self.statusbar_mgr.set_status("Waiting for task completion...")
                self.task_runner.wait_for_completion(60000)
            elif reply == QMessageBox.No:
                self.task_runner.cancel()
            else:
                event.ignore()
                return

        if not self.project:
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "Quit",
            "Save the project before quitting?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            self.project_manager.save_project(self.project)
            event.accept()
        elif reply == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()

    def get_group_order(self) -> list:
        if not self.project or not self.project.samples:
            return []
        seen = set()
        order = []
        for sample in self.project.samples:
            if sample.group and sample.group not in seen:
                seen.add(sample.group)
                order.append(sample.group)
        return order
