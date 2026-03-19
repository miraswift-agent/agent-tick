"""
Tests for AdaptiveScheduler
"""

import pytest
from datetime import datetime
from agenttick.scheduler import AdaptiveScheduler


def test_scheduler_initialization():
    """Test scheduler initializes with correct defaults."""
    config = {}
    scheduler = AdaptiveScheduler(config)
    
    assert scheduler.active_interval == 1000
    assert scheduler.idle_interval == 30000
    assert scheduler.sleep_interval == 300000
    assert scheduler.sleep_hours == (2, 6)
    assert scheduler.current_state == 'idle'


def test_scheduler_custom_config():
    """Test scheduler respects custom configuration."""
    config = {
        'active_interval_ms': 500,
        'idle_interval_ms': 15000,
        'sleep_hours': (1, 5),
    }
    scheduler = AdaptiveScheduler(config)
    
    assert scheduler.active_interval == 500
    assert scheduler.idle_interval == 15000
    assert scheduler.sleep_hours == (1, 5)


def test_mark_event_resets_state():
    """Test that marking an event resets to active state."""
    scheduler = AdaptiveScheduler({})
    scheduler.current_state = 'idle'
    
    scheduler.mark_event()
    
    assert scheduler.current_state == 'active'
    assert scheduler.ultra_quiet_multiplier == 1.0


def test_active_state_interval():
    """Test active state returns short interval."""
    scheduler = AdaptiveScheduler({})
    scheduler.mark_event()  # Recent event
    
    interval = scheduler.get_next_interval()
    
    assert interval == 1000  # Active interval
    assert scheduler.get_state() == 'active'


def test_sleep_hours_detection():
    """Test sleep hours are properly detected."""
    # This test is time-dependent - would need mocking for consistent results
    # Left as placeholder for now
    pass


def test_ultra_quiet_exponential_backoff():
    """Test ultra-quiet mode applies exponential backoff."""
    config = {'ultra_quiet_threshold_ms': 0}  # Immediate ultra-quiet for testing
    scheduler = AdaptiveScheduler(config)
    
    # Simulate 30 minutes of no events
    scheduler.last_event_time = (datetime.now().timestamp() - 1800) * 1000
    
    interval = scheduler.get_next_interval()
    
    # Should be significantly higher than idle interval
    assert interval > 30000
    assert scheduler.get_state() == 'ultra_quiet'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
