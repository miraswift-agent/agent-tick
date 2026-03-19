"""
Tests for EventDetector
"""

import pytest
import tempfile
from pathlib import Path
from agenttick.detector import EventDetector, Event


def test_event_creation():
    """Test Event object creation."""
    event = Event(
        type='test:event',
        tier=2,
        data={'key': 'value'},
        source='test'
    )
    
    assert event.type == 'test:event'
    assert event.tier == 2
    assert event.data == {'key': 'value'}
    assert event.source == 'test'
    assert event.timestamp > 0


def test_event_to_dict():
    """Test Event serialization."""
    event = Event(
        type='test:event',
        tier=1,
        data={'x': 1},
        source='test',
        timestamp=12345
    )
    
    d = event.to_dict()
    
    assert d['type'] == 'test:event'
    assert d['tier'] == 1
    assert d['data'] == {'x': 1}
    assert d['source'] == 'test'
    assert d['timestamp'] == 12345


def test_detector_initialization():
    """Test EventDetector initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            'workspaceRoot': tmpdir,
            'watchPaths': [tmpdir],
            'monitoring': {'git': {'enabled': False}}
        }
        
        detector = EventDetector(config, 'test-agent')
        
        assert detector.agent_name == 'test-agent'
        assert len(detector.event_queue) == 0


def test_infer_tier_from_path():
    """Test path-based tier inference."""
    config = {
        'workspaceRoot': '/tmp',
        'watchPaths': []
    }
    detector = EventDetector(config, 'test')
    
    # Tier 1: high significance
    assert detector.infer_tier_from_path('/workspace/identity.md') == 1
    assert detector.infer_tier_from_path('/workspace/memory/preservation.md') == 1
    
    # Tier 3: low significance
    assert detector.infer_tier_from_path('/workspace/journal/2024-03-19.md') == 3
    assert detector.infer_tier_from_path('/workspace/test.log') == 3
    
    # Tier 2: default
    assert detector.infer_tier_from_path('/workspace/projects/agent-tick.py') == 2


def test_emit_event():
    """Test event emission and queueing."""
    config = {
        'workspaceRoot': '/tmp',
        'watchPaths': []
    }
    detector = EventDetector(config, 'test')
    
    event = Event(type='test', tier=2, data={}, source='test')
    detector.emit_event(event)
    
    assert len(detector.event_queue) == 1
    assert detector.event_queue[0].type == 'test'


def test_event_callback():
    """Test event callback registration."""
    config = {
        'workspaceRoot': '/tmp',
        'watchPaths': []
    }
    detector = EventDetector(config, 'test')
    
    received_events = []
    
    def callback(event):
        received_events.append(event)
    
    detector.on_event(callback)
    
    event = Event(type='test', tier=2, data={}, source='test')
    detector.emit_event(event)
    
    assert len(received_events) == 1
    assert received_events[0].type == 'test'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
