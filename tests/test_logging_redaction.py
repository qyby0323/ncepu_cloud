from ncepu_cloud_client.api.aishu_client import AishuCloudClient
from ncepu_cloud_client.utils.logger import mask_sensitive, redact_url


def test_redact_url_masks_credentials_and_sensitive_query_values():
    url = "https://user:pass@example.com/download?access_token=abc&file=report.pdf&signature=secret"

    redacted = redact_url(url)

    assert "user:pass" not in redacted
    assert "access_token=abc" not in redacted
    assert "signature=secret" not in redacted
    assert "file=report.pdf" in redacted
    assert "***:***@example.com" in redacted


def test_mask_sensitive_masks_json_form_and_header_values():
    text = '{"access_token": "tok-value", "client_secret": "shh-value"} password=pw-value Authorization: Bearer auth-value'

    masked = mask_sensitive(text)

    assert "tok-value" not in masked
    assert "shh-value" not in masked
    assert "pw-value" not in masked
    assert "Bearer auth-value" not in masked
    assert '"access_token": "***"' in masked
    assert "password=***" in masked
    assert "Authorization: ***" in masked


def test_aishu_error_message_masks_sensitive_response_text():
    class FakeResponse:
        status_code = 401
        text = '{"message": "access_token=tok-value client_secret=shh-value"}'

        def json(self):
            return {"code": "401004000", "message": "access_token=tok-value client_secret=shh-value"}

    message = AishuCloudClient._error_message(FakeResponse(), "/oauth2/token")

    assert "tok-value" not in message
    assert "shh-value" not in message
    assert "access_token=***" in message
    assert "client_secret=***" in message
