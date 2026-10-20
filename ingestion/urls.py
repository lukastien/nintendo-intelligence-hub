"""Host allow-list for official Nintendo IR URLs."""

from urllib.parse import urlparse

from nih.errors import ProvenanceError

OFFICIAL_HOSTS = frozenset({"www.nintendo.co.jp"})


def assert_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ProvenanceError(
            "Official IR URLs use https and the host www.nintendo.co.jp. "
            f"Received {url}."
        )


def assert_simulated_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host == "www.nintendo.co.jp" or host.endswith(".nintendo.co.jp"):
        raise ProvenanceError(
            "A simulated source points at a synthetic URL, outside nintendo.co.jp."
        )
