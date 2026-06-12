from __future__ import annotations

import json
import re
import secrets
import webbrowser
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qs, urlparse

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.api.models import TokenBundle
from ncepu_cloud_client.auth.login_flow import official_entry_url
from ncepu_cloud_client.auth.oauth import build_authorize_url
from ncepu_cloud_client.auth.token_store import TokenStore
from ncepu_cloud_client.config.config_manager import ConfigManager
from ncepu_cloud_client.config.settings import Settings

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover - optional PySide6 module
    QWebEngineView = None

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor
except Exception:  # pragma: no cover - optional PySide6 module
    QWebEnginePage = None
    QWebEngineUrlRequestInterceptor = None


class LoginWorker(QThread):
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient):
        super().__init__()
        self.client = client

    def run(self) -> None:
        try:
            self.client.login()
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class ExchangeCodeWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, code: str):
        super().__init__()
        self.client = client
        self.code = code

    def run(self) -> None:
        try:
            if not hasattr(self.client, "exchange_code"):
                raise RuntimeError("当前 adapter 不支持 OAuth code 换取 token。")
            bundle = self.client.exchange_code(self.code)
            self.client.list_libraries()
            self.client.get_quota()
            self.finished_ok.emit(bundle)
        except Exception as exc:
            self.failed.emit(str(exc))


class RegisterClientWorker(QThread):
    registered = Signal(dict)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, name: str):
        super().__init__()
        self.client = client
        self.name = name

    def run(self) -> None:
        try:
            if not hasattr(self.client, "register_oauth_client"):
                raise RuntimeError("当前 adapter 不支持 OAuth 动态注册。")
            self.registered.emit(self.client.register_oauth_client(self.name))
        except Exception as exc:
            self.failed.emit(str(exc))


class SsoLoginWorker(QThread):
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, params: dict):
        super().__init__()
        self.client = client
        self.params = params

    def run(self) -> None:
        try:
            if not hasattr(self.client, "login_sso"):
                raise RuntimeError("当前 adapter 不支持 SSO。")
            self.client.login_sso(self.params)
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class TokenRequestInterceptor(QWebEngineUrlRequestInterceptor if QWebEngineUrlRequestInterceptor else object):
    token_seen = Signal(str)

    def __init__(self) -> None:
        super().__init__()

    def interceptRequest(self, info) -> None:  # noqa: N802
        candidates: list[str] = []
        try:
            candidates.append(info.requestUrl().toString())
        except Exception:
            pass
        try:
            headers = info.httpHeaders()
            for key, value in headers.items():
                key_text = bytes(key).decode("utf-8", errors="ignore")
                value_text = bytes(value).decode("utf-8", errors="ignore")
                candidates.append(f"{key_text}: {value_text}")
        except Exception:
            pass
        for candidate in candidates:
            if any(name in candidate for name in ("access_token", "accessToken", "accessTokenId", "tokenid", "Authorization: Bearer", "authorization: Bearer")):
                self.token_seen.emit(candidate)
                return


class OAuthWebPage(QWebEnginePage if QWebEnginePage else object):
    def __init__(self, dialog: "EmbeddedLoginDialog"):
        super().__init__(dialog)
        self.dialog = dialog

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # noqa: N802
        if is_main_frame and self.dialog._handle_oauth_callback(url.toString()):
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class EmbeddedLoginDialog(QDialog):
    """Official web login with automatic token discovery."""

    def __init__(self, parent: "LoginWindow"):
        super().__init__(parent)
        if QWebEngineView is None:
            raise RuntimeError("当前环境缺少 PySide6.QtWebEngineWidgets，无法使用内置网页登录。")
        self.login_window = parent
        self.bundle: TokenBundle | None = None
        self.cookies: dict[str, str] = {}
        self.rejected_tokens: set[str] = set()
        self.oauth_started = False
        self.exchange_started = False
        self.oauth_state = secrets.token_urlsafe(16)
        self.setWindowTitle("华电网盘网页登录")
        self.resize(1040, 720)

        root = QVBoxLayout(self)
        self.status = QLabel("请在内置网页中完成登录，客户端会自动检测登录状态。")
        self.status.setObjectName("MutedText")
        self.web_view = QWebEngineView()
        if QWebEnginePage is not None:
            self.web_view.setPage(OAuthWebPage(self))
        self.web_view.loadFinished.connect(lambda _ok: self.scan_for_token())
        self.web_view.urlChanged.connect(self._url_changed)
        self._setup_web_profile()

        close_button = QPushButton("取消")
        close_button.clicked.connect(self.reject)
        footer = QHBoxLayout()
        footer.addWidget(self.status)
        footer.addStretch(1)
        footer.addWidget(close_button)

        root.addWidget(self.web_view)
        root.addLayout(footer)

        self.timer = QTimer(self)
        self.timer.setInterval(1200)
        self.timer.timeout.connect(self.scan_for_token)
        self.timer.start()
        self.web_view.setUrl(QUrl(official_entry_url(parent.settings.api)))

    def _setup_web_profile(self) -> None:
        page = self.web_view.page()
        profile = page.profile()
        if QWebEngineUrlRequestInterceptor is not None:
            self.interceptor = TokenRequestInterceptor()
            self.interceptor.token_seen.connect(self._candidate_token_seen)
            profile.setUrlRequestInterceptor(self.interceptor)
        try:
            profile.cookieStore().cookieAdded.connect(self._cookie_added)
        except Exception:
            pass

    def _candidate_token_seen(self, text: str) -> None:
        if self._handle_oauth_callback(text):
            return
        if not self._is_callback_url(self.web_view.url().toString()):
            return
        bundle = self.login_window._token_bundle_from_text(text)
        if bundle:
            self._accept_bundle(bundle)

    def _cookie_added(self, cookie) -> None:
        try:
            name = bytes(cookie.name()).decode("utf-8", errors="ignore")
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
        except Exception:
            return
        if name and value:
            self.cookies[name] = value

    def scan_for_token(self) -> None:
        self._url_changed(self.web_view.url())
        script = """
(() => {
  const objectFromStorage = (storage) => {
    const result = {};
    try {
      for (let i = 0; i < storage.length; i += 1) {
        const key = storage.key(i);
        result[key] = storage.getItem(key);
      }
    } catch (error) {
      result.__error = String(error);
    }
    return result;
  };
  return JSON.stringify({
    href: location.href,
    search: location.search,
    hash: location.hash,
    cookie: (() => { try { return document.cookie; } catch (error) { return String(error); } })(),
    localStorage: objectFromStorage(window.localStorage),
    sessionStorage: objectFromStorage(window.sessionStorage),
    bodyText: (() => { try { return document.body ? document.body.innerText.slice(0, 4000) : ""; } catch (error) { return ""; } })()
  });
})()
"""
        self.web_view.page().runJavaScript(script, self._token_scan_finished)
        self.scan_indexed_db()

    def scan_indexed_db(self) -> None:
        script = """
(async () => {
  const result = {};
  if (!window.indexedDB || !indexedDB.databases) {
    return JSON.stringify(result);
  }
  const dbs = await indexedDB.databases();
  for (const dbInfo of dbs.slice(0, 8)) {
    if (!dbInfo.name) continue;
    result[dbInfo.name] = {};
    await new Promise((resolve) => {
      const req = indexedDB.open(dbInfo.name);
      req.onerror = () => resolve();
      req.onsuccess = () => {
        const db = req.result;
        const stores = Array.from(db.objectStoreNames).slice(0, 12);
        if (stores.length === 0) {
          db.close();
          resolve();
          return;
        }
        const tx = db.transaction(stores, "readonly");
        let pending = stores.length;
        const done = () => {
          pending -= 1;
          if (pending <= 0) {
            db.close();
            resolve();
          }
        };
        for (const storeName of stores) {
          const store = tx.objectStore(storeName);
          const getAll = store.getAll();
          getAll.onerror = done;
          getAll.onsuccess = () => {
            result[dbInfo.name][storeName] = getAll.result.slice(0, 20);
            done();
          };
        }
      };
    });
  }
  return JSON.stringify(result);
})()
"""
        self.web_view.page().runJavaScript(script, self._token_scan_finished)

    def _token_scan_finished(self, payload: str) -> None:
        if self.oauth_started:
            return
        if self._looks_like_logged_in_page(payload or ""):
            self.start_oauth_authorization()

    def _url_changed(self, url: QUrl) -> None:
        url_text = url.toString()
        if self._handle_oauth_callback(url_text):
            return
        if self.oauth_started:
            return

    def _looks_like_logged_in_page(self, payload: str) -> bool:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False
        href = str(data.get("href") or "").lower()
        body = str(data.get("bodyText") or "")
        if "oauth2/signin" in href or "login_challenge" in href:
            return False
        markers = ("资源库", "工作中心", "文件锁管理", "共享管理", "回收站", "文件隔离区")
        return sum(1 for marker in markers if marker in body) >= 2

    def start_oauth_authorization(self) -> None:
        if self.oauth_started:
            return
        self.oauth_started = True
        self.status.setText("网页登录成功，正在获取 REST API 授权...")
        self.web_view.setUrl(QUrl(build_authorize_url(self.login_window.settings.api, self.oauth_state)))

    def _handle_oauth_callback(self, url: str) -> bool:
        if not self._is_callback_url(url):
            return False
        parsed = urlparse(url)
        params = parse_qs(parsed.query or parsed.fragment)
        if params.get("state", [""])[0] != self.oauth_state:
            return True
        error = params.get("error", [""])[0]
        if error:
            description = params.get("error_description", [""])[0]
            self.status.setText(f"OAuth 授权失败：{error} {description}".strip())
            self.oauth_started = False
            return True
        access_bundle = self.login_window._token_bundle_from_text(url)
        if access_bundle:
            self._accept_bundle(access_bundle)
            return True
        code = params.get("code", [""])[0]
        if code:
            self.exchange_oauth_code(code)
        return True

    def _is_callback_url(self, url: str) -> bool:
        return url.startswith(self.login_window.settings.api.redirect_uri)

    def exchange_oauth_code(self, code: str) -> None:
        if self.exchange_started:
            return
        self.exchange_started = True
        self.status.setText("已取得授权码，正在换取 access token...")
        self.exchange_worker = ExchangeCodeWorker(self.login_window.client, code)
        self.exchange_worker.finished_ok.connect(self._exchange_finished)
        self.exchange_worker.failed.connect(self._exchange_failed)
        self.exchange_worker.start()

    def _exchange_finished(self, bundle: TokenBundle) -> None:
        self.bundle = bundle
        self.timer.stop()
        self.status.setText("网页登录验证通过，正在进入主程序...")
        self.accept()

    def _exchange_failed(self, message: str) -> None:
        self.exchange_started = False
        self.oauth_started = False
        TokenStore(self.login_window.settings.security).clear()
        self.status.setText(f"REST API 授权失败：{message}")
        QMessageBox.warning(self, "REST API 授权失败", message)

    def _accept_bundle(self, bundle: TokenBundle) -> None:
        if self.bundle:
            return
        if bundle.access_token in self.rejected_tokens:
            return
        self.status.setText("已检测到登录凭据，正在验证...")
        if not self.login_window.validate_and_store_token_bundle(bundle):
            self.rejected_tokens.add(bundle.access_token)
            self.status.setText("检测到的网页登录凭据无效，继续等待登录完成...")
            return
        self.bundle = bundle
        self.timer.stop()
        self.status.setText("网页登录验证通过，正在进入主程序...")
        self.accept()


class LoginSettingsDialog(QDialog):
    """Advanced login settings kept out of the primary login surface."""

    def __init__(self, parent: "LoginWindow"):
        super().__init__(parent)
        self.login_window = parent
        settings = parent.settings
        self.setWindowTitle("登录设置")
        self.resize(560, 560)

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.api_base_url = QLineEdit(settings.api.base_url)
        self.api_prefix = QLineEdit(settings.api.api_prefix)
        self.auth_url = QLineEdit(settings.api.auth_url)
        self.redirect_uri = QLineEdit(settings.api.redirect_uri)
        self.oauth_scope = QLineEdit(settings.api.oauth_scope)
        self.oauth_extra_params = QLineEdit(json.dumps(settings.api.extra_oauth_params, ensure_ascii=False))
        self.oauth_extra_params.setPlaceholderText('可选，例如 {"tenant":"ncepu"}')
        self.oauth_auth_method = QComboBox()
        self.oauth_auth_method.addItems(["basic", "body"])
        self.oauth_auth_method.setCurrentText(settings.api.oauth_client_auth_method)
        self.sso_credential_id = QLineEdit(settings.api.sso_credential_id)
        self.sso_params = QLineEdit()
        self.sso_params.setPlaceholderText('例如 {"account":"..."}')
        self.proxy_enabled = QCheckBox()
        self.proxy_enabled.setChecked(settings.proxy.enabled)
        self.http_proxy = QLineEdit(settings.proxy.http)
        self.https_proxy = QLineEdit(settings.proxy.https)
        self.manual_access_token = QLineEdit()
        self.manual_access_token.setEchoMode(QLineEdit.Password)
        self.manual_access_token.setPlaceholderText("可粘贴 access_token、Bearer 头、JSON 或回调 URL")
        self.manual_refresh_token = QLineEdit()
        self.manual_refresh_token.setEchoMode(QLineEdit.Password)
        self.manual_refresh_token.setPlaceholderText("可选 refresh_token")

        for label, widget in [
            ("业务 API 地址", self.api_base_url),
            ("API 前缀", self.api_prefix),
            ("认证地址", self.auth_url),
            ("Redirect URI", self.redirect_uri),
            ("OAuth Scope", self.oauth_scope),
            ("OAuth 扩展参数", self.oauth_extra_params),
            ("Token 认证方式", self.oauth_auth_method),
            ("SSO Credential ID", self.sso_credential_id),
            ("SSO Params JSON", self.sso_params),
            ("启用代理", self.proxy_enabled),
            ("HTTP 代理", self.http_proxy),
            ("HTTPS 代理", self.https_proxy),
            ("Access Token", self.manual_access_token),
            ("Refresh Token", self.manual_refresh_token),
        ]:
            form.addRow(label, widget)

        save_button = QPushButton("保存登录设置")
        save_button.setObjectName("PrimaryButton")
        oauth_button = QPushButton("OAuth 授权登录")
        register_button = QPushButton("动态注册 OAuth 客户端")
        sso_button = QPushButton("SSO 登录")
        token_button = QPushButton("使用 Token 进入")
        close_button = QPushButton("关闭")

        save_button.clicked.connect(self.save)
        oauth_button.clicked.connect(self.login_oauth)
        register_button.clicked.connect(self.register_client)
        sso_button.clicked.connect(self.login_sso)
        token_button.clicked.connect(self.login_with_token)
        close_button.clicked.connect(self.accept)

        action_row = QHBoxLayout()
        action_row.addWidget(save_button)
        action_row.addWidget(oauth_button)
        action_row.addWidget(register_button)
        action_row.addStretch(1)
        secondary_row = QHBoxLayout()
        secondary_row.addWidget(sso_button)
        secondary_row.addWidget(token_button)
        secondary_row.addWidget(close_button)
        secondary_row.addStretch(1)

        root.addLayout(form)
        root.addLayout(action_row)
        root.addLayout(secondary_row)

    def apply_settings(self) -> bool:
        return self.login_window.apply_login_settings(self)

    def save(self) -> None:
        if not self.apply_settings():
            return
        self.login_window.persist_settings(self.login_window.save_password.isChecked())
        QMessageBox.information(self, "已保存", "登录设置已保存。")

    def register_client(self) -> None:
        if self.apply_settings():
            self.login_window.register_client()

    def login_oauth(self) -> None:
        if self.apply_settings():
            self.login_window.login_oauth()

    def login_sso(self) -> None:
        if not self.apply_settings():
            return
        try:
            params = json.loads(self.sso_params.text().strip() or "{}")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "SSO 参数错误", str(exc))
            return
        self.login_window.login_sso(params)

    def login_with_token(self) -> None:
        if not self.apply_settings():
            return
        self.login_window.login_with_token(
            self.manual_access_token.text().strip(),
            self.manual_refresh_token.text().strip(),
        )


class LoginWindow(QDialog):
    def __init__(self, settings: Settings, client: CloudDriveClient):
        super().__init__()
        self.settings = settings
        self.client = client
        self.settings_dialog: LoginSettingsDialog | None = None
        self._auth_url_overridden = bool(settings.api.auth_url and settings.api.auth_url != settings.api.base_url)

        self.setWindowTitle("华电云盘客户端")
        self.resize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        top_row = QHBoxLayout()
        brand = QLabel("华电云盘客户端")
        brand.setObjectName("AppTitle")
        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("SettingsButton")
        self.settings_button.clicked.connect(self.open_login_settings)
        top_row.addWidget(brand)
        top_row.addStretch(1)
        top_row.addWidget(self.settings_button)

        hero = QFrame()
        hero.setObjectName("LoginPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(14)

        title = QLabel("登录")
        title.setObjectName("LoginTitle")
        subtitle = QLabel("REAL 模式连接真实华电云盘；MOCK 模式用于离线演示和测试。")
        subtitle.setObjectName("MutedText")

        self.real_panel = QWidget()
        real_form = QFormLayout(self.real_panel)
        real_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.cloud_url = QLineEdit(settings.api.base_url)
        self.cloud_url.setPlaceholderText("https://pan.ncepu.edu.cn")
        self.client_id = QLineEdit(settings.api.client_id)
        self.client_secret = QLineEdit(settings.api.client_secret)
        self.client_secret.setEchoMode(QLineEdit.Password)
        self.save_password = QCheckBox("保存密码")
        self.save_password.setChecked(bool(settings.api.client_secret))
        real_form.addRow("云盘地址", self.cloud_url)
        real_form.addRow("Client ID", self.client_id)
        real_form.addRow("Client Secret", self.client_secret)
        real_form.addRow("", self.save_password)

        self.mock_panel = QWidget()
        mock_layout = QVBoxLayout(self.mock_panel)
        mock_layout.setContentsMargins(0, 0, 0, 0)
        mock_title = QLabel("MOCK 演示模式")
        mock_title.setObjectName("CardTitle")
        mock_text = QLabel("无需账号和网络，使用内存中的示例云盘数据进入主界面。")
        mock_text.setObjectName("MutedText")
        mock_layout.addWidget(mock_title)
        mock_layout.addWidget(mock_text)
        mock_layout.addStretch(1)

        self.primary_button = QPushButton("登录真实华电云盘")
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.clicked.connect(self.login_current_mode)

        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        hero_layout.addSpacing(12)
        hero_layout.addWidget(self.real_panel)
        hero_layout.addWidget(self.mock_panel)
        hero_layout.addSpacing(8)
        hero_layout.addWidget(self.primary_button)

        footer = QHBoxLayout()
        self.real_mode_button = QPushButton("REAL")
        self.mock_mode_button = QPushButton("MOCK")
        for button in (self.real_mode_button, self.mock_mode_button):
            button.setCheckable(True)
            button.setObjectName("ModeButton")
        self.real_mode_button.clicked.connect(lambda: self.set_mode("real"))
        self.mock_mode_button.clicked.connect(lambda: self.set_mode("mock"))
        footer.addWidget(self.real_mode_button)
        footer.addWidget(self.mock_mode_button)
        footer.addStretch(1)

        root.addLayout(top_row)
        root.addStretch(1)
        root.addWidget(hero)
        root.addStretch(1)
        root.addLayout(footer)

        self.set_mode(settings.app.mode if settings.app.mode in {"real", "mock"} else "real")

    def set_mode(self, mode: str) -> None:
        self.settings.app.mode = "mock" if mode == "mock" else "real"
        is_real = self.settings.app.mode == "real"
        self.real_mode_button.setChecked(is_real)
        self.mock_mode_button.setChecked(not is_real)
        self.real_panel.setVisible(is_real)
        self.mock_panel.setVisible(not is_real)
        self.primary_button.setText("登录真实华电云盘" if is_real else "进入 MOCK 模式")

    def login_current_mode(self) -> None:
        if self.settings.app.mode == "mock":
            self.enter_mock()
        else:
            self.login_with_embedded_browser()

    def open_login_settings(self) -> None:
        self.apply_main_fields(require_credentials=False)
        self.settings_dialog = LoginSettingsDialog(self)
        self.settings_dialog.exec()

    def apply_main_fields(self, require_credentials: bool) -> bool:
        url = self.cloud_url.text().strip().rstrip("/")
        client_id = self.client_id.text().strip()
        client_secret = self.client_secret.text()
        if self.settings.app.mode == "real":
            if not url:
                QMessageBox.warning(self, "缺少云盘地址", "请填写云盘地址。")
                return False
            if require_credentials and (not client_id or not client_secret):
                QMessageBox.warning(self, "缺少 OAuth 客户端", "请填写 Client ID 和 Client Secret，或进入登录设置动态注册。")
                return False
        if url:
            self.settings.api.base_url = url
            if not self._auth_url_overridden:
                self.settings.api.auth_url = url
        self.settings.api.client_id = client_id
        self.settings.api.client_secret = client_secret
        return True

    def apply_login_settings(self, dialog: LoginSettingsDialog) -> bool:
        if not self.apply_main_fields(require_credentials=False):
            return False
        extra_oauth_params = self._parse_string_dict(dialog.oauth_extra_params.text().strip(), "OAuth 扩展参数")
        if extra_oauth_params is None:
            return False
        self.settings.api.base_url = dialog.api_base_url.text().strip().rstrip("/") or self.settings.api.base_url
        self.settings.api.api_prefix = dialog.api_prefix.text().strip()
        self.settings.api.auth_url = dialog.auth_url.text().strip().rstrip("/") or self.settings.api.base_url
        self.settings.api.redirect_uri = dialog.redirect_uri.text().strip()
        self.settings.api.oauth_scope = dialog.oauth_scope.text().strip()
        self.settings.api.extra_oauth_params = extra_oauth_params
        self.settings.api.oauth_client_auth_method = dialog.oauth_auth_method.currentText()
        self.settings.api.sso_credential_id = dialog.sso_credential_id.text().strip()
        self.settings.proxy.enabled = dialog.proxy_enabled.isChecked()
        self.settings.proxy.http = dialog.http_proxy.text().strip()
        self.settings.proxy.https = dialog.https_proxy.text().strip()
        self._auth_url_overridden = self.settings.api.auth_url != self.settings.api.base_url
        self.cloud_url.setText(self.settings.api.base_url)
        return True

    def persist_settings(self, save_secret: bool) -> None:
        persisted = deepcopy(self.settings)
        if not save_secret:
            persisted.api.client_secret = ""
        ConfigManager().save(persisted)

    def login_with_embedded_browser(self) -> None:
        if not self.apply_main_fields(require_credentials=True):
            return
        self.settings.app.mode = "real"
        self.persist_settings(self.save_password.isChecked())
        try:
            dialog = EmbeddedLoginDialog(self)
        except RuntimeError as exc:
            QMessageBox.warning(self, "内置网页登录不可用", f"{exc}\n请安装 PySide6-WebEngine 后重试。")
            webbrowser.open(official_entry_url(self.settings.api))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.bundle:
            self.settings.app.mode = "real"
            self.persist_settings(self.save_password.isChecked())
            self.accept()

    def login_oauth(self) -> None:
        if not self.apply_main_fields(require_credentials=True):
            return
        self.persist_settings(self.save_password.isChecked())
        self.primary_button.setEnabled(False)
        self.primary_button.setText("等待浏览器授权...")
        self.worker = LoginWorker(self.client)
        self.worker.finished_ok.connect(self.accept)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def enter_mock(self) -> None:
        self.settings.app.mode = "mock"
        self.persist_settings(self.save_password.isChecked())
        self.accept()

    def login_with_token(self, access_token: str, refresh_token: str = "") -> None:
        bundle = self._token_bundle_from_text(access_token, refresh_token)
        if not bundle:
            QMessageBox.warning(self, "缺少 token", "请在登录设置中粘贴 access_token。")
            return
        if not self.validate_and_store_token_bundle(bundle):
            QMessageBox.warning(self, "登录凭据无效", "检测到的 token 无法访问云端文件，请重新登录。")
            return
        if self.settings_dialog:
            self.settings_dialog.accept()
        self.accept()

    def validate_and_store_token_bundle(self, bundle: TokenBundle) -> bool:
        self.settings.app.mode = "real"
        token_store = TokenStore(self.settings.security)
        token_store.save(bundle)
        try:
            self.client.list_libraries()
            self.client.get_quota()
        except Exception:
            token_store.clear()
            return False
        self.persist_settings(self.save_password.isChecked())
        return True

    @staticmethod
    def _token_bundle_from_text(access_text: str, refresh_text: str = "") -> TokenBundle | None:
        access_text = access_text.strip()
        refresh_text = refresh_text.strip()
        if not access_text:
            return None
        token_data = LoginWindow._parse_token_text(access_text)
        access_token = (
            token_data.get("access_token")
            or token_data.get("accessToken")
            or token_data.get("access_token_id")
            or token_data.get("accessTokenId")
            or token_data.get("tokenid")
            or token_data.get("tokenId")
        )
        refresh_token = (
            refresh_text
            or token_data.get("refresh_token")
            or token_data.get("refreshToken")
            or token_data.get("refreshtoken")
            or ""
        )
        token_type = token_data.get("token_type") or token_data.get("tokenType") or token_data.get("tokentype") or "Bearer"
        if not access_token:
            return None
        return TokenBundle(access_token=str(access_token), refresh_token=str(refresh_token), token_type=str(token_type))

    @staticmethod
    def _parse_token_text(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.lower().startswith("authorization:"):
            stripped = stripped.split(":", 1)[1].strip()
        if stripped.lower().startswith("cookie:"):
            stripped = stripped.split(":", 1)[1].strip()
            return {"access_token": stripped, "token_type": "Cookie"}
        if stripped.lower().startswith("bearer "):
            return {"access_token": stripped.split(None, 1)[1].strip(), "token_type": "Bearer"}
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict):
                    return LoginWindow._find_token_data(data)
            except json.JSONDecodeError:
                pass
        if any(key in stripped for key in ("access_token=", "accessToken=", "access_token_id=", "accessTokenId=", "tokenid=")):
            parsed = urlparse(stripped)
            query = parsed.query or parsed.fragment or stripped
            query = "&".join(part.strip() for part in query.replace(";", "&").split("&"))
            values = parse_qs(query, keep_blank_values=True)
            return {key: value[-1] for key, value in values.items() if value}
        match = re.search(r'"?(access_token|accessToken|access_token_id|accessTokenId|tokenid|tokenId)"?\s*[:=]\s*"?([^",\s]+)', stripped)
        if match:
            return {match.group(1): match.group(2)}
        if LoginWindow._looks_like_token(stripped):
            return {"access_token": stripped}
        return {}

    @staticmethod
    def _looks_like_token(value: str) -> bool:
        if len(value) < 20 or any(ch.isspace() for ch in value):
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9._~+/=-]+", value))

    @staticmethod
    def _find_token_data(value: Any) -> dict[str, Any]:
        token_keys = ("access_token", "accessToken", "access_token_id", "accessTokenId", "tokenid", "tokenId")
        if isinstance(value, str):
            lowered = value.lower().strip()
            if lowered.startswith("authorization:") or lowered.startswith("bearer ") or any(f"{key}=" in value or f'"{key}"' in value for key in token_keys):
                parsed = LoginWindow._parse_token_text(value)
                if any(key in parsed for key in token_keys):
                    return parsed
            try:
                nested = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return LoginWindow._find_token_data(nested)
        if isinstance(value, list):
            for item in value:
                found = LoginWindow._find_token_data(item)
                if found:
                    return found
            return {}
        if not isinstance(value, dict):
            return {}
        if any(key in value for key in token_keys):
            return value
        for item in value.values():
            found = LoginWindow._find_token_data(item)
            if found:
                return found
        return {}

    def register_client(self) -> None:
        self.persist_settings(self.save_password.isChecked())
        self.register_worker = RegisterClientWorker(self.client, "NCEPU Cloud Client")
        self.register_worker.registered.connect(self._registered)
        self.register_worker.failed.connect(self._register_failed)
        self.register_worker.start()

    def login_sso(self, params: dict) -> None:
        self.settings.app.mode = "real"
        self.persist_settings(self.save_password.isChecked())
        self.sso_worker = SsoLoginWorker(self.client, params)
        self.sso_worker.finished_ok.connect(self.accept)
        self.sso_worker.failed.connect(self._sso_failed)
        self.sso_worker.start()

    def _registered(self, result: dict) -> None:
        client_id = result.get("client_id") or result.get("clientId") or ""
        client_secret = result.get("client_secret") or result.get("clientSecret") or ""
        if client_id:
            self.client_id.setText(client_id)
            self.settings.api.client_id = client_id
        if client_secret:
            self.client_secret.setText(client_secret)
            self.settings.api.client_secret = client_secret
            self.save_password.setChecked(True)
        self.persist_settings(self.save_password.isChecked())
        QMessageBox.information(self, "动态注册完成", f"client_id: {client_id}\nclient_secret: {client_secret}\n\n请妥善保存 secret。")

    def _register_failed(self, message: str) -> None:
        QMessageBox.warning(self, "动态注册失败", message)

    def _sso_failed(self, message: str) -> None:
        QMessageBox.warning(self, "SSO 登录失败", message)

    def _failed(self, message: str) -> None:
        self.primary_button.setEnabled(True)
        self.primary_button.setText("登录真实华电云盘")
        QMessageBox.warning(self, "登录失败", message)

    def _parse_string_dict(self, text: str, title: str) -> dict[str, str] | None:
        try:
            value: Any = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, f"{title}错误", str(exc))
            return None
        if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            QMessageBox.warning(self, f"{title}错误", f"请填写字符串到字符串的 JSON 对象，例如 {{\"tenant\":\"ncepu\"}}。")
            return None
        return value
