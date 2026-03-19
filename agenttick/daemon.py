#!/usr/bin/env python3
"""
Agent Tick Daemon

Main orchestration of scheduler, event detector, and state manager.
Runs continuous tick loop with adaptive intervals.
"""

import asyncio
import argparse
import signal
import sys
from pathlib import Path
from typing import Optional

from .scheduler import AdaptiveScheduler
from .detector import EventDetector, Event
from .state import create_state_manager, StateManager


class AgentTickDaemon:
    """
    Main daemon that orchestrates all components.
    
    Runs continuous tick loop with:
    - Adaptive scheduler (1s/30s/5min intervals)
    - Event detection (file watch, git, custom)
    - State persistence (SQLite or JSON)
    """
    
    def __init__(self, config: dict, agent_name: str):
        """
        Initialize daemon with agent config.
        
        Args:
            config: Agent configuration dict
            agent_name: Name of the agent
        """
        self.config = config
        self.agent_name = agent_name
        
        # Components
        self.scheduler = AdaptiveScheduler(config.get('tickIntervals', {}))
        self.detector = EventDetector(config, agent_name)
        self.state_manager = create_state_manager(config, agent_name)
        
        # State
        self.running = False
        self.tick_count = 0
        self.tick_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the daemon."""
        print(f"[AgentTick:{self.agent_name}] Starting daemon...")
        print(f"[AgentTick:{self.agent_name}] Workspace: {self.config['workspaceRoot']}")
        print(f"[AgentTick:{self.agent_name}] Watch paths: {len(self.config.get('watchPaths', []))}")
        
        # Initialize components
        await self.detector.initialize()
        await self.state_manager.initialize()
        
        # Load previous state
        daemon_state = await self.state_manager.get_daemon_state()
        print(f"[AgentTick:{self.agent_name}] Loaded state: {daemon_state.get('scheduler_state', 'unknown')}")
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        # Start tick loop
        self.running = True
        self.tick_task = asyncio.create_task(self._tick_loop())
        
        import os
        print(f"[AgentTick:{self.agent_name}] Daemon started (PID: {os.getpid()})")
        
        # Wait for shutdown
        await self.tick_task
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self.stop(s))
            )
    
    async def _tick_loop(self):
        """Main tick loop with adaptive intervals."""
        while self.running:
            try:
                tick_start = asyncio.get_event_loop().time()
                
                # Execute tick
                await self._tick()
                
                # Calculate next interval
                interval_ms = self.scheduler.get_next_interval()
                interval_s = interval_ms / 1000
                
                # Sleep until next tick
                await asyncio.sleep(interval_s)
                
            except asyncio.CancelledError:
                print(f"[AgentTick:{self.agent_name}] Tick loop cancelled")
                break
            except Exception as e:
                print(f"[AgentTick:{self.agent_name}] Error in tick loop: {e}")
                import traceback
                traceback.print_exc()
                # Continue running despite errors
                await asyncio.sleep(5)
    
    async def _tick(self):
        """Execute a single tick."""
        self.tick_count += 1
        
        # Detect events
        events = await self.detector.detect()
        
        if events:
            print(f"[Tick:{self.agent_name}] Detected {len(events)} events")
            self.scheduler.mark_event()
            
            # Log events
            for event in events:
                # Truncate data for logging
                data_str = str(event.data)
                if len(data_str) > 100:
                    data_str = data_str[:100] + '...'
                print(f"  - {event.type} (tier {event.tier}): {data_str}")
                
                # Save to state
                await self.state_manager.save_event(event)
        
        # Update daemon state
        await self._update_daemon_state()
        
        # Log tick completion (only periodically or when events detected)
        if events or self.tick_count % 60 == 0:
            import time
            duration_ms = int((asyncio.get_event_loop().time() - time.time()) * 1000)
            scheduler_state = self.scheduler.get_state()
            print(f"[Tick:{self.agent_name}] Complete ({scheduler_state}, count: {self.tick_count})")
    
    async def _update_daemon_state(self):
        """Update and persist daemon state."""
        import time
        state = {
            'last_tick': int(time.time() * 1000),
            'scheduler_state': self.scheduler.get_state(),
            'tick_count': self.tick_count
        }
        await self.state_manager.save_daemon_state(state)
    
    async def stop(self, sig=None):
        """Stop the daemon gracefully."""
        if sig:
            print(f"[AgentTick:{self.agent_name}] Received signal {sig.name}, stopping...")
        else:
            print(f"[AgentTick:{self.agent_name}] Stopping daemon...")
        
        self.running = False
        
        if self.tick_task:
            self.tick_task.cancel()
            try:
                await self.tick_task
            except asyncio.CancelledError:
                pass
        
        # Stop components
        await self.detector.stop()
        await self.state_manager.close()
        
        print(f"[AgentTick:{self.agent_name}] Daemon stopped (total ticks: {self.tick_count})")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Agent Tick - Persistent daemon for AI agent autonomy')
    parser.add_argument('--agent', required=True, help='Agent name (loads agents/<name>.json)')
    parser.add_argument('--config-dir', default='agents', help='Directory containing agent configs')
    args = parser.parse_args()
    
    # Load agent config
    config_path = Path(args.config_dir) / f"{args.agent}.json"
    
    if not config_path.exists():
        print(f"Error: Config not found: {config_path}")
        print(f"Create agents/{args.agent}.json with your agent configuration")
        sys.exit(1)
    
    import json
    with open(config_path) as f:
        config = json.load(f)
    
    # Validate required fields
    required_fields = ['workspaceRoot', 'watchPaths']
    for field in required_fields:
        if field not in config:
            print(f"Error: Missing required field in config: {field}")
            sys.exit(1)
    
    # Create and start daemon
    daemon = AgentTickDaemon(config, args.agent)
    
    try:
        await daemon.start()
    except KeyboardInterrupt:
        await daemon.stop()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
