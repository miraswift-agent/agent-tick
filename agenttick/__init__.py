"""
Agent Tick - Persistent daemon for AI agent autonomy

Provides continuous operation, event detection, and state management
for AI agents. Built for OpenClaw but adaptable to any framework.
"""

__version__ = "2.1.0-alpha"
__author__ = "Mira Swift"

from .config import AgentConfig, load_and_validate_config, DEFAULT_IGNORE_PATTERNS
from .scheduler import AdaptiveScheduler
from .detector import EventDetector, Event
from .state import StateManager, create_state_manager
from .daemon import AgentTickDaemon

__all__ = [
    "AgentConfig",
    "load_and_validate_config",
    "DEFAULT_IGNORE_PATTERNS",
    "AdaptiveScheduler",
    "EventDetector",
    "Event",
    "StateManager",
    "create_state_manager",
    "AgentTickDaemon",
]
