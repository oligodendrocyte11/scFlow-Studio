"""Sidebar: workflow step list and status display."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QFont


# Step status → 
STATUS_STYLE = {
    "pending":  ("○", "#888888"),
    "current":  ("●", "#2196F3"),
    "done":     ("✓", "#4CAF50"),
    "error":    ("✗", "#F44336"),
    "running":  ("⟳", "#FF9800"),
}


class SideBar(QWidget):
    """"""
    step_clicked = Signal(int)

    def __init__(self, steps: list):
        """
        Args:
            steps: [(step_id, display_name, label), ...]
        """
        super().__init__()
        self.steps = steps
        self.setFixedWidth(200)
        self.setObjectName("sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 
        title = QLabel(" ")
        title.setObjectName("sidebar_title")
        title.setFixedHeight(40)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(title)

        # StepLists
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("step_list")
        self.list_widget.setSpacing(2)

        for i, (step_id, name, label) in enumerate(steps):
            item = QListWidgetItem(f"  ○  {label}")
            item.setData(Qt.UserRole, step_id)
            item_font = QFont()
            item_font.setPointSize(11)
            item.setFont(item_font)
            item.setSizeHint(item.sizeHint().__class__(200, 42))
            self.list_widget.addItem(item)

        self.list_widget.currentRowChanged.connect(self.step_clicked.emit)
        layout.addWidget(self.list_widget)

    def set_current(self, index: int):
        self.list_widget.setCurrentRow(index)

    def set_step_status(self, index: int, status: str):
        """StepStatus"""
        if index >= self.list_widget.count():
            return
        item = self.list_widget.item(index)
        marker, color = STATUS_STYLE.get(status, ("○", "#888"))
        step_id, name, label = self.steps[index]
        item.setText(f"  {marker}  {label}")
        item.setForeground(QColor(color))
