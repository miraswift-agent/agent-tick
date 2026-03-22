"""
Tests for pluggable notifier system (Issue #2).

Covers:
- NotifierRegistry creation from config
- WebhookNotifier retry/backoff logic
- ShellNotifier template substitution and safety
- TelegramNotifier initialization
- FreezeDetector integration with notifiers
- Named notifier lookup
"""

import asyncio
import json
import os
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agenttick.notifiers.base import (
    Notifier,
    NotifierRegistry,
    register_notifier_type,
    get_notifier_type,
)
from agenttick.notifiers.webhook import WebhookNotifier, RetryableError
from agenttick.notifiers.shell import ShellNotifier
from agenttick.notifiers.telegram import TelegramNotifier


# --- Test Helpers ---


class MockNotifier(Notifier):
    """Test notifier that records sends."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.sent: List[dict] = []

    async def send(
        self, title: str, text: str, tags: Optional[Dict[str, str]] = None
    ) -> bool:
        self.sent.append({"title": title, "text": text, "tags": tags})
        return True


# --- NotifierRegistry Tests ---


class TestNotifierRegistry:
    def test_register_and_get(self):
        registry = NotifierRegistry()
        notifier = MockNotifier({})
        registry.register("test", notifier)
        assert registry.get("test") is notifier

    def test_get_missing_returns_none(self):
        registry = NotifierRegistry()
        assert registry.get("nonexistent") is None

    def test_names(self):
        registry = NotifierRegistry()
        registry.register("a", MockNotifier({}))
        registry.register("b", MockNotifier({}))
        assert set(registry.names()) == {"a", "b"}

    def test_from_config_webhook(self):
        """Build registry from config with webhook notifier."""
        config = [
            {
                "name": "my_hook",
                "type": "webhook",
                "config": {"url": "https://example.com/hook"},
            }
        ]
        registry = NotifierRegistry.from_config(config)
        assert "my_hook" in registry.names()
        assert isinstance(registry.get("my_hook"), WebhookNotifier)

    def test_from_config_shell(self):
        config = [
            {
                "name": "my_shell",
                "type": "shell",
                "config": {"cmd": 'echo "{title}"'},
            }
        ]
        registry = NotifierRegistry.from_config(config)
        assert isinstance(registry.get("my_shell"), ShellNotifier)

    def test_from_config_telegram(self):
        config = [
            {
                "name": "tg",
                "type": "telegram",
                "config": {"bot_token": "123:ABC", "chat_id": "-100123"},
            }
        ]
        registry = NotifierRegistry.from_config(config)
        assert isinstance(registry.get("tg"), TelegramNotifier)

    def test_from_config_unknown_type(self):
        """Unknown type is skipped with warning."""
        config = [
            {
                "name": "bad",
                "type": "carrier_pigeon",
                "config": {},
            }
        ]
        registry = NotifierRegistry.from_config(config)
        assert registry.get("bad") is None

    def test_from_config_invalid_config(self):
        """Invalid config (missing required field) is skipped."""
        config = [
            {
                "name": "broken",
                "type": "webhook",
                "config": {},  # Missing 'url'
            }
        ]
        registry = NotifierRegistry.from_config(config)
        assert registry.get("broken") is None


# --- WebhookNotifier Tests ---


class TestWebhookNotifier:
    def test_init_requires_url(self):
        with pytest.raises(ValueError, match="url"):
            WebhookNotifier({})

    def test_init_with_url(self):
        n = WebhookNotifier({"url": "https://example.com"})
        assert n.url == "https://example.com"
        assert n.max_retries == 5
        assert n.timeout_s == 5.0

    def test_init_custom_config(self):
        n = WebhookNotifier(
            {
                "url": "https://example.com",
                "timeoutMs": 3000,
                "maxRetries": 3,
                "backoff": "linear",
                "headers": {"Authorization": "Bearer token"},
            }
        )
        assert n.timeout_s == 3.0
        assert n.max_retries == 3
        assert n.backoff == "linear"
        assert n.headers["Authorization"] == "Bearer token"

    def test_backoff_exponential(self):
        n = WebhookNotifier({"url": "https://example.com"})
        assert n._calculate_backoff(0) == 1.0
        assert n._calculate_backoff(1) == 2.0
        assert n._calculate_backoff(2) == 4.0
        assert n._calculate_backoff(10) == 60.0  # Capped at 60

    def test_backoff_linear(self):
        n = WebhookNotifier({"url": "https://example.com", "backoff": "linear"})
        assert n._calculate_backoff(0) == 2.0
        assert n._calculate_backoff(1) == 4.0
        assert n._calculate_backoff(2) == 6.0

    def test_backoff_respects_retry_after(self):
        n = WebhookNotifier({"url": "https://example.com"})
        assert n._calculate_backoff(0, retry_after=30.0) == 30.0


# --- ShellNotifier Tests ---


class TestShellNotifier:
    def test_init_requires_cmd(self):
        with pytest.raises(ValueError, match="cmd"):
            ShellNotifier({})

    def test_init_with_cmd(self):
        n = ShellNotifier({"cmd": 'echo "hello"'})
        assert n.cmd_template == 'echo "hello"'
        assert n.use_shell is False

    @pytest.mark.asyncio
    async def test_send_echo(self):
        """Shell notifier executes command successfully."""
        n = ShellNotifier({"cmd": "echo {title}", "shell": True})
        result = await n.send("Test Alert", "Some body text")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_with_env_vars(self):
        """Environment variables are set during execution."""
        n = ShellNotifier(
            {"cmd": 'printenv AGENT_TICK_TITLE', "shell": True}
        )
        result = await n.send("My Title", "My Text")
        assert result is True

    def test_sanitize_removes_backticks(self):
        assert ShellNotifier._sanitize("hello `rm -rf`") == "hello rm -rf"

    def test_sanitize_removes_dollar_paren(self):
        input_str = "$(whoami)"
        result = ShellNotifier._sanitize(input_str)
        expected = "whoami" + ")"
        assert result == expected

    def test_sanitize_removes_semicolons(self):
        assert ShellNotifier._sanitize("hello; rm -rf /") == "hello rm -rf /"

    def test_sanitize_clean_string(self):
        assert ShellNotifier._sanitize("normal text 123") == "normal text 123"

    @pytest.mark.asyncio
    async def test_send_bad_command(self):
        """Non-existent command returns False."""
        n = ShellNotifier({"cmd": "nonexistent_command_xyz"})
        result = await n.send("test", "test")
        assert result is False

    @pytest.mark.asyncio
    async def test_template_substitution(self):
        """Template placeholders are filled correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            outpath = f.name

        try:
            n = ShellNotifier(
                {"cmd": f'echo "{{title}} - {{text}}" > {outpath}', "shell": True}
            )
            result = await n.send("MyTitle", "MyText")
            assert result is True

            with open(outpath) as f:
                content = f.read().strip()
            assert content == "MyTitle - MyText"
        finally:
            os.unlink(outpath)


# --- TelegramNotifier Tests ---


class TestTelegramNotifier:
    def test_init_requires_bot_token(self):
        with pytest.raises(ValueError, match="bot_token"):
            TelegramNotifier({"chat_id": "123"})

    def test_init_requires_chat_id(self):
        with pytest.raises(ValueError, match="chat_id"):
            TelegramNotifier({"bot_token": "123:ABC"})

    def test_init_with_config(self):
        n = TelegramNotifier(
            {
                "bot_token": "123:ABC",
                "chat_id": "-100123",
                "parse_mode": "Markdown",
            }
        )
        assert n.bot_token == "123:ABC"
        assert n.chat_id == "-100123"
        assert n.parse_mode == "Markdown"

    def test_escape_html(self):
        assert TelegramNotifier._escape_html("<b>test</b>") == "&lt;b&gt;test&lt;/b&gt;"
        assert TelegramNotifier._escape_html("A & B") == "A &amp; B"


# --- FreezeDetector Integration Tests ---


class TestFreezeDetectorNotifier:
    """Test FreezeDetector with pluggable notifiers."""

    def test_freeze_detector_with_notifier(self):
        """FreezeDetector resolves named notifier from registry."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "handlers"))
        from freeze_detector import FreezeDetector

        mock_notifier = MockNotifier({})
        registry = NotifierRegistry()
        registry.register("test_hook", mock_notifier)

        fd = FreezeDetector(
            {"notifier": "test_hook", "freeze_threshold_ms": 0},
            notifier_registry=registry,
        )
        assert fd._resolved_notifier is mock_notifier

    def test_freeze_detector_missing_notifier_fallback(self):
        """FreezeDetector falls back to alert_method if notifier not found."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "handlers"))
        from freeze_detector import FreezeDetector

        registry = NotifierRegistry()
        fd = FreezeDetector(
            {"notifier": "nonexistent", "alert_method": "log_only"},
            notifier_registry=registry,
        )
        assert fd._resolved_notifier is None
        assert fd.alert_method == "log_only"

    def test_freeze_detector_no_registry(self):
        """FreezeDetector works without a notifier registry (backward compat)."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "handlers"))
        from freeze_detector import FreezeDetector

        fd = FreezeDetector(
            {"freeze_threshold_ms": 1800000, "alert_method": "log_only"}
        )
        assert fd._resolved_notifier is None


# --- Type Registration Tests ---


class TestTypeRegistration:
    def test_webhook_registered(self):
        assert get_notifier_type("webhook") is WebhookNotifier

    def test_shell_registered(self):
        assert get_notifier_type("shell") is ShellNotifier

    def test_telegram_registered(self):
        assert get_notifier_type("telegram") is TelegramNotifier

    def test_unknown_type(self):
        assert get_notifier_type("carrier_pigeon") is None

    def test_custom_registration(self):
        register_notifier_type("mock", MockNotifier)
        assert get_notifier_type("mock") is MockNotifier


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
