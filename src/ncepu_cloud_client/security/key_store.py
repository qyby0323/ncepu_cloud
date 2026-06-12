from __future__ import annotations

from ncepu_cloud_client.config.settings import SecuritySettings

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None


class EncryptionKeyStore:
    """Store encryption passphrase in OS keyring."""

    def __init__(self, security: SecuritySettings | None = None):
        self.security = security or SecuritySettings()
        self.account = "encryption-passphrase"

    def save_passphrase(self, passphrase: str) -> None:
        if keyring is None:
            raise RuntimeError("keyring 未安装，无法安全保存加密口令。")
        keyring.set_password(self.security.keyring_service, self.account, passphrase)

    def load_passphrase(self) -> str | None:
        if keyring is None:
            return None
        try:
            return keyring.get_password(self.security.keyring_service, self.account)
        except Exception:
            return None

