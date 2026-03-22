"""
Base notifier interface and registry.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type


class Notifier(ABC):
    """
    Minimal notifier interface.

    All notifiers must implement:
    - __init__(config: dict) — initialize from config dict
    - send(title, text, tags) — send a notification (async)
    """

    def __init__(self, config: dict):
        """
        Initialize notifier with configuration.

        Args:
            config: Notifier-specific configuration dict
        """
        self.config = config

    @abstractmethod
    async def send(
        self, title: str, text: str, tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Send a notification.

        Args:
            title: Notification title/subject
            text: Notification body text
            tags: Optional key-value tags for metadata

        Returns:
            True if sent successfully, False otherwise
        """
        ...


# Registry of built-in notifier types
_NOTIFIER_TYPES: Dict[str, Type[Notifier]] = {}


def register_notifier_type(name: str, cls: Type[Notifier]) -> None:
    """Register a notifier type for factory creation."""
    _NOTIFIER_TYPES[name] = cls


def get_notifier_type(name: str) -> Optional[Type[Notifier]]:
    """Get a registered notifier type by name."""
    return _NOTIFIER_TYPES.get(name)


class NotifierRegistry:
    """
    Registry of named notifier instances.

    Handlers look up notifiers by name instead of coupling to
    specific implementations.
    """

    def __init__(self):
        self._notifiers: Dict[str, Notifier] = {}

    def register(self, name: str, notifier: Notifier) -> None:
        """Register a notifier instance by name."""
        self._notifiers[name] = notifier

    def get(self, name: str) -> Optional[Notifier]:
        """Get a notifier by name."""
        return self._notifiers.get(name)

    def names(self) -> List[str]:
        """List all registered notifier names."""
        return list(self._notifiers.keys())

    @classmethod
    def from_config(cls, notifiers_config: List[dict]) -> "NotifierRegistry":
        """
        Build a NotifierRegistry from config.

        Args:
            notifiers_config: List of notifier config dicts, each with:
                - name: Unique name for this notifier
                - type: Notifier type (webhook, shell, telegram)
                - config: Type-specific configuration

        Returns:
            Populated NotifierRegistry

        Raises:
            ValueError: If a notifier type is unknown
        """
        registry = cls()

        for entry in notifiers_config:
            name = entry.get("name", "unnamed")
            ntype = entry.get("type", "")
            nconfig = entry.get("config", {})

            notifier_cls = get_notifier_type(ntype)
            if notifier_cls is None:
                print(
                    f"[NotifierRegistry] Warning: Unknown notifier type '{ntype}' "
                    f"for '{name}', skipping"
                )
                continue

            try:
                notifier = notifier_cls(nconfig)
                registry.register(name, notifier)
                print(f"[NotifierRegistry] Registered notifier: {name} ({ntype})")
            except Exception as e:
                print(
                    f"[NotifierRegistry] Failed to create notifier '{name}': {e}"
                )

        return registry
