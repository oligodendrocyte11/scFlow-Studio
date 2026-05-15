from PySide6.QtWidgets import QStatusBar, QLabel, QProgressBar, QWidget
from PySide6.QtCore import QTimer
import psutil
import os


class StatusBarManager:
    """Status bar."""

    def __init__(self, parent: QWidget):
        self.statusbar = QStatusBar(parent)

        self.lbl_status = QLabel("")
        self.statusbar.addWidget(self.lbl_status, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.statusbar.addPermanentWidget(self.progress_bar)

        self.lbl_project = QLabel("Project: ")
        self.lbl_samples = QLabel("Sample: 0")
        self.lbl_memory = QLabel("Memory: - MB")
        self.lbl_cache = QLabel("Cache: - MB")

        for lbl in [self.lbl_project, self.lbl_samples, self.lbl_memory, self.lbl_cache]:
            lbl.setStyleSheet("padding: 0 8px;")
            self.statusbar.addPermanentWidget(lbl)

        self._timer = QTimer()
        self._timer.timeout.connect(self._update_memory)
        self._timer.start(5000)

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def set_project(self, project):
        self.lbl_project.setText(f"Project: {project.name}")
        self.lbl_samples.setText(f"Sample: {len(project.samples)}")
        self._update_cache(project)

    def set_progress(self, percent: int, message: str = ""):
        if percent < 0:
            self.progress_bar.setVisible(False)
        else:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(percent)
        if message:
            self.lbl_status.setText(message)

    def _update_memory(self):
        try:
            proc = psutil.Process(os.getpid())
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            self.lbl_memory.setText(f"Memory: {mem_mb:.0f} MB")
        except Exception:
            pass

    def _update_cache(self, project):
        try:
            total = 0
            cache_dir = project.cache_dir
            if os.path.isdir(cache_dir):
                for root, dirs, files in os.walk(cache_dir):
                    for f in files:
                        total += os.path.getsize(os.path.join(root, f))
            mb = total / (1024 * 1024)
            self.lbl_cache.setText(f"Cache: {mb:.1f} MB")
        except Exception:
            pass
