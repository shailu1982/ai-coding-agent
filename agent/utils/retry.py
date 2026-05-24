import os
import time
import anthropic

_RETRIABLE_ANTHROPIC = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)

_RETRIABLE_GITHUB_STATUSES = {429, 500, 502, 503, 504}


def _config() -> tuple:
    """Return (max_attempts, base_delay) from env."""
    return (
        int(os.getenv("MAX_API_RETRIES", "3")),
        float(os.getenv("API_RETRY_DELAY", "2.0")),
    )


def _log(msg: str):
    print(f"  ⟳ {msg}")


# ─────────────────────────────────────────────────────
# Anthropic retry wrapper
# ─────────────────────────────────────────────────────

class _RetryingMessages:
    """Wraps anthropic.resources.Messages.create with exponential backoff."""

    def __init__(self, messages, max_attempts: int, base_delay: float):
        self._messages = messages
        self._max = max_attempts
        self._delay = base_delay

    def create(self, **kwargs):
        last_exc = None
        for attempt in range(1, self._max + 1):
            try:
                return self._messages.create(**kwargs)
            except _RETRIABLE_ANTHROPIC as exc:
                last_exc = exc
                if attempt < self._max:
                    delay = self._delay * (2 ** (attempt - 1))
                    _log(
                        f"Anthropic {type(exc).__name__} — "
                        f"attempt {attempt}/{self._max}, retrying in {delay:.0f}s"
                    )
                    time.sleep(delay)
        raise last_exc


class RetryingClient:
    """
    Drop-in replacement for anthropic.Anthropic that automatically retries
    transient errors (rate limits, server errors, connection failures) with
    exponential backoff.

    Reads MAX_API_RETRIES (default 3) and API_RETRY_DELAY (default 2.0s) from env.
    """

    def __init__(self, api_key: str):
        max_attempts, base_delay = _config()
        self._client = anthropic.Anthropic(api_key=api_key)
        self.messages = _RetryingMessages(self._client.messages, max_attempts, base_delay)


# ─────────────────────────────────────────────────────
# GitHub retry wrapper
# ─────────────────────────────────────────────────────

def with_github_retry(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) and retry on transient GitHub errors
    (429, 500, 502, 503, 504) or network failures, with exponential backoff.

    Reads MAX_API_RETRIES and API_RETRY_DELAY from env.
    Honours the Retry-After header when present.

    Usage:
        issue = with_github_retry(repo.get_issue, number=42)
        pr    = with_github_retry(repo.create_pull, title=..., body=..., ...)
    """
    import github as _gh

    max_attempts, base_delay = _config()
    last_exc = None

    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except _gh.GithubException as exc:
            if exc.status not in _RETRIABLE_GITHUB_STATUSES:
                raise
            last_exc = exc
            if attempt < max_attempts:
                retry_after = getattr(exc, "headers", {}).get("Retry-After")
                delay = float(retry_after) if retry_after else base_delay * (2 ** (attempt - 1))
                _log(
                    f"GitHub {exc.status} — "
                    f"attempt {attempt}/{max_attempts}, retrying in {delay:.0f}s"
                )
                time.sleep(delay)
        except (ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                _log(
                    f"Network error ({type(exc).__name__}) — "
                    f"attempt {attempt}/{max_attempts}, retrying in {delay:.0f}s"
                )
                time.sleep(delay)

    raise last_exc
