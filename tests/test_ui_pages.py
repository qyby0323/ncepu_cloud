import time

import pytest

from ncepu_cloud_client.api.models import CloudItem, CloudItemType, CloudQuota, TokenBundle
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.ui.pages.dashboard_page import DashboardPage
from ncepu_cloud_client.ui.pages.cloud_files_page import CloudFilesPage
from ncepu_cloud_client.ui.pages.settings_page import SettingsPage
from ncepu_cloud_client.ui.windows.login_window import LoginSettingsDialog, LoginWindow
from ncepu_cloud_client.ui.windows.main_window import MainWindow
from PySide6.QtWidgets import QApplication, QPushButton


class FakeUiClient:
    def __init__(self):
        self.search_calls = []

    def list_dir(self, remote_path=None, parent_id=None):
        return []

    def search(self, keyword):
        self.search_calls.append(keyword)
        return []

    def get_quota(self):
        return CloudQuota(total=1024, used=128)


class FolderUiClient(FakeUiClient):
    def __init__(self):
        self.calls = []

    def list_dir(self, remote_path=None, parent_id=None):
        self.calls.append((remote_path, parent_id))
        if parent_id == "gns://root/课程资料":
            return []
        return [
            CloudItem(
                id="gns://root/课程资料",
                name="课程资料",
                type=CloudItemType.DIRECTORY,
                path="gns://root/课程资料",
            )
        ]


class FakeLoginClient:
    def login(self):
        return None


class RejectingLoginClient(FakeLoginClient):
    def list_libraries(self):
        raise RuntimeError("invalid token")


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def wait_until(app: QApplication, predicate, timeout_ms: int = 1000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def test_settings_page_builds_with_scroll_area(qapp):
    page = SettingsPage(Settings())
    assert page.custom_ignore_rules.placeholderText()
    assert page.oauth_extra_params.placeholderText()
    page.deleteLater()


def test_login_window_uses_minimal_mode_panels(qapp):
    settings = Settings()
    settings.api.client_secret = "secret"
    window = LoginWindow(settings, FakeLoginClient())

    assert window.settings_button.text() == "设置"
    assert window.real_mode_button.text() == "REAL"
    assert window.mock_mode_button.text() == "MOCK"
    assert window.save_password.isChecked()
    assert not window.real_panel.isHidden()
    assert window.mock_panel.isHidden()
    assert window.primary_button.text() == "登录真实华电云盘"
    assert not hasattr(window, "api_prefix")

    window.set_mode("mock")

    assert window.mock_mode_button.isChecked()
    assert window.real_panel.isHidden()
    assert not window.mock_panel.isHidden()
    assert window.primary_button.text() == "进入 MOCK 模式"
    window.deleteLater()


def test_login_settings_dialog_contains_advanced_fields(qapp):
    window = LoginWindow(Settings(), FakeLoginClient())
    dialog = LoginSettingsDialog(window)

    assert dialog.api_prefix.text() == "/api"
    assert dialog.oauth_extra_params.placeholderText()
    assert dialog.manual_access_token.placeholderText()
    assert dialog.sso_params.placeholderText()
    dialog.deleteLater()
    window.deleteLater()


def test_login_window_parses_manual_token_formats(qapp):
    assert LoginWindow._token_bundle_from_text("Authorization: Bearer access-1").access_token == "access-1"
    assert LoginWindow._token_bundle_from_text('{"access_token":"access-2","refresh_token":"refresh-2"}').refresh_token == "refresh-2"
    assert LoginWindow._token_bundle_from_text("http://127.0.0.1/callback#access_token=access-3").access_token == "access-3"
    assert LoginWindow._token_bundle_from_text('{"session":"{\\"accessToken\\":\\"access-4\\"}"}').access_token == "access-4"
    assert LoginWindow._token_bundle_from_text("foo=bar; tokenid=access-5").access_token == "access-5"
    assert LoginWindow._token_bundle_from_text("Cookie: sid=1; uid=2").token_type == "Cookie"


def test_login_window_rejects_invalid_auto_token(qapp, monkeypatch):
    class FakeTokenStore:
        saved: list[TokenBundle] = []
        cleared = False

        def __init__(self, *args, **kwargs):
            pass

        def save(self, bundle):
            self.saved.append(bundle)

        def clear(self):
            type(self).cleared = True

    monkeypatch.setattr("ncepu_cloud_client.ui.windows.login_window.TokenStore", FakeTokenStore)
    window = LoginWindow(Settings(), RejectingLoginClient())

    assert not window.validate_and_store_token_bundle(TokenBundle(access_token="bad-token"))
    assert FakeTokenStore.saved[0].access_token == "bad-token"
    assert FakeTokenStore.cleared is True
    window.deleteLater()


def test_cloud_files_page_builds_and_loads_empty_root(qapp):
    page = CloudFilesPage(FakeUiClient())
    wait_until(qapp, lambda: not page.worker.isRunning())
    assert page.table.rowCount() == 0
    page.deleteLater()


def test_main_window_topbar_search_and_account_menu(qapp):
    client = FakeUiClient()
    window = MainWindow(Settings(), client)
    wait_until(qapp, lambda: not window.cloud_files_page.worker.isRunning())
    wait_until(qapp, lambda: not window.pages[0].worker.isRunning())

    assert window.top_search.placeholderText() == "欢迎使用华电网盘，点击此处开始搜索"
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}
    assert "会员中心" not in buttons
    assert "已登录" in buttons
    assert [action.text() for action in window.account_button.menu().actions()] == ["退出登录", "切换用户"]

    window.top_search.setText("课程设计")
    window.search_cloud()
    wait_until(qapp, lambda: not window.cloud_files_page.worker.isRunning())

    assert window.stack.currentIndex() == 1
    assert client.search_calls == ["课程设计"]
    assert "课程设计" in window.cloud_files_page.status.text()
    window.deleteLater()


def test_cloud_files_page_opens_selected_folder(qapp):
    client = FolderUiClient()
    page = CloudFilesPage(client)
    wait_until(qapp, lambda: not page.worker.isRunning())

    page.table.setCurrentCell(0, 0)
    page.open_selected()
    wait_until(qapp, lambda: not page.worker.isRunning())

    assert client.calls[-1] == ("gns://root/课程资料", "gns://root/课程资料")
    assert page.breadcrumb.text() == "gns://root/课程资料"
    page.deleteLater()


def test_dashboard_metrics_read_sync_database(qapp, tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    task_id = db.add_sync_task(
        name="demo",
        local_root=str(tmp_path),
        remote_root_id="root",
        remote_root_path="/",
        direction="bidirectional",
    )
    upload_id = db.add_transfer(task_id, str(tmp_path / "a.txt"), "r1", "upload")
    download_id = db.add_transfer(task_id, str(tmp_path / "b.txt"), "r2", "download")
    failed_id = db.add_transfer(task_id, str(tmp_path / "c.txt"), "r3", "download")
    db.update_transfer(upload_id, status="running", progress=0.5)
    db.update_transfer(download_id, status="running", progress=0.25)
    db.update_transfer(failed_id, status="failed", error_message="网络超时")

    page = DashboardPage(FakeUiClient(), database=db)
    wait_until(qapp, lambda: not page.worker.isRunning())
    page.refresh_metrics()

    assert page.sync_card.value.text() == "1"
    assert page.upload_card.value.text() == "1"
    assert page.download_card.value.text() == "1"
    assert page.error_card.value.text() == "网络超时"
    page.deleteLater()


def test_dashboard_shortcut_buttons_emit_signals(qapp, tmp_path):
    page = DashboardPage(FakeUiClient(), database=SyncDatabase(tmp_path / "state.db"))
    wait_until(qapp, lambda: not page.worker.isRunning())
    buttons = {button.text(): button for button in page.findChildren(QPushButton)}
    emitted: list[str] = []
    page.open_cloud_requested.connect(lambda: emitted.append("cloud"))
    page.open_settings_requested.connect(lambda: emitted.append("settings"))

    buttons["打开云端文件"].click()
    buttons["打开设置"].click()

    assert emitted == ["cloud", "settings"]
    page.deleteLater()
