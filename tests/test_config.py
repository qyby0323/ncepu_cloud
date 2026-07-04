from ncepu_cloud_client.config.config_manager import ConfigManager
from ncepu_cloud_client.config.settings import Settings


def test_config_can_create_save_and_load(tmp_path):
    path = tmp_path / "config.toml"
    manager = ConfigManager(path)
    manager.save(Settings())
    loaded = manager.load()
    assert loaded.app.mode == "real"
    assert loaded.api.base_url == "https://pan.ncepu.edu.cn"
    assert loaded.api.auth_url == "https://pan.ncepu.edu.cn"
    loaded.app.mode = "mock"
    loaded.api.extra_oauth_params = {"tenant": "ncepu", "prompt": "none"}
    manager.save(loaded)
    assert manager.load().app.mode == "mock"
    assert manager.load().api.extra_oauth_params == {"tenant": "ncepu", "prompt": "none"}
    assert "custom_ignore_rules" not in path.read_text(encoding="utf-8")


def test_config_migrates_legacy_cloud_domain_to_pan(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[app]
mode = "real"
theme = "light"
language = "zh_CN"

[api]
base_url = "https://cloud.ncepu.edu.cn"
api_prefix = "/api"
auth_url = "https://cloud.ncepu.edu.cn"
client_id = ""
client_secret = ""
redirect_uri = "http://127.0.0.1:8765/callback"
oauth_scope = "offline openid all"
oauth_client_auth_method = "basic"
sso_credential_id = ""
timeout_seconds = 30
extra_oauth_params = {}

[proxy]
enabled = false
http = ""
https = ""
username = ""
password = ""

[sync]
max_workers = 4
default_conflict_policy = "keep_both"
enable_delete_sync = false
enable_encryption = false
custom_ignore_rules = ""

[security]
keyring_service = "NCEPUCloudClient"
""".strip(),
        encoding="utf-8",
    )

    loaded = ConfigManager(path).load()

    assert loaded.api.base_url == "https://pan.ncepu.edu.cn"
    assert loaded.api.auth_url == "https://pan.ncepu.edu.cn"
    assert "cloud.ncepu.edu.cn" not in path.read_text(encoding="utf-8")


def test_config_removes_legacy_prompt_login(tmp_path):
    path = tmp_path / "config.toml"
    settings = Settings()
    settings.api.extra_oauth_params = {"tenant": "ncepu", "prompt": "login"}
    ConfigManager(path).save(settings)

    loaded = ConfigManager(path).load()

    assert loaded.api.extra_oauth_params == {"tenant": "ncepu"}
    assert 'prompt = "login"' not in path.read_text(encoding="utf-8")
