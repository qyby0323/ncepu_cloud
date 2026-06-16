from __future__ import annotations

from PySide6.QtWidgets import QLabel, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget


class SyncTaskCard(QWidget):
    def __init__(self, name: str, local_root: str, remote_root: str, direction: str):
        super().__init__()
        self.setObjectName("Surface")
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(6)
        title = QLabel(name)
        title.setObjectName("SectionTitle")
        detail = QLabel(f"{local_root}  ->  {remote_root}")
        detail.setObjectName("MutedText")
        direction_label = QLabel(f"方向：{direction} · 状态：正常")
        direction_label.setObjectName("SuccessText")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        left.addWidget(title)
        left.addWidget(detail)
        left.addWidget(direction_label)
        left.addWidget(bar)
        start = QPushButton("启动")
        pause = QPushButton("暂停")
        start.setObjectName("GhostButton")
        pause.setObjectName("GhostButton")
        root.addLayout(left, 1)
        root.addWidget(start)
        root.addWidget(pause)
