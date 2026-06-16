from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.services.sync_service import SyncService
from ncepu_cloud_client.sync.models import SyncDirection
from ncepu_cloud_client.ui.components.sync_task_card import SyncTaskCard

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget


class SyncTasksPage(QWidget):
    def __init__(self, client: CloudDriveClient, settings: Settings | None = None):
        super().__init__()
        self.service = SyncService(client, settings=settings)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("同步任务")
        title.setObjectName("PageTitle")
        subtitle = QLabel("配置本地目录与云端文档库之间的同步，默认保留本地修改并生成冲突副本。")
        subtitle.setObjectName("MutedText")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        form_panel = QFrame()
        form_panel.setObjectName("Surface")
        form_panel_layout = QVBoxLayout(form_panel)
        form_panel_layout.setContentsMargins(18, 16, 18, 18)
        form_panel_layout.setSpacing(12)
        form_title = QLabel("新建同步任务")
        form_title.setObjectName("SectionTitle")
        form = QHBoxLayout()
        form.setSpacing(8)
        self.local_input = QLineEdit()
        self.local_input.setPlaceholderText("本地目录")
        self.remote_input = QLineEdit()
        self.remote_input.setPlaceholderText("云端可写目录 ID（如 我的文档库 下的 gns://...），留空优先选择个人文档库")
        self.direction = QComboBox()
        self.direction.addItem("双向同步", SyncDirection.BIDIRECTIONAL.value)
        self.direction.addItem("本地到云端", SyncDirection.LOCAL_TO_REMOTE.value)
        self.direction.addItem("云端到本地", SyncDirection.REMOTE_TO_LOCAL.value)
        self.delete_sync = QCheckBox("同步删除")
        self.encrypt_sync = QCheckBox("加密上传")
        browse = QPushButton("选择目录")
        add = QPushButton("添加任务")
        add.setObjectName("PrimaryButton")
        browse.clicked.connect(self.browse)
        add.clicked.connect(self.add_task)
        form.addWidget(self.local_input, 1)
        form.addWidget(self.remote_input, 1)
        form.addWidget(self.direction)
        form.addWidget(browse)
        form.addWidget(add)
        safe_row = QHBoxLayout()
        safe_hint = QLabel("安全默认：同步删除关闭，冲突时保留双方。")
        safe_hint.setObjectName("MutedText")
        safe_row.addWidget(self.delete_sync)
        safe_row.addWidget(self.encrypt_sync)
        safe_row.addWidget(safe_hint)
        safe_row.addStretch(1)
        form_panel_layout.addWidget(form_title)
        form_panel_layout.addLayout(form)
        form_panel_layout.addLayout(safe_row)

        task_panel = QFrame()
        task_panel.setObjectName("Surface")
        task_panel_layout = QVBoxLayout(task_panel)
        task_panel_layout.setContentsMargins(18, 16, 18, 18)
        task_panel_layout.setSpacing(12)
        task_header = QHBoxLayout()
        task_title = QLabel("任务列表")
        task_title.setObjectName("SectionTitle")
        start_all = QPushButton("启动同步")
        pause_all = QPushButton("暂停同步")
        start_all.clicked.connect(self.start_sync)
        pause_all.clicked.connect(self.pause_sync)
        task_header.addWidget(task_title)
        task_header.addStretch(1)
        task_header.addWidget(start_all)
        task_header.addWidget(pause_all)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.list_widget)
        task_panel_layout.addLayout(task_header)
        task_panel_layout.addWidget(scroll, 1)

        safety = QFrame()
        safety.setObjectName("Surface")
        safety.setFixedWidth(270)
        safety_layout = QVBoxLayout(safety)
        safety_layout.setContentsMargins(18, 16, 18, 18)
        safety_layout.setSpacing(10)
        safety_title = QLabel("同步安全")
        safety_title.setObjectName("SectionTitle")
        for text, object_name in [
            ("删除同步：默认关闭", "SuccessText"),
            ("冲突策略：保留双方", "SuccessText"),
            ("加密上传：可选", "MutedText"),
            ("状态：暂无待处理", "SuccessText"),
        ]:
            label = QLabel(text)
            label.setObjectName(object_name)
            safety_layout.addWidget(label)
        safety_layout.addStretch(1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(task_panel, 1)
        body.addWidget(safety)
        footer = QLabel("传输队列空闲 · 日志已脱敏 · SQLite 状态库正常")
        footer.setObjectName("MutedText")

        root.addLayout(header)
        root.addWidget(form_panel)
        root.addLayout(body, 1)
        root.addWidget(footer)
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
        if self.list_layout.count() == 0:
            empty = QLabel("暂无同步任务。添加任务后会在这里显示状态。")
            empty.setObjectName("MutedText")
            self.list_layout.addWidget(empty)
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
