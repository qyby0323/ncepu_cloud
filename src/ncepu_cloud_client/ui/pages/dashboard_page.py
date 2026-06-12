from __future__ import annotations

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.api.models import CloudQuota
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.ui.components.status_badge import StatusBadge
from ncepu_cloud_client.utils.file_utils import human_size

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QProgressBar, QVBoxLayout, QWidget


class QuotaWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient):
        super().__init__()
        self.client = client

    def run(self) -> None:
        try:
            self.loaded.emit(self.client.get_quota())
        except Exception as exc:
            self.failed.emit(str(exc))


class MetricCard(QWidget):
    def __init__(self, title: str, value: str):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        label = QLabel(title)
        label.setStyleSheet("color: #667085;")
        self.value = QLabel(value)
        self.value.setObjectName("MetricValue")
        layout.addWidget(label)
        layout.addWidget(self.value)


class DashboardPage(QWidget):
    open_sync_requested = Signal()
    open_cloud_requested = Signal()
    open_logs_requested = Signal()
    open_settings_requested = Signal()

    def __init__(self, client: CloudDriveClient, database: SyncDatabase | None = None):
        super().__init__()
        self.client = client
        self.database = database or SyncDatabase()
        root = QVBoxLayout(self)
        header = QLabel("首页仪表盘")
        header.setObjectName("PageTitle")
        self.badge = StatusBadge("未连接")
        self.quota_bar = QProgressBar()
        self.quota_bar.setRange(0, 100)
        self.quota_label = QLabel("容量信息等待加载")
        grid = QGridLayout()
        self.sync_card = MetricCard("同步任务", "0")
        self.upload_card = MetricCard("正在上传", "0")
        self.download_card = MetricCard("正在下载", "0")
        self.error_card = MetricCard("最近错误", "-")
        for index, card in enumerate([self.sync_card, self.upload_card, self.download_card, self.error_card]):
            grid.addWidget(card, index // 2, index % 2)
        buttons = QGridLayout()
        shortcuts = [
            ("选择同步目录", self.open_sync_requested),
            ("打开云端文件", self.open_cloud_requested),
            ("查看日志", self.open_logs_requested),
            ("打开设置", self.open_settings_requested),
        ]
        for index, (text, signal) in enumerate(shortcuts):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            buttons.addWidget(button, 0, index)
        root.addWidget(header)
        root.addWidget(self.badge)
        root.addWidget(self.quota_label)
        root.addWidget(self.quota_bar)
        root.addLayout(grid)
        root.addLayout(buttons)
        root.addStretch(1)
        self.metric_timer = QTimer(self)
        self.metric_timer.setInterval(3000)
        self.metric_timer.timeout.connect(self.refresh_metrics)
        self.metric_timer.start()
        self.refresh_metrics()
        self.refresh()

    def refresh(self) -> None:
        self.worker = QuotaWorker(self.client)
        self.worker.loaded.connect(self._quota_loaded)
        self.worker.failed.connect(self._quota_failed)
        self.worker.start()

    def _quota_loaded(self, quota: CloudQuota) -> None:
        self.badge.set_badge("已连接", "#2f8f46")
        self.quota_bar.setValue(int(quota.percent * 100))
        self.quota_label.setText(f"已用 {human_size(quota.used)} / 总容量 {human_size(quota.total)}")

    def _quota_failed(self, message: str) -> None:
        self.badge.set_badge("离线", "#b42318")
        self.error_card.value.setText(message[:80])

    def refresh_metrics(self) -> None:
        tasks = self.database.list_sync_tasks()
        transfers = self.database.list_transfers(limit=200)
        running_uploads = [item for item in transfers if item.get("direction") == "upload" and item.get("status") == "running"]
        running_downloads = [item for item in transfers if item.get("direction") == "download" and item.get("status") == "running"]
        failed = [item for item in transfers if item.get("status") == "failed"]
        self.sync_card.value.setText(str(len(tasks)))
        self.upload_card.value.setText(str(len(running_uploads)))
        self.download_card.value.setText(str(len(running_downloads)))
        self.error_card.value.setText((failed[0].get("error_message") or "失败任务")[:80] if failed else "-")
