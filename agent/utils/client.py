"""
Centralized Anthropic client.

Every module that needs to call the Anthropic API should import `get_client()`
from here instead of creating its own RetryingClient at module scope.

Benefits:
  - Single source of truth for the API key and retry settings.
  - Eager validation — a missing key produces a clear error at startup.
  - Lazy creation — the client is only built when first needed, avoiding
    import-time side-effects in modules that are imported but not used.
"""

import os
from functools import lru_cache

from agent.utils.retry import RetryingClient


@lru_cache(maxsize=1)
def get_client() -> RetryingClient:
    """Return a shared RetryingClient, creating it on first call.

    Raises RuntimeError immediately if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to config/.env or export it as an environment variable."
        )
    return RetryingClient(api_key=api_key)
