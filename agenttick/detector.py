"""
Event Detector for Agent Tick

Detects events via file watching (watchdog), git monitoring (GitPython),
and optional custom handlers.
"""

import asyncio
from pathlib import Path
from typing import Callable, Dict, List, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
import git


class Event:
    """Represents a detected event."""
    
    def __init__(self, 
                 type: str,
                 tier: int,
                 data: dict,
                 source: str,
                 timestamp: Optional[float] = None):
        """
        Create an event.
        
        Args:
            type: Event type (e.g., 'workspace:file_change')
            tier: Significance tier (1=high, 2=medium, 3=low)
            data: Event-specific data
            source: Source of detection (e.g., 'file_watcher', 'git_status')
            timestamp: Unix timestamp in milliseconds (auto-generated if None)
        """
        import time
        self.type = type
        self.tier = tier
        self.data = data
        self.source = source
        self.timestamp = timestamp or int(time.time() * 1000)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'type': self.type,
            'tier': self.tier,
            'data': self.data,
            'source': self.source,
            'timestamp': self.timestamp
        }


class FileWatchHandler(FileSystemEventHandler):
    """Handles file system events from watchdog."""
    
    def __init__(self, detector: 'EventDetector'):
        self.detector = detector
    
    def on_modified(self, event):
        """Called when a file is modified."""
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        
        # Ignore hidden files and temp files
        if path.name.startswith('.') or path.name.endswith('~'):
            return
        
        tier = self.detector.infer_tier_from_path(str(path))
        
        self.detector.emit_event(Event(
            type='workspace:file_change',
            tier=tier,
            data={'path': str(path)},
            source='file_watcher'
        ))


class EventDetector:
    """
    Detects events via multiple sources:
    - File system watching (watchdog)
    - Git status monitoring (GitPython)
    - Custom event sources (plugins)
    """
    
    def __init__(self, config: dict, agent_name: str):
        """
        Initialize event detector.
        
        Args:
            config: Agent configuration dict with keys:
                - workspaceRoot: Base directory path
                - watchPaths: List of directories to monitor
                - monitoring: Dict with git/email/etc configs
            agent_name: Name of the agent (for logging)
        """
        self.config = config
        self.agent_name = agent_name
        self.workspace_root = Path(config['workspaceRoot'])
        self.watch_paths = [Path(p) for p in config.get('watchPaths', [])]
        
        # Event queue
        self.event_queue: List[Event] = []
        self.event_callbacks: List[Callable] = []
        
        # File watcher
        self.observer: Optional[Observer] = None
        self.file_handler: Optional[FileWatchHandler] = None
        
        # Git monitoring
        self.git_repo: Optional[git.Repo] = None
        self.git_enabled = config.get('monitoring', {}).get('git', {}).get('enabled', True)
        
    async def initialize(self):
        """Initialize file watching and git monitoring."""
        print(f"[EventDetector:{self.agent_name}] Initializing...")
        
        # Set up file watching
        if self.watch_paths:
            self._setup_file_watcher()
        
        # Set up git monitoring
        if self.git_enabled:
            self._setup_git_monitoring()
        
        print(f"[EventDetector:{self.agent_name}] Initialized ({len(self.watch_paths)} paths watched)")
    
    def _setup_file_watcher(self):
        """Set up watchdog file system observer."""
        self.observer = Observer()
        self.file_handler = FileWatchHandler(self)
        
        for path in self.watch_paths:
            if path.exists():
                self.observer.schedule(self.file_handler, str(path), recursive=True)
                print(f"[EventDetector:{self.agent_name}] Watching: {path}")
            else:
                print(f"[EventDetector:{self.agent_name}] Warning: Path not found: {path}")
        
        self.observer.start()
    
    def _setup_git_monitoring(self):
        """Set up git repository monitoring."""
        try:
            self.git_repo = git.Repo(self.workspace_root, search_parent_directories=True)
            print(f"[EventDetector:{self.agent_name}] Git monitoring enabled")
        except git.InvalidGitRepositoryError:
            print(f"[EventDetector:{self.agent_name}] Warning: Not a git repository: {self.workspace_root}")
            self.git_repo = None
    
    async def check_git_status(self) -> Optional[Event]:
        """
        Check git status for uncommitted changes.
        
        Returns:
            Event if there are uncommitted changes, None otherwise
        """
        if not self.git_repo:
            return None
        
        try:
            # Check for uncommitted changes
            if self.git_repo.is_dirty(untracked_files=True):
                # Get detailed status
                changed = [item.a_path for item in self.git_repo.index.diff(None)]
                staged = [item.a_path for item in self.git_repo.index.diff('HEAD')]
                untracked = self.git_repo.untracked_files
                
                return Event(
                    type='workspace:git_uncommitted',
                    tier=2,  # Medium significance by default
                    data={
                        'changed': changed,
                        'staged': staged,
                        'untracked': untracked,
                        'total': len(changed) + len(staged) + len(untracked)
                    },
                    source='git_status'
                )
        except Exception as e:
            # Git commands can fail for many reasons - graceful degradation
            print(f"[EventDetector:{self.agent_name}] Git status check failed: {e}")
        
        return None
    
    def infer_tier_from_path(self, path: str) -> int:
        """
        Infer event tier from file path using heuristics.
        
        Args:
            path: File path
            
        Returns:
            int: Tier (1=high, 2=medium, 3=low)
        """
        path_lower = path.lower()
        
        # Tier 1: High significance
        if 'memory/' in path_lower and any(x in path_lower for x in ['preservation', 'gap', 'critical']):
            return 1
        if any(x in path_lower for x in ['identity.md', 'soul.md', 'strategy.md']):
            return 1
        
        # Tier 3: Low significance (journal, routine)
        if 'journal/' in path_lower:
            return 3
        if any(x in path_lower for x in ['.log', '.tmp', 'test_']):
            return 3
        
        # Tier 2: Medium significance (default)
        return 2
    
    def emit_event(self, event: Event):
        """
        Emit an event to the queue and notify callbacks.
        
        Args:
            event: Event to emit
        """
        self.event_queue.append(event)
        
        # Notify callbacks
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"[EventDetector:{self.agent_name}] Callback error: {e}")
    
    def on_event(self, callback: Callable[[Event], None]):
        """
        Register a callback for event notifications.
        
        Args:
            callback: Function to call when events are detected
        """
        self.event_callbacks.append(callback)
    
    async def detect(self) -> List[Event]:
        """
        Collect all pending events (from queue and git check).
        
        Returns:
            List of Event objects
        """
        events = self.event_queue.copy()
        self.event_queue.clear()
        
        # Check git status
        git_event = await self.check_git_status()
        if git_event:
            events.append(git_event)
        
        return events
    
    async def stop(self):
        """Stop file watching and cleanup."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            print(f"[EventDetector:{self.agent_name}] File watcher stopped")
