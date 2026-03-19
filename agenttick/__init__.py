"""
Agent Tick - Persistent daemon for AI agent autonomy

Provides continuous operation, event detection, and state management
for AI agents. Built for OpenClaw but adaptable to any framework.
"""

__version__ = '2.0.0-alpha'
__author__ = 'Mira Swift'

from .scheduler import AdaptiveScheduler
from .detector import EventDetector, Event

__all__ = ['AdaptiveScheduler', 'EventDetector', 'Event']
