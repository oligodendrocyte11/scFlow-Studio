"""
Top toolbar
"""
from PySide6.QtWidgets import QToolBar, QWidget, QLabel, QComboBox
from PySide6.QtCore import QSize
from PySide6.QtGui import QAction


class ToolBarManager:
    """Toolbar manager"""

    def __init__(self, parent: QWidget):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))

        # ── Project actions ──
        self.act_new = QAction("📁 New Project", parent)
        self.act_open = QAction("📂 Open Project", parent)
        self.act_save = QAction("💾 Save Project", parent)
        self.toolbar.addAction(self.act_new)
        self.toolbar.addAction(self.act_open)
        self.toolbar.addAction(self.act_save)

        self.toolbar.addSeparator()

        # ── Run controls ──
        self.act_run = QAction("▶ Run Current Step", parent)
        self.act_stop = QAction("⏹ Stop", parent)
        self.act_run.setEnabled(False)
        self.act_stop.setEnabled(False)
        self.toolbar.addAction(self.act_run)
        self.toolbar.addAction(self.act_stop)

        self.toolbar.addSeparator()

        # ── Theme switch() ──
        self.toolbar.addWidget(QLabel("UI Theme:"))
        self.cmb_theme = QComboBox(parent)
        self.cmb_theme.addItem("Light Mode", "light")
        self.cmb_theme.addItem("Dark Mode", "dark")
        self.cmb_theme.setMinimumWidth(110)
        self.toolbar.addWidget(self.cmb_theme)

        self.toolbar.addSeparator()

        # ── Tools ──
        self.act_settings = QAction("⚙ Settings", parent)
        self.act_help = QAction("❓ Help", parent)
        self.toolbar.addAction(self.act_settings)
        self.toolbar.addAction(self.act_help)

        # Convenience aliases
        self.new_project = self.act_new.triggered
        self.open_project = self.act_open.triggered
        self.save_project = self.act_save.triggered
        self.run_step = self.act_run.triggered
        self.stop_task = self.act_stop.triggered
        self.open_settings = self.act_settings.triggered
        self.theme_changed = self.cmb_theme.currentIndexChanged

    def set_project_state(self, has_project: bool):
        self.act_save.setEnabled(has_project)
        self.act_run.setEnabled(has_project)
        self.act_stop.setEnabled(has_project)

    def set_theme(self, theme: str):
        idx = 1 if theme == "dark" else 0
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.blockSignals(False)

    def current_theme(self) -> str:
        return self.cmb_theme.currentData() or "light"
