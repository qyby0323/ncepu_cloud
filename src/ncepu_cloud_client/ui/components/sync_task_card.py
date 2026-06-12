from __future__ import annotations

from PySide6.QtWidgets import QLabel, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget


class SyncTaskCard(QWidget):
    def __init__(self, name: str, local_root: str, remote_root: str, direction: str):
        super().__init__()
        self.setObjectName("Card")
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        title = QLabel(name)
        title.setObjectName("CardTitle")
        detail = QLabel(f"{local_root}  ->  {remote_root}\n{direction}")
        detail.setStyleSheet("color: #667085;")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        left.addWidget(title)
        left.addWidget(detail)
        left.addWidget(bar)
        start = QPushButton("启动")
        pause = QPushButton("暂停")
        root.addLayout(left, 1)
        root.addWidget(start)
        root.addWidget(pause)

