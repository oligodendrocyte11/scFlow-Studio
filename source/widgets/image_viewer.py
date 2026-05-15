"""
Image viewer - supports zooming and popup browsing with gallery navigation.
"""
from PySide6.QtWidgets import (
    QLabel, QScrollArea, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QDialog, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QWheelEvent, QMouseEvent, QImageReader, QImage
from PIL import Image


class ImageViewer(QScrollArea):
    """Zoomable image viewer with optional popup gallery navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._scale = 1.0
        self._image_path = ""
        self._image_title = ""
        self._auto_fit = True
        self._allow_wheel_zoom = False
        self._gallery: list[tuple[str, str]] = []
        self._gallery_index = -1
        self._loaded_scaled_only = False

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setWidget(self._label)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)

    def set_wheel_zoom_enabled(self, enabled: bool):
        self._allow_wheel_zoom = bool(enabled)

    def _should_force_preview_load(self, path: str) -> bool:
        reader = QImageReader(path)
        size = reader.size()
        if not size.isValid() or size.width() <= 0 or size.height() <= 0:
            return False

        vw, vh = self._preview_target_size()
        pixel_count = size.width() * size.height()
        viewport_pixels = max(vw * vh, 1)

        # Very large figures are safer to preview through a scaled decode on macOS.
        if pixel_count >= 40_000_000:
            return True
        if size.width() >= vw * 3 or size.height() >= vh * 3:
            return True
        if pixel_count >= viewport_pixels * 6:
            return True
        return False

    def load_image(self, path: str, title: str = ""):
        self._image_path = path
        self._image_title = title
        self._loaded_scaled_only = False
        self._auto_fit = True

        pixmap = QPixmap()
        if self._auto_fit and self._should_force_preview_load(path):
            pixmap = self._load_preview_pixmap(path)
        else:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                pixmap = self._load_preview_pixmap(path)

        self._pixmap = pixmap
        if self._pixmap.isNull():
            self._label.setPixmap(QPixmap())
            self._label.setText("Unable to load image")
            return

        self._label.setText("")
        self._scale = 1.0
        if self._auto_fit:
            self._fit_to_view()
        else:
            self._update_display()

    def _preview_target_size(self):
        vw = max(self.viewport().width() - 4, 320)
        vh = max(self.viewport().height() - 4, 240)
        return vw, vh

    def _load_preview_pixmap(self, path: str) -> QPixmap:
        reader = QImageReader(path)
        if not reader.canRead():
            return self._load_preview_pixmap_pil(path)

        vw, vh = self._preview_target_size()
        raw_size = reader.size()
        if raw_size.isValid() and raw_size.width() > 0 and raw_size.height() > 0:
            target = raw_size.scaled(vw, vh, Qt.KeepAspectRatio)
            if target.width() > 0 and target.height() > 0:
                reader.setScaledSize(target)

        image = reader.read()
        if image.isNull():
            return self._load_preview_pixmap_pil(path)

        self._loaded_scaled_only = True
        return QPixmap.fromImage(image)

    def _load_preview_pixmap_pil(self, path: str) -> QPixmap:
        try:
            with Image.open(path) as img:
                vw, vh = self._preview_target_size()
                img.thumbnail((max(vw, 1), max(vh, 1)), Image.Resampling.LANCZOS)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                data = img.tobytes("raw", "RGBA")
                qimage = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888).copy()
                if qimage.isNull():
                    return QPixmap()
                self._loaded_scaled_only = True
                return QPixmap.fromImage(qimage)
        except Exception:
            return QPixmap()

    def set_gallery(self, gallery: list[tuple[str, str]], current_index: int = 0):
        self._gallery = gallery or []
        self._gallery_index = current_index if self._gallery else -1

    def _fit_to_view(self):
        if not self._pixmap:
            return
        vw = self.viewport().width() - 4
        vh = self.viewport().height() - 4
        pw = self._pixmap.width()
        ph = self._pixmap.height()
        if pw == 0 or ph == 0:
            return
        sx = vw / pw
        sy = vh / ph
        self._scale = min(sx, sy, 1.0)
        self._update_display()

    def _update_display(self):
        if not self._pixmap:
            return
        w = int(self._pixmap.width() * self._scale)
        h = int(self._pixmap.height() * self._scale)
        scaled = self._pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())

    def fit_to_window(self):
        self._auto_fit = True
        self._fit_to_view()

    def original_size(self):
        if self._loaded_scaled_only and self._image_path:
            pixmap = QPixmap(self._image_path)
            if not pixmap.isNull():
                self._pixmap = pixmap
                self._loaded_scaled_only = False
        self._auto_fit = False
        self._scale = 1.0
        self._update_display()

    def zoom_in(self):
        self._scale = min(self._scale * 1.25, 5.0)
        self._update_display()

    def zoom_out(self):
        self._scale = max(self._scale / 1.25, 0.1)
        self._update_display()

    def wheelEvent(self, event: QWheelEvent):
        if not self._allow_wheel_zoom:
            event.ignore()
            return
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self._pixmap and not self._pixmap.isNull():
            self._show_popup()
        event.accept()

    def _show_popup(self):
        dialog = QDialog(self.window())
        dialog.setMinimumSize(800, 600)
        dialog.resize(1200, 800)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        viewer = ImageViewer()
        viewer.set_wheel_zoom_enabled(True)
        viewer.set_gallery(self._gallery, self._gallery_index)
        layout.addWidget(viewer)

        toolbar = QHBoxLayout()
        btn_prev = QPushButton("Previous")
        btn_next = QPushButton("Next")
        btn_fit = QPushButton("Fit to Window")
        btn_orig = QPushButton("Original Size")
        btn_zin = QPushButton("Zoom In (+)")
        btn_zout = QPushButton("Zoom Out (-)")
        btn_close = QPushButton("Close")

        toolbar.addWidget(btn_prev)
        toolbar.addWidget(btn_next)
        toolbar.addStretch()
        toolbar.addWidget(btn_fit)
        toolbar.addWidget(btn_orig)
        toolbar.addWidget(btn_zin)
        toolbar.addWidget(btn_zout)
        toolbar.addWidget(btn_close)
        layout.addLayout(toolbar)

        def load_gallery_index(index: int):
            if viewer._gallery:
                index = max(0, min(index, len(viewer._gallery) - 1))
                viewer._gallery_index = index
                title, path = viewer._gallery[index]
                viewer.load_image(path, title)
                dialog.setWindowTitle(f"Image Viewer - {title}")
                btn_prev.setEnabled(index > 0)
                btn_next.setEnabled(index < len(viewer._gallery) - 1)
            else:
                viewer.load_image(self._image_path, self._image_title)
                dialog.setWindowTitle("Image Viewer")
                btn_prev.setEnabled(False)
                btn_next.setEnabled(False)

        btn_prev.clicked.connect(lambda: load_gallery_index(viewer._gallery_index - 1))
        btn_next.clicked.connect(lambda: load_gallery_index(viewer._gallery_index + 1))
        btn_fit.clicked.connect(viewer.fit_to_window)
        btn_orig.clicked.connect(viewer.original_size)
        btn_zin.clicked.connect(viewer.zoom_in)
        btn_zout.clicked.connect(viewer.zoom_out)
        btn_close.clicked.connect(dialog.close)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: load_gallery_index(self._gallery_index if self._gallery_index >= 0 else 0))

        dialog.exec()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            if self._loaded_scaled_only and self._auto_fit:
                new_pixmap = self._load_preview_pixmap(self._image_path)
                if not new_pixmap.isNull():
                    self._pixmap = new_pixmap
            if self._auto_fit:
                self._fit_to_view()
            else:
                self._update_display()
