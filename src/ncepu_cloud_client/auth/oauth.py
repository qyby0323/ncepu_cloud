from __future__ import annotations

from urllib.parse import urlencode

from ncepu_cloud_client.config.settings import ApiSettings


def build_authorize_url(api: ApiSettings, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": api.client_id,
        "redirect_uri": api.redirect_uri,
        "scope": api.oauth_scope,
        "state": state,
    }
    params.update(api.extra_oauth_params)
    return f"{api.auth_url.rstrip('/')}/oauth2/auth?{urlencode(params)}"
