from __future__ import annotations

from ncepu_cloud_client.api.models import CloudItem
from ncepu_cloud_client.utils.file_utils import human_size

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


class FileTable(QTableWidget):
    def __init__(self):
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(["名称", "类型", "大小", "修改时间", "状态"])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for section in range(1, 5):
            self.horizontalHeader().setSectionResizeMode(section, QHeaderView.ResizeToContents)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.items: list[CloudItem] = []

    def set_items(self, items: list[CloudItem]) -> None:
        self.items = items
        self.setRowCount(len(items))
        for row, item in enumerate(items):
            type_text = "文件夹" if item.is_dir else "文件"
            status = "云端文件" if item.is_dir else "已同步"
            values = [item.name, type_text, human_size(item.size), item.modified_at or "-", status]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 0:
                    cell.setData(Qt.UserRole, item)
                self.setItem(row, col, cell)

    def selected_item(self) -> CloudItem | None:
        row = self.currentRow()
        if row < 0:
            selected = self.selectionModel().selectedRows()
            if selected:
                row = selected[0].row()
        if row < 0 or row >= len(self.items):
            return None
        return self.items[row]
