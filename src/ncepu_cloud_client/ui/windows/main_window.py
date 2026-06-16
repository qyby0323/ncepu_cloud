from __future__ import annotations

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.ui.pages.cloud_files_page import CloudFilesPage
from ncepu_cloud_client.ui.pages.dashboard_page import DashboardPage
from ncepu_cloud_client.ui.pages.logs_page import LogsPage
from ncepu_cloud_client.ui.pages.settings_page import SettingsPage
from ncepu_cloud_client.ui.pages.sync_tasks_page import SyncTasksPage
from ncepu_cloud_client.ui.pages.transfer_page import TransferPage
from ncepu_cloud_client.ui.resources import app_icon_path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    logout_requested = Signal()
    switch_user_requested = Signal()

    def __init__(self, settings: Settings, client: CloudDriveClient):
        super().__init__()
        self.settings = settings
        self.client = client
        self.setWindowTitle("华电云盘客户端")
        self.resize(1280, 820)
        self.nav_buttons: list[QPushButton] = []
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = self._build_sidebar()
        content = QWidget()
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 22)
        content_layout.setSpacing(18)
        topbar = self._build_topbar()
        self.stack = QStackedWidget()
        dashboard = DashboardPage(client)
        self.cloud_files_page = CloudFilesPage(client)
        sync_tasks = SyncTasksPage(client, settings)
        transfers = TransferPage()
        logs = LogsPage()
        settings_page = SettingsPage(settings)
        dashboard.open_sync_requested.connect(lambda: self._switch_page(2))
        dashboard.open_cloud_requested.connect(lambda: self._switch_page(1))
        dashboard.open_logs_requested.connect(lambda: self._switch_page(4))
        dashboard.open_settings_requested.connect(lambda: self._switch_page(5))
        self.pages = [
            dashboard,
            self.cloud_files_page,
            sync_tasks,
            transfers,
            logs,
            settings_page,
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        content_layout.addWidget(topbar)
        content_layout.addWidget(self.stack, 1)
        outer.addWidget(self.sidebar)
        outer.addWidget(content, 1)
        self.setCentralWidget(central)
        self._switch_page(0)

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(240)
        layout = QVBoxLayout(side)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(6)

        brand_row = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("Logo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(44, 44)
        pixmap = QPixmap(str(app_icon_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("云")
        brand_text = QVBoxLayout()
        brand = QLabel("华电云盘")
        brand.setObjectName("SidebarBrand")
        caption = QLabel("NCEPU Cloud")
        caption.setObjectName("SidebarCaption")
        brand_text.addWidget(brand)
        brand_text.addWidget(caption)
        brand_row.addWidget(logo)
        brand_row.addLayout(brand_text, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(14)

        navs = ["首页", "云端文件", "同步任务", "传输队列", "日志", "设置"]
        for index, text in enumerate(navs):
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)

        layout.addSpacing(14)
        section = QLabel("文档库")
        section.setObjectName("SidebarSection")
        layout.addWidget(section)
        for index, text in enumerate(["我的文档库", "共享文档库", "课程资料", "最近访问"]):
            item = QLabel(text)
            item.setObjectName("LibraryItemSelected" if index == 0 else "LibraryItem")
            layout.addWidget(item)
        layout.addStretch(1)
        status = QLabel("真实 API · 已连接")
        status.setObjectName("SidebarCaption")
        layout.addWidget(status)
        return side

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.top_search = QLineEdit()
        self.top_search.setObjectName("TopSearch")
        self.top_search.setPlaceholderText("搜索文件或同步任务")
        self.top_search.returnPressed.connect(self.search_cloud)
        self.account_button = QPushButton("已登录")
        self.account_button.setObjectName("AccountButton")
        account_menu = QMenu(self.account_button)
        logout_action = account_menu.addAction("退出登录")
        switch_action = account_menu.addAction("切换用户")
        logout_action.triggered.connect(self.logout_requested.emit)
        switch_action.triggered.connect(self.switch_user_requested.emit)
        self.account_button.setMenu(account_menu)
        layout.addWidget(self.top_search, 1)
        layout.addWidget(self.account_button)
        return bar

    def _switch_page(self, index: int) -> None:
        if hasattr(self, "stack"):
            self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def search_cloud(self) -> None:
        keyword = self.top_search.text().strip()
        self._switch_page(1)
        self.cloud_files_page.search_cloud(keyword)
