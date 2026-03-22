"""
Pluggable Notifier System for Agent Tick.

Provides a minimal notifier interface and built-in implementations:
- WebhookNotifier: POST JSON with retry/backoff
- ShellNotifier: Run a local command template
- TelegramNotifier: Send via Telegram Bot API

Handlers resolve notifiers by name from config instead of
shelling out to openclaw.
"""

from .base import Notifier, NotifierRegistry
from .webhook import WebhookNotifier
from .shell import ShellNotifier
from .telegram import TelegramNotifier

__all__ = [
    "Notifier",
    "NotifierRegistry",
    "WebhookNotifier",
    "ShellNotifier",
    "TelegramNotifier",
]
