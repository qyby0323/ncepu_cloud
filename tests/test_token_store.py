from ncepu_cloud_client.api.models import TokenBundle
from ncepu_cloud_client.auth.token_store import TokenStore
import ncepu_cloud_client.auth.token_store as token_store_module


def test_token_store_drops_cookie_bundle_without_refresh_token(tmp_path, monkeypatch):
    monkeypatch.setattr(token_store_module, "keyring", None)
    path = tmp_path / "tokens.json"
    store = TokenStore(path=path)

    store.save(TokenBundle(access_token="sid=1; uid=2", token_type="Cookie"))

    assert store.load() is None
    assert not path.exists()
