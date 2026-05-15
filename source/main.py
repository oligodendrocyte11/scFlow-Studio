#!/usr/bin/env python3
"""
scFlow Studio Application entry point
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.main_window import MainWindow
from core.license_manager import LicenseManager
from core.runtime_paths import get_icon_path
from ui.license_dialog import LicenseDialog


def _configure_qt_plugin_paths() -> None:
    """Ensure frozen builds can locate the Qt platform plugin."""
    if not getattr(sys, "frozen", False):
        return

    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    plugin_root = base_dir / "PySide6" / "plugins"
    platform_root = plugin_root / "platforms"

    if plugin_root.is_dir():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))
    if platform_root.is_dir():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platform_root))


def main():
    _configure_qt_plugin_paths()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("scFlow Studio")
    app.setApplicationVersion("0.1.0-mvp")
    app.setOrganizationName("scFlowStudio")
    default_font = "Segoe UI" if sys.platform.startswith("win") else "SF Pro Text" if sys.platform == "darwin" else "Sans Serif"
    app.setFont(QFont(default_font, 10))

    icon_path = get_icon_path()
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    license_manager = LicenseManager()
    license_status = license_manager.load_saved_license()
    if license_manager.is_academic_trial():
        app.setApplicationName("scFlow Studio Academic Trial")
    if not license_status.valid:
        if license_manager.is_academic_trial():
            QMessageBox.critical(None, "Academic Trial Expired", license_status.message)
            return 0
        dialog = LicenseDialog(license_manager, initial_message=license_status.message)
        if dialog.exec() != LicenseDialog.Accepted:
            return 0

    window = MainWindow()
    if license_manager.is_academic_trial():
        expires_at = license_status.payload.get("expires_at", "2026-10-01")
        window.setWindowTitle(f"scFlow Studio - Academic Trial Version (Valid until {expires_at})")
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
