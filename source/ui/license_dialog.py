from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QLineEdit,
)

from core.license_manager import LicenseManager


class LicenseDialog(QDialog):
    def __init__(self, license_manager: LicenseManager, initial_message: str = "", parent=None):
        super().__init__(parent)
        self.license_manager = license_manager
        self.setWindowTitle("Activate scFlow Studio")
        self.setMinimumWidth(640)
        self.setModal(True)
        self._build_ui(initial_message)

    def _build_ui(self, initial_message: str):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "This copy of scFlow Studio requires activation. Please send the device code to the developer to obtain an activation code.\n"
            "After successful activation, the license will be saved locally."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel("Device code:"))
        code_row = QHBoxLayout()
        self.txt_device_code = QLineEdit(self.license_manager.get_device_code())
        self.txt_device_code.setReadOnly(True)
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.clicked.connect(self._copy_device_code)
        code_row.addWidget(self.txt_device_code, 1)
        code_row.addWidget(self.btn_copy)
        layout.addLayout(code_row)

        layout.addWidget(QLabel("Activation code:"))
        self.txt_activation_code = QTextEdit()
        self.txt_activation_code.setPlaceholderText("Paste the activation code here.")
        self.txt_activation_code.setMinimumHeight(140)
        layout.addWidget(self.txt_activation_code)

        self.lbl_status = QLabel(initial_message or "Please enter an activation code.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #555555;")
        layout.addWidget(self.lbl_status)

        btn_box = QDialogButtonBox()
        self.btn_activate = btn_box.addButton("Activate", QDialogButtonBox.AcceptRole)
        self.btn_exit = btn_box.addButton("Quit", QDialogButtonBox.RejectRole)
        self.btn_activate.clicked.connect(self._activate)
        self.btn_exit.clicked.connect(self.reject)
        layout.addWidget(btn_box)

    def _copy_device_code(self):
        QApplication.clipboard().setText(self.txt_device_code.text().strip())
        self.lbl_status.setText("Device code copied.")
        self.lbl_status.setStyleSheet("color: #2E7D32;")

    def _activate(self):
        code = self.txt_activation_code.toPlainText().strip()
        status = self.license_manager.activate_from_code(code)
        if status.valid:
            self.lbl_status.setText(status.message)
            self.lbl_status.setStyleSheet("color: #2E7D32;")
            QMessageBox.information(self, "Success", status.message)
            self.accept()
            return

        self.lbl_status.setText(status.message)
        self.lbl_status.setStyleSheet("color: #C62828;")
        QMessageBox.warning(self, "Failed", status.message)
