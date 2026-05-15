from __future__ import annotations

import base64
import glob
import importlib
import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QPainter, QPageLayout, QPageSize, QPdfWriter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
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


class ExportPage(BasePage):
    STEP_ID = "export"
    STEP_NAME = "⑫ Export Report"

    FIGURE_EXTS = (".png", ".pdf", ".jpg", ".jpeg", ".svg")
    RASTER_EXTS = (".png", ".jpg", ".jpeg")
    TABLE_EXTS = (".csv", ".tsv", ".txt")

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp_h5 = QGroupBox("A. Export Objects (h5ad / project .rds)")
        fh = QFormLayout(grp_h5)

        self.cmb_object = QComboBox()
        self.cmb_object.currentIndexChanged.connect(self._on_object_changed)
        fh.addRow("Export object:", self.cmb_object)

        self.txt_h5ad_path = QLineEdit()
        self.txt_h5ad_path.setPlaceholderText("Select h5ad export path...")
        btn_browse_h5 = QPushButton("Browse...")
        btn_browse_h5.clicked.connect(self._browse_h5ad)
        h5_row = QHBoxLayout()
        h5_row.addWidget(self.txt_h5ad_path, 1)
        h5_row.addWidget(btn_browse_h5)
        fh.addRow("h5ad Path:", h5_row)

        self.btn_export_h5 = QPushButton("Export h5ad")
        self.btn_export_h5.setProperty("role", "success")
        self.btn_export_h5.clicked.connect(self._export_h5ad)
        fh.addRow("", self.btn_export_h5)

        self.lbl_h5_status = QLabel("")
        self.lbl_h5_status.setWordWrap(True)
        fh.addRow("", self.lbl_h5_status)

        self.txt_bundle_path = QLineEdit()
        self.txt_bundle_path.setPlaceholderText("Select project bundle export path...")
        btn_browse_bundle = QPushButton("Browse...")
        btn_browse_bundle.clicked.connect(self._browse_bundle_rds)
        bundle_row = QHBoxLayout()
        bundle_row.addWidget(self.txt_bundle_path, 1)
        bundle_row.addWidget(btn_browse_bundle)
        fh.addRow("Projectpath:", bundle_row)

        self.btn_export_bundle = QPushButton("ExportProject.rds")
        self.btn_export_bundle.setProperty("role", "primary")
        self.btn_export_bundle.clicked.connect(self._export_project_bundle)
        fh.addRow("", self.btn_export_bundle)

        self.lbl_bundle_status = QLabel("")
        self.lbl_bundle_status.setWordWrap(True)
        fh.addRow("", self.lbl_bundle_status)

        self.txt_full_seurat_path = QLineEdit()
        self.txt_full_seurat_path.setPlaceholderText("Select full Seurat object export path...")
        btn_browse_full = QPushButton("Browse...")
        btn_browse_full.clicked.connect(self._browse_full_seurat_rds)
        full_row = QHBoxLayout()
        full_row.addWidget(self.txt_full_seurat_path, 1)
        full_row.addWidget(btn_browse_full)
        fh.addRow(" Seurat Path:", full_row)

        self.btn_export_full_seurat = QPushButton("Export Seurat Object.rds")
        self.btn_export_full_seurat.setProperty("role", "success")
        self.btn_export_full_seurat.clicked.connect(self._export_full_seurat_rds)
        fh.addRow("", self.btn_export_full_seurat)

        self.lbl_full_seurat_status = QLabel("")
        self.lbl_full_seurat_status.setWordWrap(True)
        self.lbl_full_seurat_status.setText("Export a full Seurat object for downstream use in R.")
        self.lbl_full_seurat_status.setStyleSheet("color:#666;")
        fh.addRow("", self.lbl_full_seurat_status)
        layout.addWidget(grp_h5)

        grp_fig = QGroupBox("B. Export Image Results")
        ff = QFormLayout(grp_fig)

        self.txt_fig_dir = QLineEdit()
        self.txt_fig_dir.setPlaceholderText("Select image export folder...")
        btn_browse_fig = QPushButton("Browse...")
        btn_browse_fig.clicked.connect(self._browse_fig_dir)
        fig_row = QHBoxLayout()
        fig_row.addWidget(self.txt_fig_dir, 1)
        fig_row.addWidget(btn_browse_fig)
        ff.addRow("Export:", fig_row)

        btn_row = QHBoxLayout()
        self.btn_export_png = QPushButton("Export PNG")
        self.btn_export_pdf = QPushButton("Export PDF")
        self.btn_export_svg = QPushButton("Export SVG")
        self.btn_export_png.setProperty("role", "accent")
        self.btn_export_pdf.setProperty("role", "accent")
        self.btn_export_svg.setProperty("role", "accent")
        self.btn_export_png.clicked.connect(lambda: self._export_figures("png"))
        self.btn_export_pdf.clicked.connect(lambda: self._export_figures("pdf"))
        self.btn_export_svg.clicked.connect(lambda: self._export_figures("svg"))
        btn_row.addWidget(self.btn_export_png)
        btn_row.addWidget(self.btn_export_pdf)
        btn_row.addWidget(self.btn_export_svg)
        ff.addRow("", btn_row)

        self.lbl_fig_status = QLabel("")
        self.lbl_fig_status.setWordWrap(True)
        ff.addRow("", self.lbl_fig_status)
        layout.addWidget(grp_fig)

        grp_tbl = QGroupBox("C. Export Table Results (CSV / TSV / TXT)")
        ft = QFormLayout(grp_tbl)

        self.txt_tbl_dir = QLineEdit()
        self.txt_tbl_dir.setPlaceholderText("Select table export folder...")
        btn_browse_tbl = QPushButton("Browse...")
        btn_browse_tbl.clicked.connect(self._browse_tbl_dir)
        tbl_row = QHBoxLayout()
        tbl_row.addWidget(self.txt_tbl_dir, 1)
        tbl_row.addWidget(btn_browse_tbl)
        ft.addRow("Export:", tbl_row)

        self.btn_export_csv = QPushButton("Export All Tables")
        self.btn_export_csv.setProperty("role", "success")
        self.btn_export_csv.clicked.connect(self._export_tables)
        ft.addRow("", self.btn_export_csv)

        self.lbl_tbl_status = QLabel("")
        self.lbl_tbl_status.setWordWrap(True)
        ft.addRow("", self.lbl_tbl_status)
        layout.addWidget(grp_tbl)

        self.bind_help_refresh(
            self.cmb_object,
            self.txt_h5ad_path,
            self.txt_bundle_path,
            self.txt_full_seurat_path,
            self.txt_fig_dir,
            self.txt_tbl_dir,
        )
        return container

    def get_params(self) -> dict:
        return {"seed": self.app_config.default_seed}

    def reset_params(self):
        self.cmb_object.setCurrentIndex(0)
        self.txt_h5ad_path.clear()
        self.txt_bundle_path.clear()
        self.txt_full_seurat_path.clear()
        self.txt_fig_dir.clear()
        self.txt_tbl_dir.clear()
        self.lbl_h5_status.clear()
        self.lbl_bundle_status.clear()
        self.lbl_full_seurat_status.setText("Export a full Seurat object for downstream use in R.")
        self.lbl_full_seurat_status.setStyleSheet("color:#666;")
        self.lbl_fig_status.clear()
        self.lbl_tbl_status.clear()

    def get_help_html(self) -> str:
        object_choice = self.cmb_object.currentText() if self.cmb_object.count() else "No export object selected"
        return build_step_help("export", {"object_choice": object_choice})

    def on_page_entered(self):
        self._refresh_objects()
        self._ensure_default_export_dirs()
        self._refresh_export_counts()
        self.refresh_help()

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_objects()
        self._ensure_default_export_dirs()
        self._refresh_export_counts()
        self.refresh_help()

    def _ensure_default_export_dirs(self):
        if not self.project:
            return
        if not self.txt_fig_dir.text().strip():
            self.txt_fig_dir.setText(self.project.figures_dir())
        if not self.txt_tbl_dir.text().strip():
            self.txt_tbl_dir.setText(self.project.tables_dir())

    def _refresh_export_counts(self):
        if not self.project:
            return
        roots = self._project_export_roots()
        figures = list(self._iter_project_files(self.FIGURE_EXTS))
        tables = list(self._iter_project_files(self.TABLE_EXTS))
        root_text = "; ".join(roots) if roots else os.path.join(self.project.directory, "cache")
        self.lbl_fig_status.setText(f"Scan root: {root_text}\nFound {len(figures)} image files.")
        self.lbl_fig_status.setStyleSheet("color:#666;")
        self.lbl_tbl_status.setText(f"Scan root: {root_text}\nFound {len(tables)} table files.")
        self.lbl_tbl_status.setStyleSheet("color:#666;")

    def _refresh_objects(self):
        self.cmb_object.clear()
        if not self.project:
            self.refresh_help()
            return

        current_key = self.cmb_object.currentData() or self.get_saved_object_source("export", default="main")
        options = self.get_object_sources()
        for source in options:
            self.cmb_object.addItem(source["label"], source["key"])
        idx = self.cmb_object.findData(current_key)
        if idx >= 0:
            self.cmb_object.setCurrentIndex(idx)

        info_parts = []
        for source in options:
            if source.get("object_level") == "main":
                info_parts.append("Object(cell.type)")
            else:
                info_parts.append(f"{source.get('display_name', source.get('label'))} (subtype)")
        if info_parts:
            self.lbl_h5_status.setText("Export object: " + "; ".join(info_parts))
            self.lbl_h5_status.setStyleSheet("color:#2196F3;")
        else:
            self.lbl_h5_status.setText("Export the Seurat object after clustering or annotation is finished.")
            self.lbl_h5_status.setStyleSheet("color:#FF9800;")
        self.refresh_help()

    def _on_object_changed(self, _idx: int):
        if self.cmb_object.currentData():
            self.save_object_source_selection("export", str(self.cmb_object.currentData()))

    def _browse_h5ad(self):
        default_name = f"{self.project.name}_export.h5ad" if self.project else "scflow_export.h5ad"
        path, _ = QFileDialog.getSaveFileName(self, "Choose h5ad export location", default_name, "h5ad (*.h5ad)")
        if path:
            if not path.lower().endswith(".h5ad"):
                path += ".h5ad"
            self.txt_h5ad_path.setText(path)

    def _browse_bundle_rds(self):
        default_name = f"{self.project.name}_project_bundle.rds" if self.project else "scflow_project_bundle.rds"
        path, _ = QFileDialog.getSaveFileName(self, "Choose project bundle export location", default_name, "RDS (*.rds)")
        if path:
            if not path.lower().endswith(".rds"):
                path += ".rds"
            self.txt_bundle_path.setText(path)

    def _browse_full_seurat_rds(self):
        default_name = (
            f"{self.project.name}_full_seurat_with_annotations.rds"
            if self.project else
            "scflow_full_seurat_with_annotations.rds"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Choose full Seurat object export location", default_name, "RDS (*.rds)")
        if path:
            if not path.lower().endswith(".rds"):
                path += ".rds"
            self.txt_full_seurat_path.setText(path)

    def _browse_fig_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Export")
        if directory:
            self.txt_fig_dir.setText(directory)

    def _browse_tbl_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Export Tables")
        if directory:
            self.txt_tbl_dir.setText(directory)

    @staticmethod
    def _copy_if_exists(src: str, dst: str):
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    @staticmethod
    def _write_svg_wrapper(image_path: str, svg_path: str):
        with open(image_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        image = QImage(image_path)
        width = max(image.width(), 1)
        height = max(image.height(), 1)
        mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
            f'  <image width="{width}" height="{height}" xlink:href="data:{mime};base64,{encoded}" />\n'
            '</svg>\n'
        )
        os.makedirs(os.path.dirname(svg_path), exist_ok=True)
        with open(svg_path, "w", encoding="utf-8") as handle:
            handle.write(svg)

    @staticmethod
    def _render_svg_to_png(svg_path: str, png_path: str) -> bool:
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return False
        size = renderer.defaultSize()
        width = max(size.width(), 1600)
        height = max(size.height(), 1200)
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        os.makedirs(os.path.dirname(png_path), exist_ok=True)
        return image.save(png_path, "PNG")

    @staticmethod
    def _render_svg_to_pdf(svg_path: str, pdf_path: str) -> bool:
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return False
        size = renderer.defaultSize()
        width = max(size.width(), 1600)
        height = max(size.height(), 1200)
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

        writer = QPdfWriter(pdf_path)
        writer.setResolution(300)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageOrientation(QPageLayout.Landscape if width >= height else QPageLayout.Portrait)
        painter = QPainter(writer)
        try:
            viewport = painter.viewport()
            target_w = viewport.width()
            target_h = int(target_w * height / max(width, 1))
            if target_h > viewport.height():
                target_h = viewport.height()
                target_w = int(target_h * width / max(height, 1))
            x = max((viewport.width() - target_w) // 2, 0)
            y = max((viewport.height() - target_h) // 2, 0)
            renderer.render(painter, QRectF(x, y, target_w, target_h))
        finally:
            painter.end()
        return os.path.isfile(pdf_path)

    @staticmethod
    def _group_export_variants(paths: list[str]) -> dict[str, dict[str, str]]:
        grouped: dict[str, dict[str, str]] = {}
        for src in paths:
            rel_path = Path(src)
            key = str(rel_path.with_suffix(""))
            grouped.setdefault(key, {})[rel_path.suffix.lower()] = src
        return grouped

    def _project_export_roots(self) -> list[str]:
        if not self.project:
            return []
        roots: list[str] = []
        candidates = [
            os.path.join(self.project.directory, "cache"),
            getattr(self.project, "cache_dir", ""),
        ]
        for candidate in candidates:
            if candidate:
                norm = os.path.normpath(candidate)
                if os.path.isdir(norm) and norm not in roots:
                    roots.append(norm)
        # ProjectProject cache Case.
        if not roots and os.path.isdir(self.project.directory):
            for current_root, dirnames, _filenames in os.walk(self.project.directory):
                if os.path.basename(current_root).lower() == "cache":
                    roots.append(os.path.normpath(current_root))
                    break
                dirnames[:] = [d for d in dirnames if d not in {"results", "logs", "__pycache__", ".git", ".idea"}]
        return roots

    def _iter_project_files(self, extensions: tuple[str, ...]):
        if not self.project:
            return
        allowed = tuple(ext.lower() for ext in extensions)
        seen = set()
        for root in self._project_export_roots():
            for current_root, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in {"__pycache__", ".git", ".idea", ".pytest_cache"}
                ]
                for filename in filenames:
                    path = os.path.join(current_root, filename)
                    if os.path.splitext(filename)[1].lower() not in allowed:
                        continue
                    norm = os.path.normpath(path)
                    if norm in seen:
                        continue
                    seen.add(norm)
                    yield path

    def _relative_project_path(self, src_path: str) -> str:
        src_path = os.path.normpath(src_path)
        base = os.path.normpath(self.project.directory) if self.project else ""
        try:
            rel = os.path.relpath(src_path, base)
        except Exception:
            rel = os.path.basename(src_path)
        if rel.startswith(".."):
            rel = os.path.basename(src_path)
        return rel.replace("\\", "/")

    def _copy_with_relative_path(self, src_path: str, out_root: str, new_extension: str | None = None) -> str:
        rel = self._relative_project_path(src_path)
        rel_path = Path(rel)
        if new_extension:
            rel_path = rel_path.with_suffix(new_extension)
        dst_path = os.path.join(out_root, str(rel_path))
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return dst_path

    def _candidate_export_objects(self) -> list[tuple[str, str]]:
        return [(source["label"], source["input_rds"]) for source in self.get_object_sources() if source.get("input_rds")]

    def _selected_object_rds(self) -> str:
        selected = self.cmb_object.currentText().strip()
        for label, path in self._candidate_export_objects():
            if label == selected:
                return path.replace("\\", "/")
        return ""

    def _prepare_bundle_project_mirror(self, stage_root: str) -> str:
        mirror_root = os.path.join(stage_root, "project_mirror")
        os.makedirs(mirror_root, exist_ok=True)
        self._copy_if_exists(os.path.join(self.project.directory, "project_config.json"), os.path.join(mirror_root, "project_config.json"))
        self._copy_if_exists(os.path.join(self.project.directory, "samples.json"), os.path.join(mirror_root, "samples.json"))

        for src in self._iter_project_files(self.FIGURE_EXTS + self.TABLE_EXTS + (".json", ".rds")):
            dst = os.path.join(mirror_root, self._relative_project_path(src))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        return mirror_root

    def _get_h5ad_dependency_errors(self) -> list[str]:
        required_modules = {
            "numpy": "numpy",
            "pandas": "pandas",
            "scipy": "scipy",
            "h5py": "h5py",
        }
        problems = []
        for module_name, display in required_modules.items():
            try:
                importlib.import_module(module_name)
            except Exception as exc:
                problems.append(f"{display}: {exc}")
        return problems

    def _export_h5ad(self):
        if not self.require_project():
            return

        output_h5ad = self.txt_h5ad_path.text().strip()
        if not output_h5ad:
            QMessageBox.warning(self, "Notice", "Please choose an h5ad export path.")
            return
        if not output_h5ad.lower().endswith(".h5ad"):
            output_h5ad += ".h5ad"

        input_rds = self._selected_object_rds()
        if not input_rds or not os.path.isfile(input_rds):
            QMessageBox.warning(self, "Notice", "Cannot find an object for h5ad export. Please finish clustering or annotation first.")
            return

        self.clear_log()
        self.btn_export_h5.setText("Exporting...")
        self.btn_export_h5.setEnabled(False)
        self.lbl_h5_status.setText("Exporting intermediate R files...")
        self.lbl_h5_status.setStyleSheet("color:#666;")
        self.append_log("=== Export h5ad ===")
        self.append_log(f"  Input: {input_rds}")
        self.append_log(f"  Output: {output_h5ad}")

        self.append_log("Preparing export...")
        temp_dir = self.r_bridge.create_safe_runtime_dir("export_h5ad_temp")
        os.makedirs(temp_dir, exist_ok=True)
        staged_input_rds = os.path.join(temp_dir, "input_object.rds")
        self.append_log("Copying input object to a safe staging file...")
        shutil.copy2(input_rds, staged_input_rds)
        self.append_log(f"  Staged input: {staged_input_rds}")

        params = {
            "input_rds": staged_input_rds.replace("\\", "/"),
            "output_dir": temp_dir.replace("\\", "/"),
            "seed": self.app_config.default_seed,
        }
        self._pending_h5ad_path = output_h5ad
        self._pending_temp_dir = temp_dir
        self.register_task_owner()
        self.task_runner.run_r_script("11_export_h5ad.R", params, temp_dir, "Export h5ad")

    def _export_project_bundle(self):
        if not self.require_project():
            return

        output_rds = self.txt_bundle_path.text().strip()
        if not output_rds:
            QMessageBox.warning(self, "Notice", "Please choose a project bundle export path.")
            return
        if not output_rds.lower().endswith(".rds"):
            output_rds += ".rds"

        self.clear_log()
        self.btn_export_bundle.setText("Exporting...")
        self.btn_export_bundle.setEnabled(False)
        self.lbl_bundle_status.setText("Preparing project bundle...")
        self.lbl_bundle_status.setStyleSheet("color:#666;")
        self.append_log("=== Export Project Bundle RDS ===")
        self.append_log(f"  Project Directory: {self.project.directory}")
        self.append_log(f"  File: {output_rds}")

        self.append_log("Preparing export...")
        export_dir = self.r_bridge.create_safe_runtime_dir("export_project_bundle")
        os.makedirs(export_dir, exist_ok=True)
        staged_output_rds = os.path.join(export_dir, "project_bundle_export.rds")
        self.append_log("Preparing project files for export...")
        mirror_project_dir = self._prepare_bundle_project_mirror(export_dir)
        self.append_log(f"  Mirrored project: {mirror_project_dir}")

        params = {
            "project_dir": mirror_project_dir.replace("\\", "/"),
            "output_rds": staged_output_rds.replace("\\", "/"),
            "output_dir": export_dir.replace("\\", "/"),
            "seed": self.app_config.default_seed,
        }
        self._pending_bundle_path = output_rds
        self._pending_bundle_stage_dir = export_dir
        self._pending_bundle_stage_path = staged_output_rds
        self.register_task_owner()
        self.task_runner.run_r_script("12_export_project_bundle.R", params, export_dir, "Export Project Bundle")

    def _export_full_seurat_rds(self):
        if not self.require_project():
            return

        output_rds = self.txt_full_seurat_path.text().strip()
        if not output_rds:
            QMessageBox.warning(self, "Notice", "Please choose a full Seurat object export path.")
            return
        if not output_rds.lower().endswith(".rds"):
            output_rds += ".rds"

        self.clear_log()
        self.btn_export_full_seurat.setText("Exporting...")
        self.btn_export_full_seurat.setEnabled(False)
        self.lbl_full_seurat_status.setText("Exporting full Seurat object...")
        self.lbl_full_seurat_status.setStyleSheet("color:#666;")
        self.append_log("=== Export Full Seurat Object RDS ===")
        self.append_log(f"  Project Directory: {self.project.directory}")
        self.append_log(f"  File: {output_rds}")

        export_dir = self.r_bridge.create_safe_runtime_dir("export_full_seurat")
        os.makedirs(export_dir, exist_ok=True)
        staged_output_rds = os.path.join(export_dir, "full_seurat_export.rds")
        params = {
            "project_dir": self.project.directory.replace("\\", "/"),
            "output_rds": staged_output_rds.replace("\\", "/"),
            "output_dir": export_dir.replace("\\", "/"),
            "seed": self.app_config.default_seed,
        }
        self._pending_full_seurat_path = output_rds
        self._pending_full_seurat_stage_dir = export_dir
        self._pending_full_seurat_stage_path = staged_output_rds
        self.register_task_owner()
        self.task_runner.run_r_script("13_export_full_seurat.R", params, export_dir, "Export Seurat Object.rds")

    def on_step_finished(self, result):
        summary = result.summary if hasattr(result, "summary") else (result if isinstance(result, dict) else {})
        method = summary.get("method", "")

        if method == "intermediate_files":
            self.lbl_h5_status.setText("R intermediate export completed. Assembling h5ad...")
            self.lbl_h5_status.setStyleSheet("color:#666;")
            self.append_log("R intermediate export completed. Starting Python assembly...")
            QTimer.singleShot(200, self._assemble_h5ad)
            return

        if method == "project_bundle_rds":
            staged_output_rds = summary.get("output_rds", getattr(self, "_pending_bundle_stage_path", ""))
            output_rds = getattr(self, "_pending_bundle_path", "")
            if staged_output_rds and output_rds and os.path.isfile(staged_output_rds):
                shutil.copy2(staged_output_rds, output_rds)
            size_mb = os.path.getsize(output_rds) / (1024 * 1024) if output_rds and os.path.exists(output_rds) else 0.0
            self.btn_export_bundle.setText("Export Project Bundle RDS")
            self.btn_export_bundle.setEnabled(True)
            self.lbl_bundle_status.setText(f"Export succeeded ({size_mb:.1f} MB)")
            self.lbl_bundle_status.setStyleSheet("color:#4CAF50; font-weight:bold;")
            self.append_log("Project export succeeded.")
            if output_rds:
                self.append_log(f"  File: {output_rds}")
            QMessageBox.information(
                self,
                "Export succeeded",
                "Project bundle RDS exported successfully.\n\n"
                f"File: {output_rds}\n"
                f"Object: {summary.get('n_objects', 0)}\n"
                f"Tables: {summary.get('n_tables', 0)}\n"
                f"summary: {summary.get('n_summaries', 0)}",
            )
            try:
                shutil.rmtree(getattr(self, "_pending_bundle_stage_dir", ""), ignore_errors=True)
            except Exception:
                pass
            return

        if method == "full_seurat_rds":
            staged_output_rds = summary.get("output_rds", getattr(self, "_pending_full_seurat_stage_path", ""))
            output_rds = getattr(self, "_pending_full_seurat_path", "")
            if staged_output_rds and output_rds and os.path.isfile(staged_output_rds):
                shutil.copy2(staged_output_rds, output_rds)
            size_mb = os.path.getsize(output_rds) / (1024 * 1024) if output_rds and os.path.exists(output_rds) else 0.0
            reduction_parts = [name.upper() for name in summary.get("reductions", []) if str(name).strip()]
            reduction_ = ", ".join(reduction_parts) if reduction_parts else ""
            subtype_ = "Merged" if summary.get("subtype_merged") else ""
            n_subcluster_results = int(summary.get("n_subcluster_results", 0) or 0)
            self.btn_export_full_seurat.setText("Export Full Seurat Object RDS")
            self.btn_export_full_seurat.setEnabled(True)
            self.lbl_full_seurat_status.setText(
                f"Export succeeded ({size_mb:.1f} MB, {subtype_} subcluster annotation, subcluster results={n_subcluster_results})"
            )
            self.lbl_full_seurat_status.setStyleSheet("color:#4CAF50; font-weight:bold;")
            self.append_log("Seurat object export succeeded.")
            if output_rds:
                self.append_log(f"  File: {output_rds}")
            QMessageBox.information(
                self,
                "Export succeeded",
                "Full Seurat object RDS exported successfully.\n\n"
                f"File: {output_rds}\n"
                f"Object: {summary.get('source_object', '')}\n"
                f"cells: {summary.get('n_cells', 0)}\n"
                f"genes: {summary.get('n_features', 0)}\n"
                f"Subcluster annotation: {subtype_}\n"
                f"Subcluster results: {n_subcluster_results}\n"
                f"Reductions: {reduction_}",
            )
            try:
                shutil.rmtree(getattr(self, "_pending_full_seurat_stage_dir", ""), ignore_errors=True)
            except Exception:
                pass
            return

        self.btn_export_h5.setText("Export h5ad")
        self.btn_export_h5.setEnabled(True)

    def on_step_error(self, step, summary, detail):
        self.btn_export_h5.setText("Export h5ad")
        self.btn_export_h5.setEnabled(True)
        self.btn_export_bundle.setText("Export Project Bundle RDS")
        self.btn_export_bundle.setEnabled(True)
        self.btn_export_full_seurat.setText("Export Full Seurat Object RDS")
        self.btn_export_full_seurat.setEnabled(True)
        if "Project" in step:
            self.lbl_bundle_status.setText("Export failed")
            self.lbl_bundle_status.setStyleSheet("color:#C62828; font-weight:bold;")
            try:
                shutil.rmtree(getattr(self, "_pending_bundle_stage_dir", ""), ignore_errors=True)
            except Exception:
                pass
        elif " Seurat" in step:
            self.lbl_full_seurat_status.setText("Export failed")
            self.lbl_full_seurat_status.setStyleSheet("color:#C62828; font-weight:bold;")
            try:
                shutil.rmtree(getattr(self, "_pending_full_seurat_stage_dir", ""), ignore_errors=True)
            except Exception:
                pass
        else:
            self.lbl_h5_status.setText("Export failed")
            self.lbl_h5_status.setStyleSheet("color:#C62828; font-weight:bold;")

    def _assemble_h5ad(self):
        temp_dir = getattr(self, "_pending_temp_dir", "")
        output_path = getattr(self, "_pending_h5ad_path", "")
        try:
            self.append_log("Checking Python dependencies...")
            QApplication.processEvents()
            dependency_errors = self._get_h5ad_dependency_errors()
            if dependency_errors:
                raise ImportError(
                    "h5ad Export, Please confirm:numpy, pandas, scipy, h5py.\n"
                    + "\n".join(dependency_errors)
                )

            import h5py
            import numpy as np
            import pandas as pd
            import scipy.io
            import scipy.sparse

            mtx_path = os.path.join(temp_dir, "counts.mtx")
            barcodes_path = os.path.join(temp_dir, "barcodes.tsv")
            features_path = os.path.join(temp_dir, "features.tsv")
            meta_path = os.path.join(temp_dir, "metadata.csv")
            if not os.path.exists(mtx_path):
                raise FileNotFoundError(f"Cannot find counts.mtx: {mtx_path}")

            self.append_log("Loading counts.mtx from the staged files...")
            QApplication.processEvents()
            with open(barcodes_path, "r", encoding="utf-8") as handle:
                barcodes = [line.strip() for line in handle if line.strip()]
            with open(features_path, "r", encoding="utf-8") as handle:
                features = [line.strip() for line in handle if line.strip()]

            X = scipy.io.mmread(mtx_path)
            self.append_log(f" matrix: {X.shape}")
            self.append_log(f"  barcodes: {len(barcodes)}, features: {len(features)}")
            QApplication.processEvents()

            if X is None or X.shape == (0, 0) or X.shape[0] == 0 or X.shape[1] == 0:
                raise ValueError("The export matrix is empty. Please check the selected object.")
            if not scipy.sparse.issparse(X):
                X = scipy.sparse.coo_matrix(X)

            raw_shape = X.shape
            if raw_shape == (len(features), len(barcodes)):
                X = X.T.tocsc()
            elif raw_shape == (len(barcodes), len(features)):
                X = X.tocsc()
            else:
                raise ValueError(
                    f"matrix barcodes/features:counts={raw_shape}, barcodes={len(barcodes)}, features={len(features)}."
                )

            obs = pd.read_csv(meta_path, index_col=0)
            obs = obs.reindex(barcodes)
            if obs.shape[0] != len(barcodes):
                raise ValueError("The metadata row count does not match exported cells.")
            if obs.index.hasnans:
                raise ValueError("Metadata barcodes are invalid; unable to write h5ad.")

            sub_info = self._merge_subtype_metadata(obs)
            if sub_info:
                self.append_log(f"  Merged subcluster annotation: {sub_info}")

            var = pd.DataFrame(index=features)
            def _str_dtype():
                return h5py.string_dtype(encoding="utf-8")

            def _write_string_dataset(group, key, values):
                data = np.asarray(["" if pd.isna(v) else str(v) for v in values], dtype=object)
                ds = group.create_dataset(key, data=data, dtype=_str_dtype())
                ds.attrs["encoding-type"] = "string-array"
                ds.attrs["encoding-version"] = "0.2.0"
                return ds

            def _write_array_dataset(group, key, values):
                arr = np.asarray(values)
                ds = group.create_dataset(key, data=arr)
                ds.attrs["encoding-type"] = "array"
                ds.attrs["encoding-version"] = "0.2.0"
                return ds

            def _write_series(group, key, series):
                if pd.api.types.is_bool_dtype(series):
                    _write_array_dataset(group, key, series.fillna(False).astype(bool).to_numpy())
                elif pd.api.types.is_integer_dtype(series):
                    _write_array_dataset(group, key, series.fillna(0).astype("int64").to_numpy())
                elif pd.api.types.is_float_dtype(series):
                    _write_array_dataset(group, key, series.astype("float64").to_numpy())
                else:
                    _write_string_dataset(group, key, series.astype("string").fillna("").tolist())

            def _write_dataframe_group(handle, key, df):
                grp = handle.create_group(key)
                grp.attrs["encoding-type"] = "dataframe"
                grp.attrs["encoding-version"] = "0.2.0"
                grp.attrs["_index"] = "_index"
                grp.attrs["column-order"] = np.asarray(df.columns.tolist(), dtype=_str_dtype())
                _write_string_dataset(grp, "_index", df.index.astype(str).tolist())
                for col in df.columns:
                    _write_series(grp, str(col), df[col])
                return grp

            def _write_dict_group(handle, key):
                grp = handle.create_group(key)
                grp.attrs["encoding-type"] = "dict"
                grp.attrs["encoding-version"] = "0.1.0"
                return grp

            def _write_sparse_matrix_group(handle, key, matrix):
                grp = handle.create_group(key)
                grp.attrs["encoding-type"] = "csc_matrix"
                grp.attrs["encoding-version"] = "0.1.0"
                matrix = matrix.tocsc()
                grp.attrs["shape"] = tuple(int(x) for x in matrix.shape)
                grp.create_dataset("data", data=matrix.data)
                grp.create_dataset("indices", data=matrix.indices.astype("int32"))
                grp.create_dataset("indptr", data=matrix.indptr.astype("int32"))
                return grp

            self.append_log("Assembling h5ad structure...")
            QApplication.processEvents()
            with h5py.File(output_path, "w") as handle:
                handle.attrs["encoding-type"] = "anndata"
                handle.attrs["encoding-version"] = "0.1.0"
                _write_sparse_matrix_group(handle, "X", X)
                _write_dataframe_group(handle, "obs", obs)
                _write_dataframe_group(handle, "var", var)
                obsm_group = _write_dict_group(handle, "obsm")
                _write_dict_group(handle, "uns")
                _write_dict_group(handle, "layers")
                _write_dict_group(handle, "obsp")
                _write_dict_group(handle, "varm")
                _write_dict_group(handle, "varp")

                for emb_file in glob.glob(os.path.join(temp_dir, "embedding_*.csv")):
                    emb_name = os.path.basename(emb_file).replace("embedding_", "").replace(".csv", "")
                    emb_df = pd.read_csv(emb_file, index_col=0)
                    emb_df = emb_df.reindex(barcodes)
                    if emb_df.shape[0] != len(barcodes) or emb_df.index.hasnans:
                        raise ValueError(f"embedding_{emb_name}.csv barcodes.")
                    ds = obsm_group.create_dataset(f"X_{emb_name}", data=emb_df.to_numpy(dtype="float64"))
                    ds.attrs["encoding-type"] = "array"
                    ds.attrs["encoding-version"] = "0.2.0"
                    self.append_log(f"  obsm['X_{emb_name}']: {emb_df.shape}")

            fsize = os.path.getsize(output_path) / (1024 * 1024)
            self.append_log("h5ad export succeeded.")
            self.append_log(f"  File: {output_path}")
            self.append_log(f"  Size: {fsize:.1f} MB")
            self.append_log(f"  cells: {X.shape[0]}, genes: {X.shape[1]}")
            self.lbl_h5_status.setText(f"Export succeeded ({fsize:.1f} MB)")
            self.lbl_h5_status.setStyleSheet("color:#4CAF50; font-weight:bold;")
            QMessageBox.information(
                self,
                "Export succeeded",
                f"h5ad exported successfully.\n\nFile: {output_path}\n{X.shape[0]} cells x {X.shape[1]} genes\n: {fsize:.1f} MB",
            )
        except ImportError as exc:
            self.append_log(f"Missing Python: {exc}")
            self.lbl_h5_status.setText("Missing h5ad Export")
            self.lbl_h5_status.setStyleSheet("color:#C62828; font-weight:bold;")
            QMessageBox.critical(
                self,
                "Missing Python ",
                "Missing h5ad Export.\n\n"
                ":numpy, pandas, scipy, h5py\n"
                ",;,.\n\n"
                f"Details:\n{exc}",
            )
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            self.append_log(f"h5ad Failed: {exc}")
            self.append_log(tb)
            self.lbl_h5_status.setText("Export failed")
            self.lbl_h5_status.setStyleSheet("color:#C62828; font-weight:bold;")
            QMessageBox.critical(self, "Export failed", f"h5ad export failed:\n\n{exc}")
        finally:
            self.btn_export_h5.setText("Export h5ad")
            self.btn_export_h5.setEnabled(True)
            try:
                shutil.rmtree(getattr(self, "_pending_temp_dir", ""), ignore_errors=True)
            except Exception:
                pass

    def _merge_subtype_metadata(self, obs):
        if not self.project:
            return None
        sub_meta_csv = os.path.join(self.project.cache_subdir("subcluster"), "sub_metadata.csv")
        if not os.path.exists(sub_meta_csv):
            if "subtype" in obs.columns:
                return f"subtype already present in obs ({obs['subtype'].nunique()} categories)"
            return None
        try:
            import pandas as pd
            sub_obs = pd.read_csv(sub_meta_csv, index_col=0)
            if "subtype" in sub_obs.columns:
                obs["subtype"] = sub_obs.reindex(obs.index)["subtype"]
                n_annotated = int(obs["subtype"].notna().sum())
                return f"subtype merged for {n_annotated} cells"
        except Exception:
            pass
        return None

    def _export_figures(self, fmt: str = "png"):
        if not self.require_project():
            return
        out_dir = self.txt_fig_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Notice", "Export.")
            return
        os.makedirs(out_dir, exist_ok=True)

        roots = self._project_export_roots()
        all_figures = list(self._iter_project_files(self.FIGURE_EXTS))
        self.clear_log()
        self.append_log(f"=== Export {fmt.upper()} ===")
        self.append_log("  Source roots: " + ("; ".join(roots) if roots else "cache"))
        self.append_log(f"Figure files found: {len(all_figures)}")
        if not all_figures:
            self.lbl_fig_status.setText("Figure export completed.")
            self.lbl_fig_status.setStyleSheet("color:#C62828; font-weight:bold;")
            QMessageBox.information(self, "Notice", "No figures were exported. Please confirm that the project cache folder contains figure files.")
            return

        exported = 0
        failed = []
        grouped = {}
        for src in all_figures:
            rel = self._relative_project_path(src)
            rel_path = Path(rel)
            key = str(rel_path.with_suffix(""))
            grouped.setdefault(key, {})[rel_path.suffix.lower()] = src

        for rel_base, variants in grouped.items():
            try:
                if fmt == "png":
                    dst = os.path.join(out_dir, str(Path(rel_base).with_suffix(".png")))
                    if ".png" in variants:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(variants[".png"], dst)
                        exported += 1
                    elif ".jpg" in variants or ".jpeg" in variants:
                        raster_src = variants.get(".jpg") or variants.get(".jpeg")
                        image = QImage(raster_src)
                        if image.isNull() or not image.save(dst, "PNG"):
                            raise RuntimeError("Unable to convert JPG/JPEG to PNG")
                        exported += 1
                    elif ".svg" in variants:
                        if not self._render_svg_to_png(variants[".svg"], dst):
                            raise RuntimeError("Unable to convert SVG to PNG")
                        exported += 1
                elif fmt == "pdf":
                    dst = os.path.join(out_dir, str(Path(rel_base).with_suffix(".pdf")))
                    if ".pdf" in variants:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(variants[".pdf"], dst)
                        exported += 1
                    elif ".svg" in variants:
                        if not self._render_svg_to_pdf(variants[".svg"], dst):
                            raise RuntimeError("Unable to convert SVG to PDF")
                        exported += 1
                    elif ".png" in variants or ".jpg" in variants or ".jpeg" in variants:
                        raster_src = variants.get(".png") or variants.get(".jpg") or variants.get(".jpeg")
                        from PIL import Image
                        img = Image.open(raster_src)
                        if img.mode == "RGBA":
                            img = img.convert("RGB")
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        img.save(dst, "PDF")
                        exported += 1
                elif fmt == "svg":
                    dst = os.path.join(out_dir, str(Path(rel_base).with_suffix(".svg")))
                    if ".svg" in variants:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(variants[".svg"], dst)
                        exported += 1
                    elif ".png" in variants or ".jpg" in variants or ".jpeg" in variants:
                        raster_src = variants.get(".png") or variants.get(".jpg") or variants.get(".jpeg")
                        self._write_svg_wrapper(raster_src, dst)
                        exported += 1
            except Exception as exc:
                src_hint = ", ".join(sorted(variants.values()))
                failed.append(f"{src_hint}: {exc}")

        self.lbl_fig_status.setText(f"Exported {exported} {fmt.upper()} files: {out_dir}")
        if exported == 0:
            QMessageBox.information(self, "Notice", f"No {fmt.upper()} files were exported. Please check the project cache.")
        else:
            message = f"Exported {exported} {fmt.upper()} files:\n{out_dir}"
            if failed:
                message += f"\n\n{len(failed)} files failed to export. See the log for details."
            QMessageBox.information(self, "Export Finished", message)

    def _export_tables(self):
        if not self.require_project():
            return
        out_dir = self.txt_tbl_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Notice", "Please choose a table export directory.")
            return
        os.makedirs(out_dir, exist_ok=True)

        roots = self._project_export_roots()
        csv_files = list(self._iter_project_files(self.TABLE_EXTS))
        self.clear_log()
        self.append_log("=== Export All Tables ===")
        self.append_log("  Source roots: " + ("; ".join(roots) if roots else "cache"))
        self.append_log(f"Table files found: {len(csv_files)}")
        if not csv_files:
            self.lbl_tbl_status.setText("Table export completed.")
            self.lbl_tbl_status.setStyleSheet("color:#C62828; font-weight:bold;")
            QMessageBox.information(self, "Notice", "No tables were exported. Please confirm that the project cache folder contains table files.")
            return

        exported = 0
        for src in csv_files:
            rel = self._relative_project_path(src)
            dst = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            exported += 1

        self.lbl_tbl_status.setText(f"Exported {exported} table files: {out_dir}")
        self.lbl_tbl_status.setStyleSheet("color:#4CAF50; font-weight:bold;")
        QMessageBox.information(self, "Export Finished", f"Exported {exported} table files:\n{out_dir}")

    def run_step(self):
        QMessageBox.information(self, "Notice", "Please use the export buttons above to export the selected file type.")
