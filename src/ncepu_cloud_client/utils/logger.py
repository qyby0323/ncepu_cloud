from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ncepu_cloud_client.app.paths import ensure_runtime_dirs, log_file

SENSITIVE_KEYS = (
    "access_token",
    "refresh_token",
    "client_secret",
    "password",
    "authorization",
    "token",
    "tokenid",
    "signature",
    "sign",
    "secret",
    "ticket",
    "code",
)

_KEY_PATTERN = r"access_token|refresh_token|client_secret|password|authorization|tokenid|token|signature|sign|secret|ticket|code"
_QUOTED_VALUE_RE = re.compile(
    rf"(?P<prefix>['\"]?(?:{_KEY_PATTERN})['\"]?\s*[:=]\s*['\"])(?P<value>[^'\"]*)(?P<suffix>['\"])",
    re.IGNORECASE,
)
_BARE_VALUE_RE = re.compile(
    rf"(?P<prefix>\b(?:access_token|refresh_token|client_secret|password|tokenid|token|signature|sign|secret|ticket|code)\b\s*[:=]\s*)(?P<value>[^\s,&}}]+)",
    re.IGNORECASE,
)
_AUTH_VALUE_RE = re.compile(
    r"(?P<prefix>\bauthorization\b\s*[:=]\s*)(?P<value>[^\n\r,]+)",
    re.IGNORECASE,
)


def mask_sensitive(text: str) -> str:
    masked = _QUOTED_VALUE_RE.sub(lambda match: f"{match.group('prefix')}***{match.group('suffix')}", text)
    masked = _AUTH_VALUE_RE.sub(lambda match: f"{match.group('prefix')}***", masked)
    return _BARE_VALUE_RE.sub(lambda match: f"{match.group('prefix')}***", masked)


def redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return mask_sensitive(url)
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "***:***@" + netloc.rsplit("@", 1)[1]
    query = urlencode(
        [
            (key, "***" if _is_sensitive_key(key) else value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ],
        doseq=True,
    )
    return mask_sensitive(urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment)))


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEYS)


def setup_logging() -> logging.Logger:
    ensure_runtime_dirs()
    logger = logging.getLogger("ncepu_cloud_client")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler = RotatingFileHandler(log_file(), maxBytes=5 * 1024 * 1024, backupCount=7, encoding="utf-8")
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)
    logger.addHandler(console)
    return logger


def get_logger(name: str) -> logging.Logger:
    return setup_logging().getChild(name)
