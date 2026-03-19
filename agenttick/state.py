"""
State Management for Agent Tick

Provides pluggable backends for state persistence:
- SQLite (production default, crash-proof)
- JSON (debugging, legacy)
- Engram (future integration)
"""

import json
import sqlite3
import aiosqlite
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from .detector import Event


class StateBackend(ABC):
    """Abstract base class for state persistence backends."""
    
    @abstractmethod
    async def save_event(self, event: Event) -> None:
        """Save an event to persistent storage."""
        pass
    
    @abstractmethod
    async def get_events(self, 
                        since: Optional[int] = None,
                        tier: Optional[int] = None,
                        limit: int = 100) -> List[Event]:
        """Retrieve events with optional filters."""
        pass
    
    @abstractmethod
    async def save_snapshot(self, key: str, value: Any) -> None:
        """Save a key-value snapshot."""
        pass
    
    @abstractmethod
    async def get_snapshot(self, key: str) -> Optional[Any]:
        """Retrieve a snapshot value."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close backend connections."""
        pass


class SQLiteBackend(StateBackend):
    """
    SQLite-based state backend (production default).
    
    Features:
    - ACID compliance with WAL mode
    - Crash-proof event storage
    - Efficient querying with indexes
    - Engram-compatible schema
    """
    
    def __init__(self, db_path: str):
        """
        Initialize SQLite backend.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        """Initialize database connection and schema."""
        self.db = await aiosqlite.connect(str(self.db_path))
        
        # Enable WAL mode for crash safety
        await self.db.execute('PRAGMA journal_mode=WAL')
        
        # Create schema
        await self._create_schema()
        
        await self.db.commit()
    
    async def _create_schema(self):
        """Create database tables and indexes."""
        # Events table
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                type TEXT NOT NULL,
                tier INTEGER NOT NULL,
                data JSON,
                source TEXT NOT NULL,
                handled BOOLEAN DEFAULT FALSE,
                created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
            )
        ''')
        
        # Snapshots table (for daemon state)
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                key TEXT PRIMARY KEY,
                value JSON,
                updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
            )
        ''')
        
        # Agent metadata table
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS agent_metadata (
                key TEXT PRIMARY KEY,
                value JSON,
                updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
            )
        ''')
        
        # Indexes for fast queries
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_events_tier ON events(tier)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_events_handled ON events(handled)')
    
    async def save_event(self, event: Event) -> None:
        """Save an event to the database."""
        await self.db.execute('''
            INSERT INTO events (timestamp, type, tier, data, source)
            VALUES (?, ?, ?, ?, ?)
        ''', (event.timestamp, event.type, event.tier, json.dumps(event.data), event.source))
        
        await self.db.commit()
    
    async def get_events(self,
                        since: Optional[int] = None,
                        tier: Optional[int] = None,
                        limit: int = 100) -> List[Event]:
        """Retrieve events with filters."""
        query = 'SELECT timestamp, type, tier, data, source FROM events WHERE 1=1'
        params = []
        
        if since is not None:
            query += ' AND timestamp > ?'
            params.append(since)
        
        if tier is not None:
            query += ' AND tier = ?'
            params.append(tier)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor = await self.db.execute(query, params)
        rows = await cursor.fetchall()
        
        events = []
        for row in rows:
            timestamp, event_type, event_tier, data_json, source = row
            events.append(Event(
                type=event_type,
                tier=event_tier,
                data=json.loads(data_json) if data_json else {},
                source=source,
                timestamp=timestamp
            ))
        
        return events
    
    async def save_snapshot(self, key: str, value: Any) -> None:
        """Save or update a snapshot."""
        await self.db.execute('''
            INSERT OR REPLACE INTO snapshots (key, value)
            VALUES (?, ?)
        ''', (key, json.dumps(value)))
        
        await self.db.commit()
    
    async def get_snapshot(self, key: str) -> Optional[Any]:
        """Retrieve a snapshot value."""
        cursor = await self.db.execute(
            'SELECT value FROM snapshots WHERE key = ?',
            (key,)
        )
        row = await cursor.fetchone()
        
        if row:
            return json.loads(row[0])
        return None
    
    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.close()


class JSONBackend(StateBackend):
    """
    JSON file-based state backend (debugging/legacy).
    
    Simple file I/O for human-readable state.
    Not crash-proof, no querying support.
    """
    
    def __init__(self, json_path: str):
        """
        Initialize JSON backend.
        
        Args:
            json_path: Path to JSON state file
        """
        self.json_path = Path(json_path)
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
    
    def _load_state(self) -> dict:
        """Load state from JSON file."""
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.json_path}, starting fresh")
        
        return {
            'events': [],
            'snapshots': {},
            'metadata': {}
        }
    
    def _save_state(self):
        """Save state to JSON file."""
        with open(self.json_path, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    async def save_event(self, event: Event) -> None:
        """Save event to JSON state."""
        self.state['events'].append(event.to_dict())
        
        # Keep only last 1000 events to prevent file bloat
        if len(self.state['events']) > 1000:
            self.state['events'] = self.state['events'][-1000:]
        
        self._save_state()
    
    async def get_events(self,
                        since: Optional[int] = None,
                        tier: Optional[int] = None,
                        limit: int = 100) -> List[Event]:
        """Retrieve events (inefficient - loads all then filters)."""
        events = []
        
        for event_dict in reversed(self.state['events']):
            if since is not None and event_dict['timestamp'] <= since:
                continue
            if tier is not None and event_dict['tier'] != tier:
                continue
            
            events.append(Event(
                type=event_dict['type'],
                tier=event_dict['tier'],
                data=event_dict['data'],
                source=event_dict['source'],
                timestamp=event_dict['timestamp']
            ))
            
            if len(events) >= limit:
                break
        
        return events
    
    async def save_snapshot(self, key: str, value: Any) -> None:
        """Save snapshot to JSON state."""
        self.state['snapshots'][key] = value
        self._save_state()
    
    async def get_snapshot(self, key: str) -> Optional[Any]:
        """Retrieve snapshot from JSON state."""
        return self.state['snapshots'].get(key)
    
    async def close(self) -> None:
        """No cleanup needed for JSON backend."""
        pass


class StateManager:
    """
    High-level state management with pluggable backends.
    
    Provides convenient methods for common state operations
    while abstracting the underlying storage mechanism.
    """
    
    def __init__(self, backend: StateBackend, agent_name: str):
        """
        Initialize state manager.
        
        Args:
            backend: State backend instance
            agent_name: Name of the agent
        """
        self.backend = backend
        self.agent_name = agent_name
    
    async def initialize(self):
        """Initialize backend (if needed)."""
        if hasattr(self.backend, 'initialize'):
            await self.backend.initialize()
    
    async def save_event(self, event: Event) -> None:
        """Save an event."""
        await self.backend.save_event(event)
    
    async def get_recent_events(self, limit: int = 100) -> List[Event]:
        """Get most recent events."""
        return await self.backend.get_events(limit=limit)
    
    async def get_events_since(self, timestamp: int, limit: int = 100) -> List[Event]:
        """Get events since a timestamp."""
        return await self.backend.get_events(since=timestamp, limit=limit)
    
    async def get_high_priority_events(self, limit: int = 100) -> List[Event]:
        """Get Tier 1 events only."""
        return await self.backend.get_events(tier=1, limit=limit)
    
    async def save_daemon_state(self, state: dict) -> None:
        """Save daemon state snapshot."""
        await self.backend.save_snapshot('daemon_state', state)
    
    async def get_daemon_state(self) -> dict:
        """Get daemon state snapshot."""
        state = await self.backend.get_snapshot('daemon_state')
        if state is None:
            # Default state
            return {
                'last_tick': 0,
                'scheduler_state': 'idle',
                'last_published': {},
                'published_this_week': {}
            }
        return state
    
    async def update_last_published(self, channel: str) -> None:
        """Update last published timestamp for a channel."""
        import time
        state = await self.get_daemon_state()
        if 'last_published' not in state:
            state['last_published'] = {}
        state['last_published'][channel] = int(time.time() * 1000)
        await self.save_daemon_state(state)
    
    async def close(self) -> None:
        """Close backend connections."""
        await self.backend.close()


def create_state_manager(config: dict, agent_name: str) -> StateManager:
    """
    Factory function to create StateManager with appropriate backend.
    
    Args:
        config: Agent configuration with keys:
            - stateBackend: 'sqlite' | 'json' | 'engram'
            - statePath: Path to state file/database
        agent_name: Name of the agent
    
    Returns:
        StateManager instance
    """
    backend_type = config.get('stateBackend', 'sqlite')
    state_path = config.get('statePath', f'state/{agent_name}.db')
    
    if backend_type == 'sqlite':
        backend = SQLiteBackend(state_path)
    elif backend_type == 'json':
        backend = JSONBackend(state_path)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")
    
    return StateManager(backend, agent_name)
