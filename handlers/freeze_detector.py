"""
Freeze Detection Handler

Detects when Mira commits to work but doesn't execute (autonomy freeze pattern).

Pattern:
1. Git activity detected (active state)
2. Same uncommitted files persist for >30min
3. No new commits during that time
4. Alert via OpenClaw wake event
"""

import time
import subprocess
from typing import Dict, Optional


class FreezeDetector:
    """
    Detects autonomy freeze pattern and alerts.
    """
    
    def __init__(self, config: dict):
        """
        Initialize freeze detector.
        
        Args:
            config: Handler config with:
                - freeze_threshold_ms: Time with no progress = freeze (default 30min)
                - alert_method: 'cron_wake' or 'log_only'
                - work_hours: [start, end] in 24h format (default [6, 23])
        """
        self.config = config
        self.freeze_threshold_ms = config.get('freeze_threshold_ms', 1800000)  # 30min
        self.alert_method = config.get('alert_method', 'cron_wake')
        self.work_hours = config.get('work_hours', [6, 23])
        
        # State tracking
        self.first_uncommitted_detected: Optional[int] = None
        self.last_uncommitted_files: Optional[str] = None
        self.last_commit_time: Optional[int] = None
        self.freeze_alerted = False
    
    def is_work_hours(self) -> bool:
        """Check if currently in work hours."""
        from datetime import datetime
        hour = datetime.now().hour
        return self.work_hours[0] <= hour < self.work_hours[1]
    
    def handle_event(self, event: dict):
        """
        Process an event and check for freeze pattern.
        
        Args:
            event: Event dict with type, tier, data, timestamp
        """
        if event['type'] != 'workspace:git_uncommitted':
            return
        
        now = event['timestamp']
        
        # Not in work hours - reset state
        if not self.is_work_hours():
            self._reset_state()
            return
        
        # Get file signature (for detecting if same files stuck)
        files_signature = self._get_files_signature(event['data'])
        
        # First time seeing uncommitted files
        if self.first_uncommitted_detected is None:
            self.first_uncommitted_detected = now
            self.last_uncommitted_files = files_signature
            self.freeze_alerted = False
            return
        
        # Files changed - work is happening, reset
        if files_signature != self.last_uncommitted_files:
            self._reset_state()
            self.first_uncommitted_detected = now
            self.last_uncommitted_files = files_signature
            return
        
        # Same files, check duration
        duration_ms = now - self.first_uncommitted_detected
        
        if duration_ms > self.freeze_threshold_ms and not self.freeze_alerted:
            self._alert_freeze(event, duration_ms)
            self.freeze_alerted = True
    
    def _get_files_signature(self, data: dict) -> str:
        """Create signature of uncommitted files for comparison."""
        changed = sorted(data.get('changed', []))
        staged = sorted(data.get('staged', []))
        untracked = sorted(data.get('untracked', []))
        return f"{','.join(changed)}|{','.join(staged)}|{','.join(untracked)}"
    
    def _reset_state(self):
        """Reset freeze detection state."""
        self.first_uncommitted_detected = None
        self.last_uncommitted_files = None
        self.freeze_alerted = False
    
    def _alert_freeze(self, event: dict, duration_ms: int):
        """Send freeze alert."""
        duration_min = duration_ms / 60000
        
        files = event['data'].get('changed', []) + event['data'].get('staged', [])
        files_list = ', '.join(files[:5])
        if len(files) > 5:
            files_list += f" (+{len(files)-5} more)"
        
        message = (
            f"🧊 FREEZE DETECTED: Same uncommitted files for {duration_min:.0f} minutes.\n"
            f"Files: {files_list}\n"
            f"Pattern: Active git state, but no commits/progress.\n"
            f"Action: Commit work or take next step?"
        )
        
        print(f"[FreezeDetector] {message}")
        
        if self.alert_method == 'cron_wake':
            self._send_wake_event(message)
        
    def _send_wake_event(self, message: str):
        """Send wake event to OpenClaw via cron tool."""
        try:
            # Use openclaw CLI to send wake event
            cmd = ['openclaw', 'cron', 'wake', '--text', message, '--mode', 'now']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                print(f"[FreezeDetector] Wake event sent successfully")
            else:
                print(f"[FreezeDetector] Wake event failed: {result.stderr}")
        
        except Exception as e:
            print(f"[FreezeDetector] Error sending wake event: {e}")
