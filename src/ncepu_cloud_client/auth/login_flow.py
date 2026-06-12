from __future__ import annotations

import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ncepu_cloud_client.auth.oauth import build_authorize_url
from ncepu_cloud_client.config.settings import ApiSettings


OAUTH_CLIENT_HELP = (
    "未收到 OAuth 回调。若浏览器显示 invalid_client 或 /oauth2/fallbacks/error 404，"
    "说明当前 client_id/client_secret 没有通过认证；请先使用“动态注册 OAuth 客户端”，"
    "或填写学校开放平台/AnyShare 管理端发放的 client_id、client_secret 和 redirect_uri。"
    "程序会先打开 https://pan.ncepu.edu.cn 官方入口，再打开 OAuth 授权地址。"
    "若 OAuth 标签页仍停在 /oauth2/signin?login_challenge=... 白屏，请先在官方入口完成网页登录，"
    "然后刷新 OAuth 标签页并在浏览器授权页同意该客户端访问。"
)


class OAuthCallbackResult:
    def __init__(self) -> None:
        self.code: str | None = None
        self.error: str | None = None
        self.error_description: str | None = None

    @property
    def done(self) -> bool:
        return bool(self.code or self.error)


def wait_for_oauth_code(api: ApiSettings, timeout_seconds: int = 180) -> str:
    state = secrets.token_urlsafe(16)
    parsed = urlparse(api.redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    result = OAuthCallbackResult()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [""])[0] != state:
                result.error = "OAuth state mismatch"
            else:
                result.code = query.get("code", [None])[0]
                result.error = query.get("error", [None])[0]
                result.error_description = query.get("error_description", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("登录完成，可以关闭此窗口。".encode("utf-8"))

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer((host, port), Handler)
    server.timeout = 1
    try:
        open_login_pages(api, state)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and not result.done:
            server.handle_request()
    finally:
        server.server_close()
    if result.error:
        if result.error == "invalid_client":
            raise RuntimeError(f"OAuth invalid_client：{OAUTH_CLIENT_HELP}")
        if result.error == "consent_required":
            raise RuntimeError(
                "OAuth consent_required：服务器要求先完成一次用户授权同意。"
                "请删除登录设置里的 {\"prompt\":\"none\"}，重新登录并在浏览器授权页同意该客户端访问。"
                f"{' 原始说明：' + result.error_description if result.error_description else ''}"
            )
        if result.error == "login_required":
            raise RuntimeError(
                "OAuth login_required：浏览器网页登录态未被授权端点识别。"
                "请先在 https://pan.ncepu.edu.cn 完成网页登录，关闭白屏 OAuth 标签页后重新点击登录。"
                f"{' 原始说明：' + result.error_description if result.error_description else ''}"
            )
        detail = f": {result.error_description}" if result.error_description else ""
        raise RuntimeError(f"{result.error}{detail}")
    if not result.code:
        raise TimeoutError(OAUTH_CLIENT_HELP)
    return result.code


def open_login_pages(api: ApiSettings, state: str) -> None:
    entry_url = official_entry_url(api)
    authorize_url = build_authorize_url(api, state)
    if entry_url:
        webbrowser.open(entry_url)
    webbrowser.open(authorize_url)


def official_entry_url(api: ApiSettings) -> str:
    return (api.base_url or api.auth_url).rstrip("/")
