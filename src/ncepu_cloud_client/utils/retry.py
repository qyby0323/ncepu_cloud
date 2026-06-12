from __future__ import annotations

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except Exception:  # pragma: no cover
    retry = None
    retry_if_exception_type = None
    stop_after_attempt = None
    wait_exponential = None


def network_retry():
    if retry is None:
        def decorator(func):
            return func
        return decorator
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )

