"""
Telegram Notifier — Send messages via Telegram Bot API.

Optional: only active if bot_token and chat_id are provided.
"""

import asyncio
import json
from typing import Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .base import Notifier, register_notifier_type


class TelegramNotifier(Notifier):
    """
    Send notifications via Telegram Bot API.

    Config:
        bot_token: Telegram bot token (required)
        chat_id: Target chat/group ID (required)
        parse_mode: Message parse mode — "HTML" or "Markdown" (default: "HTML")
        disable_notification: Send silently (default: False)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.bot_token: str = config.get("bot_token", "")
        self.chat_id: str = str(config.get("chat_id", ""))

        if not self.bot_token:
            raise ValueError("TelegramNotifier requires 'bot_token' in config")
        if not self.chat_id:
            raise ValueError("TelegramNotifier requires 'chat_id' in config")

        self.parse_mode: str = config.get("parse_mode", "HTML")
        self.disable_notification: bool = config.get("disable_notification", False)
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"

    async def send(
        self, title: str, text: str, tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Send a message via Telegram Bot API.

        Format: "<b>title</b>\n\ntext\n\ntags"
        """
        # Build message
        if self.parse_mode == "HTML":
            message = f"<b>{self._escape_html(title)}</b>\n\n{self._escape_html(text)}"
        else:
            message = f"*{title}*\n\n{text}"

        if tags:
            tags_str = " ".join(f"#{k}:{v}" for k, v in tags.items())
            message += f"\n\n{tags_str}"

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": self.parse_mode,
            "disable_notification": self.disable_notification,
        }

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._sync_send, payload
            )
            return result
        except Exception as e:
            print(f"[TelegramNotifier] Error: {e}")
            return False

    def _sync_send(self, payload: dict) -> bool:
        """Synchronous Telegram API call."""
        url = f"{self.api_base}/sendMessage"
        data = json.dumps(payload).encode("utf-8")

        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            response = urlopen(req, timeout=10)
            result = json.loads(response.read().decode("utf-8"))
            return result.get("ok", False)
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"[TelegramNotifier] HTTP {e.code}: {body}")
            return False
        except URLError as e:
            print(f"[TelegramNotifier] Connection error: {e.reason}")
            return False

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters for Telegram."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


# Register with factory
register_notifier_type("telegram", TelegramNotifier)
