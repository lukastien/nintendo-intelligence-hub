"""HTTP fetch with a short retry budget.

Failures stay failures. Callers report the source unavailable instead of
filling the gap with another series.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

from nih.errors import NihError

logger = logging.getLogger("nih.ingest")

USER_AGENT = "NintendoIntelligenceHub/0.1 (educational portfolio; local ingestion)"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(NihError):
    """Raised when a URL cannot be retrieved inside the retry budget."""


def get_bytes(
    url: str,
    *,
    timeout: float = 30.0,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    session: requests.Session | None = None,
) -> bytes:
    """GET a URL and return the body.

    Retries connection errors and a few server statuses. The last error is
    raised. The response body of a successful request is returned unchanged.
    """

    if attempts < 1:
        raise FetchError("attempts must be at least 1")
    own_session = session is None
    client = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    last_error: Exception | None = None
    try:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(url, headers=headers, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("fetch failed %s attempt %s/%s: %s", url, attempt, attempts, exc)
            else:
                if response.status_code in RETRYABLE_STATUS:
                    last_error = FetchError(f"{url} returned HTTP {response.status_code}")
                    logger.warning(
                        "fetch retryable %s attempt %s/%s: HTTP %s",
                        url,
                        attempt,
                        attempts,
                        response.status_code,
                    )
                elif response.status_code >= 400:
                    raise FetchError(f"{url} returned HTTP {response.status_code}")
                else:
                    return response.content
            if attempt < attempts:
                sleep(0.4 * attempt)
        raise FetchError(f"{url} was not retrieved after {attempts} attempts: {last_error}")
    finally:
        if own_session:
            client.close()
