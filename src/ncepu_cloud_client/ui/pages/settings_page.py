from __future__ import annotations

import json

from ncepu_cloud_client.config.config_manager import ConfigManager
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.app.paths import app_data_dir, config_file, log_dir
from ncepu_cloud_client.security.key_store import EncryptionKeyStore

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QHBoxLayout,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TestConnectionWorker(QThread):
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        try:
            from ncepu_cloud_client.app.bootstrap import build_client
            from ncepu_cloud_client.utils.file_utils import human_size

            quota = build_client(self.settings).get_quota()
            self.ok.emit(f"连接成功：已用 {human_size(quota.used)} / {human_size(quota.total)}")
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsPage(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.manager = ConfigManager()
        root = QVBoxLayout(self)
        title = QLabel("设置")
        title.setObjectName("PageTitle")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.mode = QComboBox()
        self.mode.addItems(["real", "mock"])
        self.mode.setCurrentText(settings.app.mode)
        self.theme = QComboBox()
        self.theme.addItems(["light", "dark"])
        self.theme.setCurrentText(settings.app.theme)
        self.base_url = QLineEdit(settings.api.base_url)
        self.api_prefix = QLineEdit(settings.api.api_prefix)
        self.auth_url = QLineEdit(settings.api.auth_url)
        self.client_id = QLineEdit(settings.api.client_id)
        self.client_secret = QLineEdit(settings.api.client_secret)
        self.client_secret.setEchoMode(QLineEdit.Password)
        self.redirect_uri = QLineEdit(settings.api.redirect_uri)
        self.oauth_scope = QLineEdit(settings.api.oauth_scope)
        self.oauth_extra_params = QLineEdit(json.dumps(settings.api.extra_oauth_params, ensure_ascii=False))
        self.oauth_extra_params.setPlaceholderText('可选，例如 {"tenant":"ncepu"}')
        self.oauth_auth_method = QComboBox()
        self.oauth_auth_method.addItems(["basic", "body"])
        self.oauth_auth_method.setCurrentText(settings.api.oauth_client_auth_method)
        self.sso_credential_id = QLineEdit(settings.api.sso_credential_id)
        self.proxy_enabled = QCheckBox()
        self.proxy_enabled.setChecked(settings.proxy.enabled)
        self.http_proxy = QLineEdit(settings.proxy.http)
        self.https_proxy = QLineEdit(settings.proxy.https)
        self.proxy_username = QLineEdit(settings.proxy.username)
        self.proxy_password = QLineEdit(settings.proxy.password)
        self.proxy_password.setEchoMode(QLineEdit.Password)
        self.max_workers = QSpinBox()
        self.max_workers.setRange(1, 16)
        self.max_workers.setValue(settings.sync.max_workers)
        self.delete_sync = QCheckBox()
        self.delete_sync.setChecked(settings.sync.enable_delete_sync)
        self.encrypt = QCheckBox()
        self.encrypt.setChecked(settings.sync.enable_encryption)
        self.custom_ignore_rules = QTextEdit()
        self.custom_ignore_rules.setPlainText(settings.sync.custom_ignore_rules)
        self.custom_ignore_rules.setPlaceholderText("每行一条规则，例如 build/、*.bak、cache/**")
        self.custom_ignore_rules.setFixedHeight(96)
        self.encryption_passphrase = QLineEdit()
        self.encryption_passphrase.setEchoMode(QLineEdit.Password)
        self.encryption_passphrase.setPlaceholderText("留空表示不修改 keyring 中的口令")
        for label, widget in [
            ("运行模式", self.mode),
            ("主题", self.theme),
            ("API Base URL", self.base_url),
            ("API 前缀", self.api_prefix),
            ("Auth URL", self.auth_url),
            ("Client ID", self.client_id),
            ("Client Secret", self.client_secret),
            ("Redirect URI", self.redirect_uri),
            ("OAuth Scope", self.oauth_scope),
            ("OAuth 扩展参数", self.oauth_extra_params),
            ("Token 认证方式", self.oauth_auth_method),
            ("SSO Credential ID", self.sso_credential_id),
            ("启用代理", self.proxy_enabled),
            ("HTTP 代理", self.http_proxy),
            ("HTTPS 代理", self.https_proxy),
            ("代理用户名", self.proxy_username),
            ("代理密码", self.proxy_password),
            ("最大并发", self.max_workers),
            ("启用删除同步", self.delete_sync),
            ("启用加密上传", self.encrypt),
            ("自定义过滤规则", self.custom_ignore_rules),
            ("加密口令", self.encryption_passphrase),
        ]:
            form.addRow(label, widget)
        save = QPushButton("保存设置")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self.save)
        test_connection = QPushButton("测试连接")
        open_config = QPushButton("打开配置文件")
        open_data = QPushButton("打开数据目录")
        open_logs = QPushButton("打开日志目录")
        logout = QPushButton("退出登录")
        open_config.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_file()))))
        open_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir()))))
        open_logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        logout.clicked.connect(self.logout)
        test_connection.clicked.connect(self.test_connection)
        primary_actions = QHBoxLayout()
        primary_actions.addWidget(save)
        primary_actions.addWidget(test_connection)
        primary_actions.addStretch(1)
        file_actions = QHBoxLayout()
        file_actions.addWidget(open_config)
        file_actions.addWidget(open_data)
        file_actions.addWidget(open_logs)
        file_actions.addWidget(logout)
        file_actions.addStretch(1)
        content_layout.addLayout(form)
        content_layout.addLayout(primary_actions)
        content_layout.addLayout(file_actions)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(title)
        root.addWidget(scroll, 1)

    def save(self) -> bool:
        try:
            extra_oauth_params = json.loads(self.oauth_extra_params.text().strip() or "{}")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "OAuth 扩展参数错误", str(exc))
            return False
        if not isinstance(extra_oauth_params, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in extra_oauth_params.items()):
            QMessageBox.warning(self, "OAuth 扩展参数错误", "请填写字符串到字符串的 JSON 对象，例如 {\"tenant\":\"ncepu\"}。")
            return False
        self.settings.app.mode = self.mode.currentText()
        self.settings.app.theme = self.theme.currentText()
        self.settings.api.base_url = self.base_url.text().strip()
        self.settings.api.api_prefix = self.api_prefix.text().strip()
        self.settings.api.auth_url = self.auth_url.text().strip()
        self.settings.api.client_id = self.client_id.text().strip()
        self.settings.api.client_secret = self.client_secret.text()
        self.settings.api.redirect_uri = self.redirect_uri.text().strip()
        self.settings.api.oauth_scope = self.oauth_scope.text().strip()
        self.settings.api.extra_oauth_params = extra_oauth_params
        self.settings.api.oauth_client_auth_method = self.oauth_auth_method.currentText()
        self.settings.api.sso_credential_id = self.sso_credential_id.text().strip()
        self.settings.proxy.enabled = self.proxy_enabled.isChecked()
        self.settings.proxy.http = self.http_proxy.text().strip()
        self.settings.proxy.https = self.https_proxy.text().strip()
        self.settings.proxy.username = self.proxy_username.text().strip()
        self.settings.proxy.password = self.proxy_password.text()
        self.settings.sync.max_workers = self.max_workers.value()
        self.settings.sync.enable_delete_sync = self.delete_sync.isChecked()
        self.settings.sync.enable_encryption = self.encrypt.isChecked()
        self.settings.sync.custom_ignore_rules = self.custom_ignore_rules.toPlainText().strip()
        self.manager.save(self.settings)
        if self.encryption_passphrase.text():
            try:
                EncryptionKeyStore(self.settings.security).save_passphrase(self.encryption_passphrase.text())
            except Exception as exc:
                QMessageBox.warning(self, "加密口令未保存", str(exc))
                return False
        QMessageBox.information(self, "已保存", "配置已保存，部分设置重启后生效。")
        return True

    def logout(self) -> None:
        from ncepu_cloud_client.app.bootstrap import build_client

        try:
            build_client(self.settings).logout()
            QMessageBox.information(self, "已退出", "登录凭据已清除。")
        except Exception as exc:
            QMessageBox.warning(self, "退出失败", str(exc))

    def test_connection(self) -> None:
        if not self.save():
            return
        self.test_worker = TestConnectionWorker(self.settings)
        self.test_worker.ok.connect(lambda msg: QMessageBox.information(self, "测试连接", msg))
        self.test_worker.failed.connect(lambda msg: QMessageBox.warning(self, "测试连接失败", msg))
        self.test_worker.start()
