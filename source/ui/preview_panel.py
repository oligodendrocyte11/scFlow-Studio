from dataclasses import dataclass
from datetime import datetime
import csv
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QWidget,
    QApplication,
)

from widgets.image_viewer import ImageViewer


@dataclass
class PreviewItem:
    name: str
    item_type: str  # figure | table | summary
    path: str
    pdf_path: str = ""
    step: str = ""
    timestamp: str = ""
    in_export_list: bool = False


class PreviewPanel(QWidget):
    export_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("preview_panel")
        self.setMinimumWidth(380)

        self._items: list[PreviewItem] = []
        self._current_index = -1

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.lbl_title = QLabel("Preview")
        self.lbl_title.setObjectName("preview_title")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        top.addWidget(self.lbl_title, 1)

        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.btn_prev.setFixedSize(30, 28)
        self.btn_next.setFixedSize(30, 28)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)
        top.addWidget(self.btn_prev)
        top.addWidget(self.btn_next)
        layout.addLayout(top)

        self.tab_bar = QTabBar()
        self.tab_bar.addTab("Images")
        self.tab_bar.addTab("Tables")
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_bar)

        self.stack = QStackedWidget()
        self.image_viewer = ImageViewer()
        self.stack.addWidget(self.image_viewer)

        self.table_view = QTableWidget()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.stack.addWidget(self.table_view)
        layout.addWidget(self.stack, 1)

        btn_layout = QHBoxLayout()
        self.btn_save_png = QPushButton("Save PNG")
        self.btn_save_pdf = QPushButton("Save PDF")
        self.btn_copy = QPushButton("Copy Image")
        self.btn_export_csv = QPushButton("Export CSV")
        for btn in [self.btn_save_png, self.btn_save_pdf, self.btn_copy, self.btn_export_csv]:
            btn.setFixedHeight(28)
            btn_layout.addWidget(btn)
        self.btn_save_png.clicked.connect(self._save_png)
        self.btn_save_pdf.clicked.connect(self._save_pdf)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        self.btn_export_csv.clicked.connect(self._export_csv)
        layout.addLayout(btn_layout)

        self.lbl_list_title = QLabel("Result List")
        self.lbl_list_title.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(self.lbl_list_title)

        self.result_list = QListWidget()
        self.result_list.setMaximumHeight(200)
        self.result_list.currentRowChanged.connect(self._on_list_item_changed)
        layout.addWidget(self.result_list)

    def show_image(self, path: str, title: str = ""):
        if not os.path.isfile(path):
            return
        self.image_viewer.load_image(path, title)
        self.tab_bar.setCurrentIndex(0)
        self.stack.setCurrentIndex(0)
        if title:
            self.lbl_title.setText(title)

    def show_table(self, data: list[list], headers: list[str], title: str = ""):
        self.table_view.clear()
        if not data:
            return
        self.table_view.setColumnCount(len(headers))
        self.table_view.setHorizontalHeaderLabels(headers)
        self.table_view.setRowCount(len(data))
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.table_view.setItem(r, c, QTableWidgetItem(str(val)))
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tab_bar.setCurrentIndex(1)
        self.stack.setCurrentIndex(1)
        if title:
            self.lbl_title.setText(title)

    def show_table_from_csv(self, csv_path: str, title: str = ""):
        if not os.path.isfile(csv_path):
            return
        with open(csv_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if not rows:
            return
        self.show_table(rows[1:], rows[0], title)

    def add_item(self, name: str, path: str, item_type: str = "figure", step: str = "", pdf_path: str = ""):
        if item_type == "figure" and path and not pdf_path:
            stem, _ = os.path.splitext(path)
            guessed_pdf = stem + ".pdf"
            if os.path.isfile(guessed_pdf):
                pdf_path = guessed_pdf
        item = PreviewItem(
            name=name,
            item_type=item_type,
            path=path,
            pdf_path=pdf_path,
            step=step,
            timestamp=datetime.now().strftime("%H:%M:%S"),
        )
        self._items.append(item)
        icon = "🖼" if item_type == "figure" else "📊" if item_type == "table" else "📑"
        list_item = QListWidgetItem(f"{icon} {name}")
        list_item.setData(Qt.UserRole, len(self._items) - 1)
        self.result_list.addItem(list_item)
        self.result_list.setCurrentRow(self.result_list.count() - 1)

    def clear_items(self, step: str = ""):
        if step:
            self._items = [item for item in self._items if item.step != step]
        else:
            self._items.clear()
        self._rebuild_list()

    def _on_tab_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _on_list_item_changed(self, row: int):
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        self._current_index = row
        self.lbl_title.setText(f"{item.name}  [{item.step}]")

        if item.item_type == "figure" and os.path.isfile(item.path):
            figure_items = [(entry.name, entry.path) for entry in self._items if entry.item_type == "figure" and os.path.isfile(entry.path)]
            current_gallery_index = 0
            figure_row = 0
            for idx, entry in enumerate(self._items):
                if entry.item_type != "figure" or not os.path.isfile(entry.path):
                    continue
                if idx == row:
                    current_gallery_index = figure_row
                    break
                figure_row += 1
            self.image_viewer.set_gallery(figure_items, current_gallery_index)
            self.show_image(item.path, item.name)
        elif item.item_type == "table":
            self.show_table_from_csv(item.path, item.name)

        self._update_nav_buttons()
        self._update_action_buttons()

    def _go_prev(self):
        if self._current_index > 0:
            self.result_list.setCurrentRow(self._current_index - 1)

    def _go_next(self):
        if self._current_index < len(self._items) - 1:
            self.result_list.setCurrentRow(self._current_index + 1)

    def _update_nav_buttons(self):
        has_items = len(self._items) > 0
        self.btn_prev.setEnabled(has_items and self._current_index > 0)
        self.btn_next.setEnabled(has_items and 0 <= self._current_index < len(self._items) - 1)

    def _update_action_buttons(self):
        if self._current_index < 0 or self._current_index >= len(self._items):
            self.btn_save_png.setEnabled(False)
            self.btn_save_pdf.setEnabled(False)
            self.btn_copy.setEnabled(False)
            self.btn_export_csv.setEnabled(False)
            return
        item = self._items[self._current_index]
        is_figure = item.item_type == "figure" and os.path.isfile(item.path)
        is_table = item.item_type == "table" and os.path.isfile(item.path)
        self.btn_save_png.setEnabled(is_figure)
        self.btn_save_pdf.setEnabled(is_figure and bool(item.pdf_path and os.path.isfile(item.pdf_path)))
        self.btn_copy.setEnabled(is_figure)
        self.btn_export_csv.setEnabled(is_table)

    def _save_png(self):
        if self._current_index < 0 or self._current_index >= len(self._items):
            return
        item = self._items[self._current_index]
        if item.item_type != "figure" or not os.path.isfile(item.path):
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Save PNG", os.path.basename(item.path), "PNG (*.png)")
        if out_path:
            if not out_path.lower().endswith(".png"):
                out_path += ".png"
            import shutil
            shutil.copy2(item.path, out_path)

    def _save_pdf(self):
        if self._current_index < 0 or self._current_index >= len(self._items):
            return
        item = self._items[self._current_index]
        if not item.pdf_path or not os.path.isfile(item.pdf_path):
            QMessageBox.information(self, "Notice", "Images PDF file.")
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", os.path.basename(item.pdf_path), "PDF (*.pdf)")
        if out_path:
            if not out_path.lower().endswith(".pdf"):
                out_path += ".pdf"
            import shutil
            shutil.copy2(item.pdf_path, out_path)

    def _copy_to_clipboard(self):
        if self._current_index < 0 or self._current_index >= len(self._items):
            return
        item = self._items[self._current_index]
        if item.item_type != "figure" or not os.path.isfile(item.path):
            return
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(item.path)
        QApplication.clipboard().setPixmap(pixmap)

    def _export_csv(self):
        if self._current_index < 0 or self._current_index >= len(self._items):
            return
        item = self._items[self._current_index]
        if item.item_type != "table" or not os.path.isfile(item.path):
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Export CSV", os.path.basename(item.path), "CSV (*.csv)")
        if out_path:
            if not out_path.lower().endswith(".csv"):
                out_path += ".csv"
            import shutil
            shutil.copy2(item.path, out_path)

    def _rebuild_list(self):
        self.result_list.clear()
        for index, item in enumerate(self._items):
            icon = "🖼" if item.item_type == "figure" else "📊" if item.item_type == "table" else "📑"
            list_item = QListWidgetItem(f"{icon} {item.name}")
            list_item.setData(Qt.UserRole, index)
            self.result_list.addItem(list_item)
        if self._items:
            self.result_list.setCurrentRow(min(self._current_index if self._current_index >= 0 else 0, len(self._items) - 1))
        else:
            self._current_index = -1
            self.lbl_title.setText("Preview")
            self._update_nav_buttons()
            self._update_action_buttons()
