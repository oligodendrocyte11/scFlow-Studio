"""Step 1: create a project and add sample data paths."""
import os

from PySide6.QtCore import Qt, QSize, QObject, QThread, Signal, Slot, QEventLoop
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.matrix_importer import (
    detect_10x_barcode_suffix_groups,
    detect_matrix_samples,
    detect_rar_samples,
    detect_sparse_bundle_folder,
    detect_tar_samples,
    extract_rar_samples,
    extract_tar_samples,
    import_rds_samples,
    import_shared_matrix_samples,
    split_matrix_by_samples,
)
from core.project_manager import ProjectManager, SampleInfo
from ui.help_content import build_step_help
from ui.pages.base_page import BasePage


class AddSampleDialog(QDialog):
    """Add Sample"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Sample")
        self.setMinimumWidth(500)

        layout = QFormLayout(self)
        self.txt_name = QLineEdit()
        self.txt_group = QLineEdit()
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["10X Matrix Folder"])
        self.cmb_species = QComboBox()
        self.cmb_species.addItems(["Rat", "Mouse", "Human"])

        self.txt_path = QLineEdit()
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.txt_path, 1)
        path_layout.addWidget(self.btn_browse)

        layout.addRow("Sample Name:", self.txt_name)
        layout.addRow("Group:", self.txt_group)
        layout.addRow("Data Type:", self.cmb_type)
        layout.addRow("Species:", self.cmb_species)
        layout.addRow("Data Path:", path_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select 10X Data Folder")
        if path:
            self.txt_path.setText(path)
            folder_name = os.path.basename(os.path.normpath(path))
            if folder_name:
                if not self.txt_name.text().strip():
                    self.txt_name.setText(folder_name)
                if not self.txt_group.text().strip():
                    self.txt_group.setText(folder_name)

    def get_sample(self) -> SampleInfo:
        return SampleInfo(
            name=self.txt_name.text().strip(),
            group=self.txt_group.text().strip(),
            data_type=self.cmb_type.currentText(),
            species=self.cmb_species.currentText(),
            data_path=self.txt_path.text().strip(),
        )


class MatrixImportDialog(QDialog):
    """Import matrix samples and assign sample names/groups."""

    def __init__(self, file_path: str, detected: dict, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._detected = detected
        self.setWindowTitle("Import Expression Matrix")
        self.resize(840, 520)

        layout = QVBoxLayout(self)
        source_type = detected.get("source_type", "")
        sample_count = detected.get("sample_count", 0)
        cell_count = detected.get("cell_count")
        if cell_count is None:
            summary_text = f"Detected {sample_count} sample files."
        else:
            summary_text = f"Detected {sample_count} samples with {cell_count} cells in total."
        if source_type == "seurat_rds":
            desc_text = "Please confirm the sample name and group. This single-sample Seurat RDS will be added to the project for QC, doublet removal, and merging."
        else:
            desc_text = "Please confirm the sample names and groups. The file will be split into samples for QC, doublet removal, and merging."

        summary_label = QLabel(f"{summary_text}\n{desc_text}")
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        species_row = QHBoxLayout()
        species_row.addWidget(QLabel("Species:"))
        self.cmb_species = QComboBox()
        self.cmb_species.addItems(["Rat", "Mouse", "Human"])
        if "mouse" in os.path.basename(file_path).lower():
            self.cmb_species.setCurrentText("Mouse")
        species_row.addWidget(self.cmb_species)
        species_row.addStretch()
        layout.addLayout(species_row)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Sample Name", "Group", "cells"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setRowCount(len(detected.get("samples", [])))
        for row, sample in enumerate(detected.get("samples", [])):
            self.table.setItem(row, 0, QTableWidgetItem(sample["sample_name"]))
            self.table.setItem(row, 1, QTableWidgetItem(sample["group"]))
            count_item = QTableWidgetItem(str(sample.get("cell_count", 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, count_item)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_samples(self) -> tuple[str, list[dict]]:
        samples = []
        species = self.cmb_species.currentText()
        for row, raw in enumerate(self._detected.get("samples", [])):
            sample_name_item = self.table.item(row, 0)
            group_item = self.table.item(row, 1)
            sample_name = sample_name_item.text().strip() if sample_name_item else raw["sample_name"]
            group = group_item.text().strip() if group_item else raw["group"]
            if not sample_name:
                raise ValueError(f"Sample name in row {row + 1} cannot be empty.")
            samples.append({
                "sample_name": sample_name,
                "group": group or sample_name,
                "cell_count": raw.get("cell_count", 0),
                "gene_count": raw.get("gene_count", 0),
                "column_indexes": raw.get("column_indexes", []),
                "cell_ids": raw.get("cell_ids", []),
                "archive_member": raw.get("archive_member", ""),
                "archive_bundle_members": raw.get("archive_bundle_members", {}),
                "archive_members": raw.get("archive_members", {}),
                "archive_target_names": raw.get("archive_target_names", {}),
                "nested_archive_member": raw.get("nested_archive_member", ""),
                "rar_inner_archive": raw.get("rar_inner_archive", ""),
                "library_identity": raw.get("library_identity", ""),
                "split_suffix": raw.get("split_suffix", ""),
                "data_type": raw.get("data_type", ""),
            })
        return species, samples


class BusyWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    @Slot()
    def run(self):
        try:
            self.finished.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:
            self.error.emit(str(exc))


class ProjectPage(BasePage):
    STEP_ID = "project"
    STEP_NAME = "① Project and Data"
    PLOT_THEME_PREVIEWS = {
        "publication_classic": ("Nature", ["#3B6FB6", "#D95F02", "#1B9E77", "#7570B3", "#E7298A"]),
        "soft_academic": ("Cell", ["#C44E52", "#4C72B0", "#55A868", "#8172B3", "#CCB974"]),
        "professional_contrast": ("Science", ["#0077BB", "#33BBEE", "#009988", "#EE7733", "#CC3311"]),
        "warm_story": ("Warm Story", ["#B56576", "#E56B6F", "#EAAC8B", "#6D597A", "#355070"]),
        "fresh_nature": ("Fresh Nature", ["#2A9D8F", "#52B788", "#84CC16", "#F4A261", "#457B9D"]),
        "pastel_muted": ("Pastel Muted", ["#A8DADC", "#B8E0D2", "#E9C46A", "#D4A373", "#CDB4DB"]),
        "nordic_mist": ("Ocean Mist", ["#2B6CB0", "#38A3A5", "#7BC8A4", "#F4A261", "#6C5CE7"]),
        "sunset_pop": ("Cancer Discovery", ["#8E6C8A", "#E64B35", "#4DBBD5", "#00A087", "#3C5488"]),
        "urban_ink": ("Immunity", ["#5B8E7D", "#C06C84", "#355C7D", "#F67280", "#F8B195"]),
        "earth_clay": ("Amber Bloom", ["#D1495B", "#EDAe49", "#66A182", "#2E4057", "#8D6A9F"]),
    }

    def __init__(self, **kwargs):
        self._project_manager = ProjectManager()
        self._updating_sample_table = False
        super().__init__(**kwargs)
    def _run_busy_task(self, title: str, label: str, fn, *args, **kwargs):
        progress = QProgressDialog(label, None, 0, 0, self)
        progress.setWindowTitle(title)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        thread = QThread(self)
        worker = BusyWorker(fn, *args, **kwargs)
        worker.moveToThread(thread)

        result_box = {"value": None, "error": None}
        loop = QEventLoop()

        def _on_finished(result):
            result_box["value"] = result
            loop.quit()

        def _on_error(message):
            result_box["error"] = message
            loop.quit()

        worker.finished.connect(_on_finished)
        worker.error.connect(_on_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.start()
        loop.exec()
        progress.close()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()

        if result_box["error"]:
            raise RuntimeError(result_box["error"])
        return result_box["value"]

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)

        grp_project = QGroupBox("Project")
        form = QFormLayout(grp_project)
        self.txt_project_name = QLineEdit()
        self.txt_project_dir = QLineEdit()
        self.btn_browse_dir = QPushButton("Browse...")
        self.btn_browse_dir.clicked.connect(self._browse_project_dir)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.txt_project_dir, 1)
        dir_layout.addWidget(self.btn_browse_dir)

        self.cmb_ref_mode = QComboBox()
        self.cmb_ref_mode.addItems(["Reference original data paths (recommended)", "Copy data into project folder"])
        form.addRow("Project name:", self.txt_project_name)
        form.addRow("Project Directory:", dir_layout)
        form.addRow("Data storage mode:", self.cmb_ref_mode)

        self.cmb_plot_theme = QComboBox()
        for theme_key, (theme_name, _colors) in self.PLOT_THEME_PREVIEWS.items():
            self.cmb_plot_theme.addItem(theme_name, theme_key)
        self.cmb_plot_theme.currentIndexChanged.connect(self._on_plot_theme_changed)

        theme_row = QVBoxLayout()
        theme_row.setSpacing(6)
        theme_row.addWidget(self.cmb_plot_theme)
        self.lbl_plot_theme_preview = QLabel()
        self.lbl_plot_theme_preview.setWordWrap(True)
        self.lbl_plot_theme_preview.setStyleSheet("border: 1px solid #D8D8D8; border-radius: 6px; padding: 6px;")
        self.lbl_plot_theme_preview.setTextFormat(Qt.PlainText)
        self.lbl_plot_theme_swatches = QLabel()
        self.lbl_plot_theme_swatches.setFixedHeight(26)
        self.lbl_plot_theme_swatches.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        theme_row.addWidget(self.lbl_plot_theme_preview)
        theme_row.addWidget(self.lbl_plot_theme_swatches)
        form.addRow("Plot theme:", theme_row)
        self._update_plot_theme_preview()

        self.btn_create = QPushButton("Create Project")
        self.btn_create.setProperty("role", "accent")
        self.btn_create.clicked.connect(self._create_project)
        form.addRow("", self.btn_create)
        layout.addWidget(grp_project)

        grp_samples = QGroupBox("Sample List")
        s_layout = QVBoxLayout(grp_samples)
        btn_row = QHBoxLayout()
        self.btn_add_sample = QPushButton("Add Sample")
        self.btn_import_matrix = QPushButton("Import Matrix File")
        self.btn_remove_sample = QPushButton("Delete Selected")
        self.btn_check_all = QPushButton("Check All Data")
        self.btn_add_sample.clicked.connect(self._add_sample)
        self.btn_import_matrix.clicked.connect(self._import_matrix_file)
        self.btn_remove_sample.clicked.connect(self._remove_sample)
        self.btn_check_all.clicked.connect(self._check_all_data)
        btn_row.addWidget(self.btn_add_sample)
        btn_row.addWidget(self.btn_import_matrix)
        btn_row.addWidget(self.btn_remove_sample)
        btn_row.addWidget(self.btn_check_all)
        btn_row.addStretch()
        s_layout.addLayout(btn_row)

        self.sample_table = QTableWidget()
        self.sample_table.setColumnCount(6)
        self.sample_table.setHorizontalHeaderLabels(["Sample Name", "Group", "Data Type", "Species", "Path", "Status"])
        self.sample_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.sample_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sample_table.itemChanged.connect(self._on_sample_item_changed)
        s_layout.addWidget(self.sample_table)
        layout.addWidget(grp_samples)

        self.bind_help_refresh(self.txt_project_name, self.txt_project_dir, self.cmb_ref_mode, self.cmb_plot_theme)
        return container

    def reset_params(self):
        self.txt_project_name.clear()
        self.txt_project_dir.clear()
        self.cmb_ref_mode.setCurrentIndex(0)
        self.cmb_plot_theme.setCurrentIndex(0)
        self._update_plot_theme_preview()
        self.sample_table.setRowCount(0)

    def _update_plot_theme_preview(self):
        theme_key = self.cmb_plot_theme.currentData()
        theme_name, colors = self.PLOT_THEME_PREVIEWS.get(theme_key, self.PLOT_THEME_PREVIEWS["publication_classic"])
        self.lbl_plot_theme_preview.setText(f"{theme_name}\nColor preview:")
        self.lbl_plot_theme_swatches.setPixmap(self._build_theme_swatch_pixmap(colors))

    def _build_theme_swatch_pixmap(self, colors: list[str]) -> QPixmap:
        dot_size = 18
        gap = 8
        margin = 2
        width = margin * 2 + len(colors) * dot_size + max(len(colors) - 1, 0) * gap
        height = dot_size + margin * 2
        pixmap = QPixmap(QSize(width, height))
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor("#888888"))
        pen.setWidth(1)
        painter.setPen(pen)
        x = margin
        for color in colors:
            painter.setBrush(QColor(color))
            painter.drawEllipse(x, margin, dot_size, dot_size)
            x += dot_size + gap
        painter.end()
        return pixmap

    def _on_plot_theme_changed(self, *_args):
        self._update_plot_theme_preview()
        self.refresh_help()
        if self.project:
            self.project.plot_theme = self.cmb_plot_theme.currentData()
            self._save_samples()
            self._project_manager.save_project(self.project)
            self.main_window.apply_project_plot_theme(self.project.plot_theme)
            self.append_log(f"Project plot theme: {self.cmb_plot_theme.currentText()}")

    def get_help_html(self) -> str:
        sample_count = len(self.project.samples) if self.project else self.sample_table.rowCount()
        return build_step_help("project", {"ref_mode": self.cmb_ref_mode.currentText(), "plot_theme": self.cmb_plot_theme.currentText(), "sample_count": sample_count})

    def start_new_project(self):
        self.txt_project_name.setFocus()

    def _browse_project_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Project Directory")
        if path:
            self.txt_project_dir.setText(path)

    def _create_project(self):
        name = self.txt_project_name.text().strip()
        directory = self.txt_project_dir.text().strip()
        if not name:
            QMessageBox.warning(self, "Notice", "Please enter a project name.")
            return
        if not directory or not os.path.isdir(directory):
            QMessageBox.warning(self, "Notice", "Please select a valid project directory.")
            return

        ref_mode = "reference" if self.cmb_ref_mode.currentIndex() == 0 else "copy"
        plot_theme = self.cmb_plot_theme.currentData()
        try:
            project = self._project_manager.create_project(name, directory, ref_mode)
            project.plot_theme = plot_theme
            self.project = project
            self.main_window.set_project(project)
            self.main_window.apply_project_plot_theme(project.plot_theme)
            self.append_log(f"Project created: {project.directory}")
            QMessageBox.information(self, "Success", f"Project created: {name}.")
        except Exception as e:
            QMessageBox.critical(self, "Failed", str(e))
    def _add_sample(self):
        dialog = AddSampleDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        sample = dialog.get_sample()
        if not sample.name:
            QMessageBox.warning(self, "Notice", "Sample name cannot be empty.")
            return
        if not self.project:
            QMessageBox.warning(self, "Notice", "Please create or open a project first.")
            return

        split_groups = []
        if sample.data_type == "10X Matrix Folder":
            try:
                split_groups = detect_10x_barcode_suffix_groups(sample.data_path)
            except Exception:
                split_groups = []

        if split_groups:
            existing_names = {s.name for s in self.project.samples}
            added_names = []
            for item in split_groups:
                base_name = f"{sample.name}_{item['suffix']}"
                unique_name = base_name
                suffix = 2
                while unique_name in existing_names:
                    unique_name = f"{base_name}_{suffix}"
                    suffix += 1
                existing_names.add(unique_name)
                self.project.samples.append(
                    SampleInfo(
                        name=unique_name,
                        group=sample.group or sample.name,
                        data_type=sample.data_type,
                        species=sample.species,
                        data_path=sample.data_path,
                        split_suffix=str(item["suffix"]),
                        cell_count=int(item.get("cell_count", 0)),
                    )
                )
                added_names.append(unique_name)
            self._refresh_sample_table()
            self._save_samples()
            self.append_log(f"Detected {len(split_groups)} barcode suffix groups in the 10X folder. Added samples: " + ", ".join(added_names))
            QMessageBox.information(
                self,
                "Sample",
                f"Detected {len(split_groups)} barcode suffix groups in this 10X folder.\n\n"
                f"Added {len(split_groups)} samples:\n"
                + "\n".join(added_names)
                + "\n\nDuring QC, cells will be loaded according to their barcode suffixes.",
            )
            return

        if sample.data_type == "10X Matrix Folder":
            try:
                detected_bundle = detect_sparse_bundle_folder(sample.data_path)
            except Exception:
                detected_bundle = None

            if detected_bundle and detected_bundle.get("sample_count", 0) > 1:
                bundle_dialog = MatrixImportDialog(sample.data_path, detected_bundle, self)
                bundle_dialog.cmb_species.setCurrentText(sample.species)
                if bundle_dialog.exec() != QDialog.Accepted:
                    return
                try:
                    species, sample_defs = bundle_dialog.get_samples()
                except Exception as e:
                    QMessageBox.warning(self, "Notice", str(e))
                    return

                existing_names = {s.name for s in self.project.samples}
                added = 0
                for item in sample_defs:
                    sample_name = item["sample_name"]
                    unique_name = sample_name
                    suffix = 2
                    while unique_name in existing_names:
                        unique_name = f"{sample_name}_{suffix}"
                        suffix += 1
                    existing_names.add(unique_name)
                    self.project.samples.append(
                        SampleInfo(
                            name=unique_name,
                            group=item["group"],
                            data_type="Sparse Bundle Folder",
                            species=species,
                            data_path=sample.data_path,
                            library_identity=item.get("library_identity", item["sample_name"]),
                            cell_count=item.get("cell_count", 0),
                            gene_count=item.get("gene_count", 0),
                        )
                    )
                    added += 1

                self._refresh_sample_table()
                self._save_samples()
                self.append_log(f"Detected sparse matrix bundle. Registered {added} samples from {os.path.basename(sample.data_path)}")
                QMessageBox.information(
                    self,
                    "Import Completed",
                    f"Detected {added} samples from the metadata Library_Identity field.\n\n"
                    "The samples have been added and are ready for QC.",
                )
                return

        self.project.samples.append(sample)
        self._refresh_sample_table()
        self._save_samples()
        self.append_log(f"Added sample: {sample.name}")

    def _import_matrix_file(self):
        if not self.project:
            QMessageBox.warning(self, "Notice", "Please create or open a project first.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Matrix File",
            "",
            "file (*.txt *.tsv *.csv *.txt.gz *.tsv.gz *.csv.gz *.tar *.tar.gz *.tgz *.rar *.rds)",
        )
        if not path:
            return

        try:
            if path.lower().endswith((".tar", ".tar.gz", ".tgz")):
                detected = detect_tar_samples(path)
            elif path.lower().endswith(".rar"):
                detected = detect_rar_samples(path)
            elif path.lower().endswith(".rds"):
                detected = self._detect_seurat_rds(path)
            else:
                detected = detect_matrix_samples(path)
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Unable to import matrix file:\n{e}")
            return

        dialog = MatrixImportDialog(path, detected, self)
        if dialog.exec() != QDialog.Accepted:
            return

        try:
            species, sample_defs = dialog.get_samples()
        except Exception as e:
            QMessageBox.warning(self, "Notice", str(e))
            return

        base_name = os.path.basename(path)
        base_root = os.path.splitext(os.path.splitext(base_name)[0])[0]
        output_root = os.path.join(self.project.cache_subdir("raw_index"), "matrix_imports", base_root)
        progress = QProgressDialog("Importing matrix file...", None, 0, max(len(sample_defs), 1), self)
        progress.setWindowTitle("Import Matrix")
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        self.append_log(f"Import matrix file: {os.path.basename(path)}")
        self.append_log(f"Imported {len(sample_defs)} samples into the project.")

        def _update_progress(processed_rows: int):
            progress.setRange(0, 0)
            progress.setLabelText(f"Reading matrix file...\nProcessed {processed_rows} genes.")
            QApplication.processEvents()

        last_logged = {"index": 0}

        def _update_tar_progress(index: int, total: int, sample_name: str):
            total = max(int(total), 1)
            progress.setRange(0, total)
            progress.setValue(min(int(index), total))
            percent = int(min(int(index), total) * 100 / total)
            progress.setLabelText(f"Extracting matrix samples...\nCompleted {index}/{total} ({percent}%): {sample_name}")
            if index != last_logged["index"]:
                last_logged["index"] = index
                self.append_log(f"  Completed {index}/{total}: {sample_name}")
            QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if path.lower().endswith((".tar", ".tar.gz", ".tgz")):
                outputs = extract_tar_samples(path, sample_defs, output_root, progress_callback=_update_tar_progress)
            elif path.lower().endswith(".rar"):
                outputs = extract_rar_samples(path, sample_defs, output_root, progress_callback=_update_tar_progress)
            elif path.lower().endswith(".rds"):
                progress.setRange(0, 0)
                progress.setLabelText("Importing Seurat RDS sample...")
                QApplication.processEvents()
                outputs = import_rds_samples(path, sample_defs, output_root)
            elif detected.get("source_type") == "shared_matrix_suffix_groups":
                progress.setRange(0, 0)
                progress.setLabelText("Splitting matrix by sample...")
                QApplication.processEvents()
                outputs = import_shared_matrix_samples(path, sample_defs, output_root)
            else:
                outputs = split_matrix_by_samples(path, sample_defs, output_root, progress_callback=_update_progress)
        except Exception as e:
            self.append_log(f"Failed: {e}")
            QMessageBox.critical(self, "Failed", f"Matrix import failed:\n{e}")
            return
        finally:
            progress.close()
            QApplication.restoreOverrideCursor()

        existing_names = {s.name for s in self.project.samples}
        added = 0
        for item in outputs:
            sample_name = item["sample_name"]
            unique_name = sample_name
            suffix = 2
            while unique_name in existing_names:
                unique_name = f"{sample_name}_{suffix}"
                suffix += 1
            existing_names.add(unique_name)
            self.project.samples.append(
                SampleInfo(
                    name=unique_name,
                    group=item["group"],
                    data_type=item["data_type"],
                    species=species,
                    data_path=item["data_path"],
                    split_suffix=item.get("split_suffix", ""),
                    cell_count=item.get("cell_count", 0),
                    gene_count=item.get("gene_count", 0),
                )
            )
            added += 1

        self._refresh_sample_table()
        self._save_samples()
        self.append_log(f"Imported {added} samples from matrix file: {os.path.basename(path)}")
        QMessageBox.information(
            self,
            "Finished",
            f"Imported {added} samples.\n\nPlease confirm sample names/groups, then continue to QC and doublet removal.",
        )

    def _remove_sample(self):
        rows = set(idx.row() for idx in self.sample_table.selectedIndexes())
        if not rows:
            return
        for row in sorted(rows, reverse=True):
            if row < len(self.project.samples):
                removed = self.project.samples.pop(row)
                self.append_log(f"Sample:{removed.name}")
        self._refresh_sample_table()
        self._save_samples()

    def _on_sample_item_changed(self, item):
        if self._updating_sample_table or not self.project:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.project.samples) or col not in (0, 1):
            return

        sample = self.project.samples[row]
        new_value = (item.text() or "").strip()
        old_value = sample.name if col == 0 else sample.group
        if not new_value:
            QMessageBox.warning(self, "Notice", "Sample name and group cannot be empty.")
            self._updating_sample_table = True
            item.setText(old_value)
            self._updating_sample_table = False
            return

        if col == 0:
            duplicate = any(i != row and s.name == new_value for i, s in enumerate(self.project.samples))
            if duplicate:
                QMessageBox.warning(self, "Notice", f"Sample name '{new_value}' already exists.")
                self._updating_sample_table = True
                item.setText(old_value)
                self._updating_sample_table = False
                return
            sample.name = new_value
            self.append_log(f"Updated sample name: {old_value} -> {new_value}")
        else:
            sample.group = new_value
            self.append_log(f"Updated group: {sample.name} -> {new_value}")

        self._save_samples()
        self.refresh_help()

    def _refresh_sample_table(self):
        if not self.project:
            return
        samples = self.project.samples
        self._updating_sample_table = True
        self.sample_table.setRowCount(len(samples))
        for r, s in enumerate(samples):
            name_item = QTableWidgetItem(s.name)
            group_item = QTableWidgetItem(s.group)
            data_type_item = QTableWidgetItem(s.data_type)
            species_item = QTableWidgetItem(s.species)
            path_item = QTableWidgetItem(s.data_path)

            for locked_item in (data_type_item, species_item, path_item):
                locked_item.setFlags(locked_item.flags() & ~Qt.ItemIsEditable)

            self.sample_table.setItem(r, 0, name_item)
            self.sample_table.setItem(r, 1, group_item)
            self.sample_table.setItem(r, 2, data_type_item)
            self.sample_table.setItem(r, 3, species_item)
            self.sample_table.setItem(r, 4, path_item)
            status_item = QTableWidgetItem(s.status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if s.status == "valid":
                status_item.setForeground(QColor("#4CAF50"))
            elif s.status in ("missing", "error"):
                status_item.setForeground(QColor("#F44336"))
            else:
                status_item.setForeground(QColor("#888888"))
            self.sample_table.setItem(r, 5, status_item)

        self._updating_sample_table = False
        self.main_window.statusbar_mgr.lbl_samples.setText(f"Sample: {len(samples)}")
        self.refresh_help()

    def _save_samples(self):
        if self.project:
            self._project_manager.save_project(self.project)
    def _check_all_data(self):
        if not self.project or not self.project.samples:
            QMessageBox.warning(self, "Notice", "No sample is currently selected.")
            return

        self.append_log("=== Checking sample data ===")
        all_ok = True
        for sample in self.project.samples:
            if sample.data_type == "Seurat RDS":
                ok, msg = self._validate_seurat_rds_file(sample.data_path)
            elif sample.data_type == "Sparse Bundle Folder":
                ok, msg = self._validate_sparse_bundle_folder(sample.data_path)
            elif sample.data_type.startswith("Expression Matrix"):
                ok, msg = self._validate_expression_matrix_file(sample.data_path)
            else:
                ok, msg = self._validate_10x_folder(sample.data_path)

            if ok:
                sample.status = "valid"
                self.append_log(f"  OK: {sample.name}")
            else:
                sample.status = "missing"
                all_ok = False
                self.append_log(f"  Failed: {sample.name}: {msg}")

        self._refresh_sample_table()
        self._save_samples()
        if all_ok:
            self.append_log("=== All sample data checks passed ===")
            headers = ["Sample Name", "Group", "Species", "Status"]
            data = [[s.name, s.group, s.species, s.status] for s in self.project.samples]
            self.main_window.show_preview_table(data, headers, "Sample")
        else:
            self.append_log("=== Sample data check failed. Please verify the paths and file formats. ===")

    @staticmethod
    def _validate_10x_folder(path: str) -> tuple[bool, str]:
        """ 10X """
        if not path or not os.path.isdir(path):
            return False, f"Path does not exist: {path}"
        entries = [name for name in os.listdir(path) if os.path.isfile(os.path.join(path, name))]
        lower_entries = [name.lower() for name in entries]
        required_suffixes = {
            "matrix": ("matrix.mtx", "matrix.mtx.gz"),
            "features": ("features.tsv", "features.tsv.gz", "genes.tsv", "genes.tsv.gz"),
            "barcodes": ("barcodes.tsv", "barcodes.tsv.gz"),
        }
        for file_type, suffixes in required_suffixes.items():
            found = any(entry.endswith(suffixes) for entry in lower_entries)
            if not found:
                return False, f"Missing {file_type} file"
        return True, "OK"

    @staticmethod
    def _validate_sparse_bundle_folder(path: str) -> tuple[bool, str]:
        try:
            detect_sparse_bundle_folder(path)
            return True, "OK"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _validate_expression_matrix_file(path: str) -> tuple[bool, str]:
        if not path or not os.path.isfile(path):
            return False, f"File does not exist: {path}"
        if os.path.getsize(path) <= 0:
            return False, "file is empty"
        return True, "OK"

    @staticmethod
    def _validate_seurat_rds_file(path: str) -> tuple[bool, str]:
        if not path or not os.path.isfile(path):
            return False, f"File does not exist: {path}"
        if not path.lower().endswith(".rds"):
            return False, ".rds file"
        if os.path.getsize(path) <= 0:
            return False, "file is empty"
        return True, "OK"

    def _detect_seurat_rds(self, path: str) -> dict:
        detect_dir = os.path.join(self.project.cache_subdir("raw_index"), "rds_detect", os.path.splitext(os.path.basename(path))[0])
        os.makedirs(detect_dir, exist_ok=True)

        def _call():
            return self.r_bridge.call_script(
                script_name="01_detect_seurat_rds.R",
                params={"input_rds": path.replace("\\", "/")},
                output_dir=detect_dir,
            )

        result = self._run_busy_task("Detect Seurat RDS", "Inspecting .rds file for Seurat sample information...", _call)
        if not result.success:
            raise RuntimeError(result.error_message or " Seurat RDS Failed.")
        return result.summary

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self.txt_project_name.setText(project.name)
        self.txt_project_dir.setText(os.path.dirname(project.directory))
        idx = self.cmb_plot_theme.findData(getattr(project, "plot_theme", "publication_classic"))
        if idx >= 0:
            self.cmb_plot_theme.setCurrentIndex(idx)
        self._refresh_sample_table()
        self.refresh_help()

    def run_step(self):
        """"""""
        self._check_all_data()

    def go_next(self):
        if not self.project:
            QMessageBox.warning(self, "Notice", "Please create or open a project first.")
            return
        if not self.project.samples:
            QMessageBox.warning(self, "Notice", "Sample.")
            return
        invalid = [s for s in self.project.samples if s.status != "valid"]
        if invalid:
            reply = QMessageBox.question(self, "Notice", f"{len(invalid)} samples are invalid. Continue?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        super().go_next()
