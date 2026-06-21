"""Fetch an Indeed job page using only the Python standard library.

Indeed sits behind anti-bot protection, so we present realistic browser
headers and retry on transient/blocking status codes with backoff. No third
party packages are required (no ``requests``), which keeps the tool install
free and dependency free.
"""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
import zlib

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "no-cache",
    "Connection": "close",
}

# Status codes worth retrying — transient server errors plus the codes Indeed
# returns when it rate-limits or challenges an automated request.
_RETRY_STATUS = {403, 408, 425, 429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised when a page cannot be retrieved after exhausting retries."""

    def __init__(self, url: str, message: str, status: int | None = None):
        self.url = url
        self.status = status
        super().__init__(message)


def _decode_body(raw: bytes, encoding: str | None) -> str:
    enc = (encoding or "").lower()
    if "gzip" in enc:
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif "deflate" in enc:
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            try:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except zlib.error:
                pass
    return raw.decode("utf-8", errors="replace")


def fetch(
    url: str,
    *,
    timeout: float = 30.0,
    retries: int = 3,
    backoff: float = 2.0,
) -> str:
    """Return the HTML body of ``url``.

    Retries on transient/blocking statuses with exponential backoff. Raises
    :class:`FetchError` if every attempt fails.
    """
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = _decode_body(resp.read(), resp.headers.get("Content-Encoding"))
                return body
        except urllib.error.HTTPError as e:
            last_err = e
            status = e.code
            if status not in _RETRY_STATUS or attempt == retries:
                raise FetchError(
                    url,
                    f"HTTP {status} {e.reason} (Indeed may be blocking automated "
                    f"requests; try --html with a saved page)",
                    status=status,
                ) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt == retries:
                raise FetchError(url, f"network error: {e}") from e
        # Backoff before the next attempt.
        time.sleep(backoff * (2**attempt))

    raise FetchError(url, f"failed after {retries + 1} attempts: {last_err}")
