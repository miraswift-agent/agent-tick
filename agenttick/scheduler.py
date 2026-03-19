"""
Adaptive Scheduler for Agent Tick

Manages tick intervals based on activity, system load, and time of day.
Implements exponential backoff for ultra-quiet periods.
"""

import asyncio
import psutil
from datetime import datetime
from typing import Optional


class AdaptiveScheduler:
    """
    Adaptive tick scheduler with system-load awareness.
    
    States:
    - active: Recent event detected (1s default)
    - idle: No events for 5+ minutes (30s default)
    - sleep: During configured sleep hours (5min default)
    - ultra_quiet: Extended idle with exponential backoff
    """
    
    def __init__(self, config: dict):
        """
        Initialize scheduler with agent-specific config.
        
        Args:
            config: Dict with keys:
                - active_interval_ms: Tick interval when active (default: 1000)
                - idle_interval_ms: Tick interval when idle (default: 30000)
                - sleep_interval_ms: Tick interval during sleep (default: 300000)
                - sleep_hours: Tuple (start, end) in 24h format (default: (2, 6))
                - ultra_quiet_threshold_ms: When to enter ultra_quiet (default: 1800000 = 30min)
                - ultra_quiet_max_ms: Max interval during ultra_quiet (default: 900000 = 15min)
                - system_load_threshold: CPU % to trigger throttle (default: 70)
        """
        self.config = config
        
        # Interval configuration (milliseconds)
        self.active_interval = config.get('active_interval_ms', 1000)
        self.idle_interval = config.get('idle_interval_ms', 30000)
        self.sleep_interval = config.get('sleep_interval_ms', 300000)
        
        # Sleep hours (local time, 24h format)
        self.sleep_hours = config.get('sleep_hours', (2, 6))
        
        # Ultra-quiet mode (exponential backoff)
        self.ultra_quiet_threshold = config.get('ultra_quiet_threshold_ms', 1800000)  # 30 min
        self.ultra_quiet_max = config.get('ultra_quiet_max_ms', 900000)  # 15 min
        
        # System load awareness
        self.system_load_threshold = config.get('system_load_threshold', 70)
        
        # State tracking
        self.last_event_time = datetime.now().timestamp() * 1000  # ms
        self.current_state = 'idle'
        self.ultra_quiet_multiplier = 1.0
        
    def mark_event(self):
        """Mark that an event was detected (resets to active state)."""
        self.last_event_time = datetime.now().timestamp() * 1000
        self.current_state = 'active'
        self.ultra_quiet_multiplier = 1.0
        
    def get_next_interval(self) -> float:
        """
        Calculate the next tick interval in milliseconds.
        
        Returns:
            float: Milliseconds until next tick
        """
        now = datetime.now()
        current_time_ms = now.timestamp() * 1000
        time_since_event = current_time_ms - self.last_event_time
        
        # Determine base interval
        interval = self._calculate_base_interval(now, time_since_event)
        
        # Apply system load throttling
        interval = self._apply_system_load_throttle(interval)
        
        return interval
    
    def _calculate_base_interval(self, now: datetime, time_since_event: float) -> float:
        """Calculate base interval before throttling."""
        hour = now.hour
        
        # Sleep mode: configured sleep hours
        if self.sleep_hours[0] <= hour < self.sleep_hours[1]:
            self.current_state = 'sleep'
            return self.sleep_interval
        
        # Active mode: event within last 60 seconds
        if time_since_event < 60 * 1000:
            self.current_state = 'active'
            return self.active_interval
        
        # Ultra-quiet mode: no events for 30+ minutes
        if time_since_event > self.ultra_quiet_threshold:
            self.current_state = 'ultra_quiet'
            return self._calculate_ultra_quiet_interval(time_since_event)
        
        # Idle mode: no events for 5+ minutes
        if time_since_event > 5 * 60 * 1000:
            self.current_state = 'idle'
            return self.idle_interval
        
        # Default: standard monitoring (5 seconds)
        self.current_state = 'idle'
        return 5000
    
    def _calculate_ultra_quiet_interval(self, time_since_event: float) -> float:
        """
        Calculate interval for ultra-quiet mode with exponential backoff.
        
        Pattern: 30s → 10min → 30min → capped at 15min
        """
        # Time past the ultra-quiet threshold
        quiet_duration = time_since_event - self.ultra_quiet_threshold
        
        # Exponential multiplier based on how long we've been quiet
        # Doubles every 10 minutes of quiet time
        minutes_quiet = quiet_duration / (60 * 1000)
        self.ultra_quiet_multiplier = min(2 ** (minutes_quiet / 10), 30)  # Cap at 30x
        
        interval = self.idle_interval * self.ultra_quiet_multiplier
        
        # Cap at configured maximum
        return min(interval, self.ultra_quiet_max)
    
    def _apply_system_load_throttle(self, interval: float) -> float:
        """
        Apply system load throttling if CPU or RAM is under pressure.
        
        Args:
            interval: Base interval in milliseconds
            
        Returns:
            float: Throttled interval (1.5-2x if system stressed)
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            
            # If either CPU or RAM is high, throttle
            if cpu_percent > self.system_load_threshold or memory_percent > 80:
                throttle_factor = 1.5 if cpu_percent > self.system_load_threshold else 2.0
                return interval * throttle_factor
                
        except Exception:
            # If psutil fails, don't throttle (graceful degradation)
            pass
        
        return interval
    
    def get_state(self) -> str:
        """Get current scheduler state for logging."""
        return self.current_state
    
    def get_stats(self) -> dict:
        """Get current scheduler statistics."""
        return {
            'state': self.current_state,
            'last_event_ms_ago': datetime.now().timestamp() * 1000 - self.last_event_time,
            'ultra_quiet_multiplier': self.ultra_quiet_multiplier,
        }
