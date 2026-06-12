from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.services.sync_service import SyncService
from ncepu_cloud_client.sync.models import SyncDirection
from ncepu_cloud_client.ui.components.sync_task_card import SyncTaskCard

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget


class SyncTasksPage(QWidget):
    def __init__(self, client: CloudDriveClient, settings: Settings | None = None):
        super().__init__()
        self.service = SyncService(client, settings=settings)
        root = QVBoxLayout(self)
        title = QLabel("同步任务")
        title.setObjectName("PageTitle")
        form = QHBoxLayout()
        self.local_input = QLineEdit()
        self.local_input.setPlaceholderText("本地目录")
        self.remote_input = QLineEdit()
        self.remote_input.setPlaceholderText("云端目录 ID（如 gns://...），留空自动选择第一个可访问文档库")
        self.direction = QComboBox()
        self.direction.addItem("双向同步", SyncDirection.BIDIRECTIONAL.value)
        self.direction.addItem("本地到云端", SyncDirection.LOCAL_TO_REMOTE.value)
        self.direction.addItem("云端到本地", SyncDirection.REMOTE_TO_LOCAL.value)
        self.delete_sync = QCheckBox("同步删除")
        self.encrypt_sync = QCheckBox("加密上传")
        browse = QPushButton("选择目录")
        add = QPushButton("添加任务")
        start_all = QPushButton("启动同步")
        pause_all = QPushButton("暂停同步")
        add.setObjectName("PrimaryButton")
        browse.clicked.connect(self.browse)
        add.clicked.connect(self.add_task)
        start_all.clicked.connect(self.start_sync)
        pause_all.clicked.connect(self.pause_sync)
        form.addWidget(self.local_input, 1)
        form.addWidget(self.remote_input)
        form.addWidget(self.direction)
        form.addWidget(self.delete_sync)
        form.addWidget(self.encrypt_sync)
        form.addWidget(browse)
        form.addWidget(add)
        form.addWidget(start_all)
        form.addWidget(pause_all)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.list_widget)
        root.addWidget(title)
        root.addLayout(form)
        root.addWidget(scroll, 1)
        self.refresh()

    def browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择本地同步目录")
        if path:
            self.local_input.setText(path)

    def add_task(self) -> None:
        local = self.local_input.text().strip()
        remote = self.remote_input.text().strip() or "root"
        if not local:
            QMessageBox.warning(self, "缺少本地目录", "请选择本地同步目录。")
            return
        task_id = self.service.add_task(
            name=Path(local).name or "同步任务",
            local_root=Path(local),
            remote_root_id=remote,
            remote_root_path=remote,
            direction=SyncDirection(self.direction.currentData()),
            delete_sync_enabled=self.delete_sync.isChecked(),
            encryption_enabled=self.encrypt_sync.isChecked(),
        )
        QMessageBox.information(self, "任务已添加", f"同步任务 #{task_id} 已创建。")
        self.refresh()

    def refresh(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for task in self.service.database.list_sync_tasks():
            self.list_layout.addWidget(SyncTaskCard(task["name"], task["local_root"], task["remote_root_path"], task["direction"]))
        self.list_layout.addStretch(1)

    def start_sync(self) -> None:
        try:
            self.service.start()
            QMessageBox.information(self, "同步已启动", "本地文件变化会进入同步队列。")
        except Exception as exc:
            QMessageBox.warning(self, "同步启动失败", str(exc))

    def pause_sync(self) -> None:
        try:
            self.service.stop()
            QMessageBox.information(self, "同步已暂停", "已停止监听本地目录。")
        except Exception as exc:
            QMessageBox.warning(self, "同步暂停失败", str(exc))
