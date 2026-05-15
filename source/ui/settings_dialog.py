from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from app.config import AppConfig, detect_rscript, save_app_config
from core.runtime_paths import get_bundled_rscript

SUBPROCESS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SettingsDialog(QDialog):
    def __init__(self, app_config: AppConfig, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        self.bundled_rscript = get_bundled_rscript()
        self.setWindowTitle("Settings")
        self.setMinimumWidth(620)
        self.setMinimumHeight(480)

        self._build_ui()
        self._load_from_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        example_path = (
            r"Example: C:\Program Files\R\R-4.4.3\bin\Rscript.exe"
            if os.name == "nt"
            else "/usr/local/bin/Rscript"
        )

        grp_r = QGroupBox("R Environment")
        r_layout = QVBoxLayout(grp_r)

        path_layout = QHBoxLayout()
        path_label = QLabel("Rscript Path:")
        path_label.setFixedWidth(90)
        self.txt_r_path = QLineEdit()
        self.txt_r_path.setPlaceholderText(example_path)
        self.btn_browse_r = QPushButton("Browse...")
        self.btn_browse_r.setFixedWidth(70)
        self.btn_browse_r.clicked.connect(self._browse_rscript)
        self.btn_auto_detect = QPushButton("Auto")
        self.btn_auto_detect.setFixedWidth(80)
        self.btn_auto_detect.clicked.connect(self._auto_detect_r)

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.txt_r_path, 1)
        path_layout.addWidget(self.btn_browse_r)
        path_layout.addWidget(self.btn_auto_detect)
        r_layout.addLayout(path_layout)

        self.lbl_bundled_r = QLabel("")
        self.lbl_bundled_r.setWordWrap(True)
        r_layout.addWidget(self.lbl_bundled_r)

        test_layout = QHBoxLayout()
        self.btn_test_r = QPushButton("Test R")
        self.btn_test_r.setFixedWidth(140)
        self.btn_test_r.clicked.connect(self._test_r_env)
        self.lbl_r_status = QLabel("")
        self.lbl_r_status.setWordWrap(True)
        test_layout.addWidget(self.btn_test_r)
        test_layout.addWidget(self.lbl_r_status, 1)
        r_layout.addLayout(test_layout)

        self.txt_r_info = QTextEdit()
        self.txt_r_info.setReadOnly(True)
        self.txt_r_info.setMaximumHeight(120)
        self.txt_r_info.setPlaceholderText("Click Test R to inspect the configured R environment.")
        r_layout.addWidget(self.txt_r_info)
        layout.addWidget(grp_r)

        grp_defaults = QGroupBox("Parameters")
        form = QFormLayout(grp_defaults)
        self.spn_seed = QSpinBox()
        self.spn_seed.setRange(1, 999999)
        self.spn_preview_dpi = QSpinBox()
        self.spn_preview_dpi.setRange(72, 300)
        self.spn_export_dpi = QSpinBox()
        self.spn_export_dpi.setRange(150, 600)
        form.addRow("Random seed:", self.spn_seed)
        form.addRow("Preview DPI:", self.spn_preview_dpi)
        form.addRow("Export DPI:", self.spn_export_dpi)
        layout.addWidget(grp_defaults)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("Save Settings")
        btn_box.button(QDialogButtonBox.Cancel).setText("Cancel")
        btn_box.accepted.connect(self._save_and_close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_from_config(self):
        configured = (self.app_config.r_executable or "").strip()
        if self.bundled_rscript:
            bundled_ = f"Bundled R detected: {self.bundled_rscript}"
            if os.name == "nt" and configured in ("", "Rscript"):
                self.txt_r_path.setText(str(self.bundled_rscript))
                bundled_ = f"Bundled R detected (portable): {self.bundled_rscript}"
            else:
                self.txt_r_path.setText(configured)
                bundled_ += "\nOn macOS, the bundled Rscript is preferred when available."
            self.lbl_bundled_r.setText(bundled_)
        else:
            self.txt_r_path.setText(configured)
            self.lbl_bundled_r.setText("No bundled R was detected. Please configure Rscript manually.")

        self.spn_seed.setValue(self.app_config.default_seed)
        self.spn_preview_dpi.setValue(self.app_config.preview_dpi)
        self.spn_export_dpi.setValue(self.app_config.export_dpi)

    def _save_and_close(self):
        r_path = self.txt_r_path.text().strip()
        if not r_path:
            QMessageBox.warning(self, "Notice", "Please provide an Rscript path.")
            return

        self.app_config.r_executable = r_path
        self.app_config.default_seed = self.spn_seed.value()
        self.app_config.preview_dpi = self.spn_preview_dpi.value()
        self.app_config.export_dpi = self.spn_export_dpi.value()
        save_app_config(self.app_config)
        self.accept()

    def _browse_rscript(self):
        if os.name == "nt":
            filter_str = "Rscript (Rscript.exe);;file (*)"
            start_dir = r"C:\Program Files\R"
        else:
            filter_str = "Rscript (Rscript*);;file (*)"
            start_dir = "/usr/local/bin"
        if not os.path.isdir(start_dir):
            start_dir = ""
        path, _ = QFileDialog.getOpenFileName(self, "Select Rscript file", start_dir, filter_str)
        if path:
            self.txt_r_path.setText(path)
            QTimer.singleShot(200, self._test_r_env)

    def _auto_detect_r(self):
        self._set_status("Testing Rscript...", "#FF9800")
        self.txt_r_info.clear()
        detected = detect_rscript()
        if detected:
            self.txt_r_path.setText(detected)
            self._set_status(f"Detected R: {detected}", "#2E7D32")
            QTimer.singleShot(200, self._test_r_env)
        else:
            hint = "R was not detected. Please select Rscript.exe." if os.name == "nt" else "R was not detected. Please select Rscript."
            self._set_status(hint, "#C62828")

    def _test_r_env(self):
        r_path = self.txt_r_path.text().strip()
        if not r_path:
            self._set_status("Please provide an Rscript path.", "#C62828")
            return

        self._set_status("Testing Rscript...", "#FF9800")
        self.txt_r_info.clear()
        self.btn_test_r.setEnabled(False)
        try:
            result = subprocess.run(
                [r_path, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
                creationflags=SUBPROCESS_NO_WINDOW,
            )
            version_output = (result.stdout + result.stderr).strip()
            if result.returncode != 0 and not version_output:
                self._set_status(f"Rscript Failed(exit {result.returncode}).", "#C62828")
                return
            self._set_status("R is available.", "#2E7D32")
            self.txt_r_info.setPlainText(version_output or "Rscript is available.")
        except FileNotFoundError:
            self._set_status("Cannot find Rscript. Please check the path.", "#C62828")
        except subprocess.TimeoutExpired:
            self._set_status("Rscript test timed out after 15 seconds.", "#C62828")
        except Exception as exc:
            self._set_status(f"Test failed: {exc}", "#C62828")
        finally:
            self.btn_test_r.setEnabled(True)

    def _set_status(self, text: str, color: str):
        self.lbl_r_status.setText(text)
        self.lbl_r_status.setStyleSheet(f"color: {color};")
