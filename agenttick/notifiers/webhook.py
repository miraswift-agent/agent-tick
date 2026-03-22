"""
Webhook Notifier — POST JSON payload with retry and exponential backoff.

Respects 429/Retry-After headers.
"""

import asyncio
import json
import time
from typing import Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .base import Notifier, register_notifier_type


class WebhookNotifier(Notifier):
    """
    POST JSON notifications to a webhook URL.

    Config:
        url: Webhook endpoint URL (required)
        headers: Dict of extra HTTP headers (optional)
        timeoutMs: Request timeout in milliseconds (default: 5000)
        maxRetries: Maximum retry attempts (default: 5)
        backoff: Backoff strategy — "exponential" or "linear" (default: exponential)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.url: str = config.get("url", "")
        if not self.url:
            raise ValueError("WebhookNotifier requires 'url' in config")

        self.headers: Dict[str, str] = config.get("headers", {})
        self.timeout_s: float = config.get("timeoutMs", 5000) / 1000.0
        self.max_retries: int = config.get("maxRetries", 5)
        self.backoff: str = config.get("backoff", "exponential")

    async def send(
        self, title: str, text: str, tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Send a JSON POST to the webhook URL with retry/backoff.

        Payload format:
            {"title": "...", "text": "...", "tags": {...}, "timestamp": ...}
        """
        payload = {
            "title": title,
            "text": text,
            "tags": tags or {},
            "timestamp": int(time.time() * 1000),
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(self.max_retries + 1):
            try:
                result = await self._do_request(data)
                return result
            except RetryableError as e:
                if attempt >= self.max_retries:
                    print(
                        f"[WebhookNotifier] Failed after {self.max_retries} retries: {e}"
                    )
                    return False

                delay = self._calculate_backoff(attempt, e.retry_after)
                print(
                    f"[WebhookNotifier] Retry {attempt + 1}/{self.max_retries} "
                    f"in {delay:.1f}s ({e})"
                )
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"[WebhookNotifier] Non-retryable error: {e}")
                return False

        return False

    async def _do_request(self, data: bytes) -> bool:
        """Execute the HTTP request (runs in executor to avoid blocking)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_request, data)

    def _sync_request(self, data: bytes) -> bool:
        """Synchronous HTTP POST."""
        req = Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in self.headers.items():
            req.add_header(key, value)

        try:
            response = urlopen(req, timeout=self.timeout_s)
            status = response.getcode()
            if 200 <= status < 300:
                return True
            raise RetryableError(f"HTTP {status}")
        except HTTPError as e:
            if e.code == 429:
                # Rate limited — respect Retry-After header
                retry_after = None
                ra_header = e.headers.get("Retry-After")
                if ra_header:
                    try:
                        retry_after = float(ra_header)
                    except ValueError:
                        pass
                raise RetryableError(
                    f"429 Too Many Requests", retry_after=retry_after
                )
            elif 500 <= e.code < 600:
                raise RetryableError(f"HTTP {e.code}")
            else:
                raise  # Non-retryable HTTP error
        except URLError as e:
            raise RetryableError(f"Connection error: {e.reason}")

    def _calculate_backoff(
        self, attempt: int, retry_after: Optional[float] = None
    ) -> float:
        """Calculate backoff delay in seconds."""
        if retry_after is not None:
            return retry_after

        if self.backoff == "linear":
            return (attempt + 1) * 2.0
        else:
            # Exponential: 1s, 2s, 4s, 8s, 16s
            return min(2**attempt, 60.0)


class RetryableError(Exception):
    """Error that should be retried."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


# Register with factory
register_notifier_type("webhook", WebhookNotifier)
