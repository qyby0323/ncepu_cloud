from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class ProgressItem(QWidget):
    def __init__(self, title: str, subtitle: str = "", progress: float = 0):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        title_label = QLabel(title)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #667085;")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(progress * 100))
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(bar)
        self.bar = bar

