from __future__ import annotations


class CloudError(Exception):
    """Base cloud client error."""


class ConfigError(CloudError):
    """Configuration is missing or invalid."""


class AuthError(CloudError):
    """Authentication failed."""


class TokenExpiredError(AuthError):
    """Access token is expired and refresh failed."""


class PermissionDeniedError(CloudError):
    """Current user lacks permission."""


class NotFoundError(CloudError):
    """Cloud resource was not found."""


class ConflictError(CloudError):
    """Conflict detected."""


class RateLimitError(CloudError):
    """Server rejected request because of rate limiting."""


class NetworkError(CloudError):
    """Network, proxy or timeout error."""


class ServerError(CloudError):
    """Remote server error."""

