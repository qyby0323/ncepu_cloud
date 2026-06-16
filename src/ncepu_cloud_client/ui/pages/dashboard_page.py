from __future__ import annotations

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.api.models import CloudItem, CloudQuota
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.utils.file_utils import human_size

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


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


class RecentFilesWorker(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient):
        super().__init__()
        self.client = client

    def run(self) -> None:
        try:
            self.loaded.emit(self.client.list_dir(remote_path="/", parent_id=None))
        except Exception as exc:
            self.failed.emit(str(exc))


class SummaryBlock(QFrame):
    def __init__(self, title: str, value: str, note: str = ""):
        super().__init__()
        self.setObjectName("SubtleSurface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("MutedText")
        self.value = QLabel(value)
        self.value.setObjectName("MetricValue")
        self.note = QLabel(note)
        self.note.setObjectName("MutedText")
        layout.addWidget(label)
        layout.addWidget(self.value)
        layout.addWidget(self.note)
        self.body_layout = layout


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
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        header = QLabel("首页")
        header.setObjectName("PageTitle")
        subtitle = QLabel("默认只显示客户端是否正常、空间是否充足、是否需要处理。")
        subtitle.setObjectName("MutedText")
        title_box.addWidget(header)
        title_box.addWidget(subtitle)
        header_row.addLayout(title_box, 1)

        summary = QFrame()
        summary.setObjectName("Surface")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(18, 18, 18, 18)
        summary_layout.setSpacing(14)
        self.connection_card = SummaryBlock("连接状态", "连接正常", "真实 API 已连接")
        self.quota_card = SummaryBlock("容量", "容量充足", "等待容量信息")
        self.sync_card = SummaryBlock("待处理", "暂无待处理", "同步任务运行正常")
        self.quota_bar = QProgressBar()
        self.quota_bar.setRange(0, 100)
        self.quota_bar.setTextVisible(False)
        self.quota_card.body_layout.addWidget(self.quota_bar)
        summary_layout.addWidget(self.connection_card)
        summary_layout.addWidget(self.quota_card)
        summary_layout.addWidget(self.sync_card)

        self.upload_card = SummaryBlock("上传中", "0")
        self.download_card = SummaryBlock("下载中", "0")
        self.error_card = SummaryBlock("最近错误", "-")

        lower = QHBoxLayout()
        lower.setSpacing(18)
        recent = QFrame()
        recent.setObjectName("Surface")
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(18, 16, 18, 18)
        recent_layout.setSpacing(12)
        recent_title = QLabel("最近文件")
        recent_title.setObjectName("SectionTitle")
        self.recent_table = QTableWidget(0, 3)
        self.recent_table.setHorizontalHeaderLabels(["名称", "修改时间", "状态"])
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.recent_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.recent_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_empty = QLabel("正在加载云端文件...")
        self.recent_empty.setObjectName("MutedText")
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(self.recent_empty)
        recent_layout.addWidget(self.recent_table, 1)

        quick = QFrame()
        quick.setObjectName("Surface")
        quick.setFixedWidth(260)
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(18, 16, 18, 18)
        quick_layout.setSpacing(12)
        pending_title = QLabel("快速开始")
        pending_title.setObjectName("SectionTitle")
        self.pending_label = QLabel("暂无待处理事项")
        self.pending_label.setObjectName("SuccessText")
        cloud_button = QPushButton("打开云端文件")
        cloud_button.setObjectName("PrimaryButton")
        sync_button = QPushButton("新建同步任务")
        settings_button = QPushButton("打开设置")
        settings_button.setObjectName("GhostButton")
        cloud_button.clicked.connect(self.open_cloud_requested.emit)
        sync_button.clicked.connect(self.open_sync_requested.emit)
        settings_button.clicked.connect(self.open_settings_requested.emit)
        quick_layout.addWidget(pending_title)
        quick_layout.addWidget(self.pending_label)
        quick_layout.addSpacing(8)
        quick_layout.addWidget(cloud_button)
        quick_layout.addWidget(sync_button)
        quick_layout.addWidget(settings_button)
        quick_layout.addStretch(1)

        lower.addWidget(recent, 1)
        lower.addWidget(quick)

        footer = QLabel("真实 API · Token 自动刷新 · 日志已脱敏")
        footer.setObjectName("MutedText")

        root.addLayout(header_row)
        root.addWidget(summary)
        root.addLayout(lower, 1)
        root.addWidget(footer)
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
        self.recent_worker = RecentFilesWorker(self.client)
        self.recent_worker.loaded.connect(self._recent_files_loaded)
        self.recent_worker.failed.connect(self._recent_files_failed)
        self.recent_worker.start()

    def _quota_loaded(self, quota: CloudQuota) -> None:
        self.connection_card.value.setText("连接正常")
        self.connection_card.note.setText("真实 API 已连接")
        self.quota_bar.setValue(int(quota.percent * 100))
        self.quota_card.value.setText("容量充足")
        self.quota_card.note.setText(f"已用 {human_size(quota.used)} / {human_size(quota.total)}")

    def _quota_failed(self, message: str) -> None:
        self.connection_card.value.setText("连接异常")
        self.connection_card.note.setText(message[:80])
        self.error_card.value.setText(message[:80])
        self.pending_label.setText("连接需要处理")
        self.pending_label.setObjectName("WarningText")
        self.pending_label.style().unpolish(self.pending_label)
        self.pending_label.style().polish(self.pending_label)

    def refresh_metrics(self) -> None:
        tasks = self.database.list_sync_tasks()
        transfers = self.database.list_transfers(limit=200)
        running_uploads = [item for item in transfers if item.get("direction") == "upload" and item.get("status") == "running"]
        running_downloads = [item for item in transfers if item.get("direction") == "download" and item.get("status") == "running"]
        failed = [item for item in transfers if item.get("status") == "failed"]
        self.upload_card.value.setText(str(len(running_uploads)))
        self.download_card.value.setText(str(len(running_downloads)))
        self.error_card.value.setText((failed[0].get("error_message") or "失败任务")[:80] if failed else "-")
        running_count = len(running_uploads) + len(running_downloads)
        self.sync_card.value.setText("暂无待处理")
        if running_count:
            self.sync_card.note.setText(f"{running_count} 个传输任务进行中")
        elif tasks:
            self.sync_card.note.setText(f"{len(tasks)} 个同步任务运行正常")
        else:
            self.sync_card.note.setText("暂无同步任务")
        self.pending_label.setText("暂无待处理事项")
        self.pending_label.setObjectName("SuccessText")
        self.pending_label.style().unpolish(self.pending_label)
        self.pending_label.style().polish(self.pending_label)

    def _recent_files_loaded(self, items: list[CloudItem]) -> None:
        visible_items = items[:8]
        self.recent_table.setRowCount(len(visible_items))
        self.recent_empty.setVisible(len(visible_items) == 0)
        self.recent_empty.setText("云端根目录暂无文件。")
        for row, item in enumerate(visible_items):
            values = [
                item.name,
                item.modified_at or "-",
                "文件夹" if item.is_dir else "云端文件",
            ]
            for col, value in enumerate(values):
                self.recent_table.setItem(row, col, QTableWidgetItem(value))

    def _recent_files_failed(self, message: str) -> None:
        self.recent_table.setRowCount(0)
        self.recent_empty.setVisible(True)
        self.recent_empty.setText(f"最近文件加载失败：{message[:60]}")
