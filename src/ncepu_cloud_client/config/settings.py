from __future__ import annotations

from dataclasses import dataclass, field

from ncepu_cloud_client.app.constants import DEFAULT_AUTH_URL, DEFAULT_BASE_URL, DEFAULT_REDIRECT_URI


@dataclass
class AppSettings:
    mode: str = "real"
    theme: str = "light"
    language: str = "zh_CN"


@dataclass
class ApiSettings:
    base_url: str = DEFAULT_BASE_URL
    api_prefix: str = "/api"
    auth_url: str = DEFAULT_AUTH_URL
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = DEFAULT_REDIRECT_URI
    oauth_scope: str = "offline openid all"
    oauth_client_auth_method: str = "basic"
    sso_credential_id: str = ""
    timeout_seconds: int = 30
    extra_oauth_params: dict[str, str] = field(default_factory=dict)


@dataclass
class ProxySettings:
    enabled: bool = False
    http: str = ""
    https: str = ""
    username: str = ""
    password: str = ""


@dataclass
class SyncSettings:
    max_workers: int = 4
    default_conflict_policy: str = "keep_both"
    enable_delete_sync: bool = False
    enable_encryption: bool = False


@dataclass
class SecuritySettings:
    keyring_service: str = "NCEPUCloudClient"


@dataclass
class Settings:
    app: AppSettings = field(default_factory=AppSettings)
    api: ApiSettings = field(default_factory=ApiSettings)
    proxy: ProxySettings = field(default_factory=ProxySettings)
    sync: SyncSettings = field(default_factory=SyncSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
