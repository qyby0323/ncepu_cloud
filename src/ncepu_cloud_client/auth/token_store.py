from __future__ import annotations

import json
import time
from pathlib import Path

from ncepu_cloud_client.api.models import TokenBundle
from ncepu_cloud_client.app.paths import ensure_runtime_dirs, token_file
from ncepu_cloud_client.config.settings import SecuritySettings

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None


class TokenStore:
    """Store OAuth token data through keyring with file fallback."""

    def __init__(self, security: SecuritySettings | None = None, path: Path | None = None):
        self.security = security or SecuritySettings()
        self.path = path or token_file()
        self.account = "oauth-token"

    def save(self, bundle: TokenBundle) -> None:
        payload = json.dumps(bundle.__dict__, ensure_ascii=False)
        if keyring is not None:
            try:
                keyring.set_password(self.security.keyring_service, self.account, payload)
                return
            except Exception:
                pass
        ensure_runtime_dirs()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(payload, encoding="utf-8")

    def load(self) -> TokenBundle | None:
        payload: str | None = None
        if keyring is not None:
            try:
                payload = keyring.get_password(self.security.keyring_service, self.account)
            except Exception:
                payload = None
        if not payload and self.path.exists():
            payload = self.path.read_text(encoding="utf-8")
        if not payload:
            return None
        data = json.loads(payload)
        bundle = TokenBundle(**data)
        if bundle.token_type.lower() == "cookie" and not bundle.refresh_token:
            self.clear()
            return None
        return bundle

    def clear(self) -> None:
        if keyring is not None:
            try:
                keyring.delete_password(self.security.keyring_service, self.account)
            except Exception:
                pass
        if self.path.exists():
            self.path.unlink()

    def is_expired(self, skew_seconds: int = 60) -> bool:
        bundle = self.load()
        if bundle is None or not bundle.access_token:
            return True
        if bundle.expires_at is None:
            return False
        return bundle.expires_at <= time.time() + skew_seconds
