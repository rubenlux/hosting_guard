"""
Site availability probing for post-deploy health checks.

check_site_once  – single HTTP probe (no retries)
wait_for_site_online – polls until 2xx, hard HTTP error, or timeout

Status classification:
  2xx                             → online
  526 / TLS error / connect error → ssl_pending  (keep polling)
  403 / 404 / 502 / 503           → http_failed   (stop immediately)
"""
import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_FAIL_CODES = frozenset({403, 404, 502, 503})


async def check_site_once(subdomain: str, *, timeout: float = 8.0) -> dict:
    """
    Single HTTP probe.
    Returns {"http_status": int|None, "error_type": None|"tls"|"connection"|"other"}.
    """
    url = f"https://{subdomain}"
    try:
        async with httpx.AsyncClient(
            verify=False, timeout=timeout, follow_redirects=False
        ) as client:
            resp = await client.get(url)
            return {"http_status": resp.status_code, "error_type": None}
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
        return {"http_status": None, "error_type": "connection"}
    except Exception as exc:
        msg = str(exc).lower()
        if "ssl" in msg or "tls" in msg or "certificate" in msg:
            return {"http_status": None, "error_type": "tls"}
        return {"http_status": None, "error_type": "other"}


async def wait_for_site_online(
    subdomain: str,
    *,
    timeout_seconds: int = 60,
    interval_seconds: int = 5,
) -> dict:
    """
    Polls until 2xx, a hard HTTP failure, or timeout.

    Returns:
        {
            "status":           "online" | "ssl_pending" | "http_failed",
            "last_http_status": int | None,
            "last_error_type":  str | None,
            "attempts":         int,
            "duration_seconds": float,
        }
    """
    started = time.monotonic()
    attempts = 0
    last_status: Optional[int] = None
    last_error: Optional[str] = None

    while True:
        probe = await check_site_once(subdomain)
        attempts += 1
        last_status = probe["http_status"]
        last_error  = probe["error_type"]

        if last_status is not None and last_status < 400:
            return {
                "status": "online",
                "last_http_status": last_status,
                "last_error_type": None,
                "attempts": attempts,
                "duration_seconds": time.monotonic() - started,
            }

        if last_status in _HTTP_FAIL_CODES:
            return {
                "status": "http_failed",
                "last_http_status": last_status,
                "last_error_type": None,
                "attempts": attempts,
                "duration_seconds": time.monotonic() - started,
            }

        elapsed = time.monotonic() - started
        remaining = timeout_seconds - elapsed
        if remaining <= interval_seconds:
            return {
                "status": "ssl_pending",
                "last_http_status": last_status,
                "last_error_type": last_error,
                "attempts": attempts,
                "duration_seconds": elapsed,
            }

        await asyncio.sleep(interval_seconds)
