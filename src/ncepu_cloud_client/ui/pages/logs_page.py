from __future__ import annotations

from ncepu_cloud_client.app.paths import log_file

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


class LogsPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("日志")
        title.setObjectName("PageTitle")
        toolbar = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(["ALL", "INFO", "WARNING", "ERROR"])
        refresh = QPushButton("刷新")
        clear = QPushButton("清空显示")
        refresh.clicked.connect(self.refresh)
        clear.clicked.connect(lambda: self.text.clear())
        toolbar.addWidget(self.level)
        toolbar.addWidget(refresh)
        toolbar.addWidget(clear)
        toolbar.addStretch(1)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        root.addWidget(title)
        root.addLayout(toolbar)
        root.addWidget(self.text, 1)
        self.refresh()

    def refresh(self) -> None:
        path = log_file()
        if not path.exists():
            self.text.setPlainText("暂无日志")
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
        level = self.level.currentText()
        if level != "ALL":
            lines = [line for line in lines if f" {level} " in line]
        self.text.setPlainText("\n".join(lines))

