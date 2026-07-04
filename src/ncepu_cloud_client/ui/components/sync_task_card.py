from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget


class SyncTaskCard(QWidget):
    delete_requested = Signal(int)

    def __init__(self, task_id: int, name: str, local_root: str, remote_root: str, direction: str, ignore_rules: str = ""):
        super().__init__()
        self.task_id = task_id
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
        rules_text = self._rules_summary(ignore_rules)
        rules_label = QLabel(f"过滤规则：{rules_text}")
        rules_label.setObjectName("MutedText")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        left.addWidget(title)
        left.addWidget(detail)
        left.addWidget(direction_label)
        left.addWidget(rules_label)
        left.addWidget(bar)
        start = QPushButton("启动")
        pause = QPushButton("暂停")
        delete = QPushButton("删除")
        start.setObjectName("GhostButton")
        pause.setObjectName("GhostButton")
        delete.setObjectName("GhostButton")
        delete.clicked.connect(lambda: self.delete_requested.emit(self.task_id))
        root.addLayout(left, 1)
        root.addWidget(start)
        root.addWidget(pause)
        root.addWidget(delete)

    @staticmethod
    def _rules_summary(ignore_rules: str) -> str:
        # 卡片上只显示简短摘要，完整规则仍保存在数据库中。
        # 这样任务很多时界面不会被长规则列表撑高。
        rules = [line.strip() for line in ignore_rules.splitlines() if line.strip() and not line.strip().startswith("#")]
        if not rules:
            return "默认规则 + 当前目录 .syncignore"
        if len(rules) <= 3:
            return "、".join(rules)
        return "、".join(rules[:3]) + f" 等 {len(rules)} 条"
