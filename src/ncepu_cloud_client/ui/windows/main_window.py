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
        self.resize(1180, 760)
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        self.sidebar = self._build_sidebar()
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 24, 18)
        topbar = self._build_topbar()
        self.stack = QStackedWidget()
        dashboard = DashboardPage(client)
        self.cloud_files_page = CloudFilesPage(client)
        sync_tasks = SyncTasksPage(client, settings)
        transfers = TransferPage()
        logs = LogsPage()
        settings_page = SettingsPage(settings)
        dashboard.open_sync_requested.connect(lambda: self.stack.setCurrentIndex(2))
        dashboard.open_cloud_requested.connect(lambda: self.stack.setCurrentIndex(1))
        dashboard.open_logs_requested.connect(lambda: self.stack.setCurrentIndex(4))
        dashboard.open_settings_requested.connect(lambda: self.stack.setCurrentIndex(5))
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

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(88)
        layout = QVBoxLayout(side)
        layout.setAlignment(Qt.AlignTop)
        logo = QLabel()
        logo.setObjectName("Logo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedHeight(76)
        pixmap = QPixmap(str(app_icon_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("☁")
        layout.addWidget(logo)
        navs = ["首页", "云端", "同步", "传输", "日志", "设置"]
        for index, text in enumerate(navs):
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.clicked.connect(lambda checked=False, i=index: self.stack.setCurrentIndex(i))
            layout.addWidget(button)
        layout.addStretch(1)
        return side

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        title = QLabel("华电云盘")
        title.setObjectName("AppTitle")
        self.top_search = QLineEdit()
        self.top_search.setPlaceholderText("欢迎使用华电网盘，点击此处开始搜索")
        self.top_search.returnPressed.connect(self.search_cloud)
        self.account_button = QPushButton("已登录")
        account_menu = QMenu(self.account_button)
        logout_action = account_menu.addAction("退出登录")
        switch_action = account_menu.addAction("切换用户")
        logout_action.triggered.connect(self.logout_requested.emit)
        switch_action.triggered.connect(self.switch_user_requested.emit)
        self.account_button.setMenu(account_menu)
        layout.addWidget(title)
        layout.addWidget(self.top_search, 1)
        layout.addWidget(self.account_button)
        return bar

    def search_cloud(self) -> None:
        keyword = self.top_search.text().strip()
        self.stack.setCurrentIndex(1)
        self.cloud_files_page.search_cloud(keyword)
