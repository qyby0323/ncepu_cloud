from __future__ import annotations

import sys

from ncepu_cloud_client.app.bootstrap import bootstrap, build_client
from ncepu_cloud_client.app.constants import APP_NAME
from ncepu_cloud_client.auth.token_store import TokenStore
from ncepu_cloud_client.config.config_manager import ConfigManager
from ncepu_cloud_client.ui.resources import app_icon_path
from ncepu_cloud_client.ui.styles import load_styles
from ncepu_cloud_client.ui.windows.login_window import LoginWindow
from ncepu_cloud_client.ui.windows.main_window import MainWindow

LOGOUT_EXIT_CODE = 100
SWITCH_USER_EXIT_CODE = 101


def _set_windows_app_user_model_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"NCEPU.{APP_NAME}")
    except Exception:
        pass


def run_app() -> int:
    _set_windows_app_user_model_id()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon

    bootstrap()
    app = QApplication(sys.argv)
    app.setApplicationName("NCEPUCloudClient")
    icon = QIcon(str(app_icon_path()))
    app.setWindowIcon(icon)
    auto_start_login = False
    while True:
        settings = ConfigManager().load()
        if auto_start_login:
            settings.app.mode = "real"
        client = build_client(settings)
        app.setStyleSheet(load_styles(settings.app.theme))
        login = LoginWindow(settings, client)
        login.setWindowIcon(icon)
        if auto_start_login:
            login.set_mode("real")
            QTimer.singleShot(0, login.login_with_embedded_browser)
        auto_start_login = False
        if login.exec() != LoginWindow.Accepted:
            return 0

        settings = ConfigManager().load()
        client = build_client(settings)
        window = MainWindow(settings, client)
        window.setWindowIcon(icon)

        def return_to_login(exit_code: int) -> None:
            try:
                if settings.app.mode == "mock":
                    client.logout()
                else:
                    TokenStore(settings.security).clear()
            finally:
                window.close()
                app.exit(exit_code)

        window.logout_requested.connect(lambda: return_to_login(LOGOUT_EXIT_CODE))
        window.switch_user_requested.connect(lambda: return_to_login(SWITCH_USER_EXIT_CODE))
        window.show()
        result = app.exec()
        if result == LOGOUT_EXIT_CODE:
            auto_start_login = False
            continue
        if result == SWITCH_USER_EXIT_CODE:
            auto_start_login = True
            continue
        return result
