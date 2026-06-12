from __future__ import annotations

from ncepu_cloud_client.sync.database import SyncDatabase

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class TransferPage(QWidget):
    def __init__(self):
        super().__init__()
        self.database = SyncDatabase()
        root = QVBoxLayout(self)
        title = QLabel("传输列表")
        title.setObjectName("PageTitle")
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["文件名", "方向", "进度", "状态", "错误信息", "创建时间", "更新时间"])
        root.addWidget(title)
        root.addWidget(refresh)
        root.addWidget(self.table, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        records = self.database.list_transfers()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.get("local_path") or "-",
                record.get("direction") or "-",
                "",
                record.get("status") or "-",
                record.get("error_message") or "",
                record.get("created_at") or "",
                record.get("updated_at") or "",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(float(record.get("progress") or 0) * 100))
            self.table.setCellWidget(row, 2, bar)
