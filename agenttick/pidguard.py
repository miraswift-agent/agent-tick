"""
Single-Instance Guard for Agent Tick.

Prevents multiple daemon instances for the same agent via PID file
in the state/ directory.

Usage:
    guard = PIDGuard("mira", state_dir="state")
    if not guard.acquire(force=False):
        sys.exit(1)
    # ... run daemon ...
    guard.release()
"""

import os
import signal
import sys
from pathlib import Path
from typing import Optional


class PIDGuard:
    """
    Single-instance guard using PID files.

    Creates state/<agent_name>.pid containing the current process PID.
    On startup, checks if another instance is already running.
    """

    def __init__(self, agent_name: str, state_dir: str = "state"):
        """
        Initialize PID guard.

        Args:
            agent_name: Name of the agent (used for PID filename)
            state_dir: Directory to store PID files
        """
        self.agent_name = agent_name
        self.state_dir = Path(state_dir)
        self.pid_path = self.state_dir / f"{agent_name}.pid"
        self._acquired = False

    def acquire(self, force: bool = False) -> bool:
        """
        Attempt to acquire the single-instance lock.

        Args:
            force: If True, override existing PID file even if process is running

        Returns:
            True if lock acquired, False if another instance is running
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)

        existing_pid = self._read_pid()

        if existing_pid is not None:
            if force:
                print(
                    f"[PIDGuard:{self.agent_name}] Force flag set, "
                    f"overriding existing PID {existing_pid}"
                )
            elif self._is_process_running(existing_pid):
                print(
                    f"[PIDGuard:{self.agent_name}] Another instance is already "
                    f"running (PID: {existing_pid}). "
                    f"Use --force to override."
                )
                return False
            else:
                print(
                    f"[PIDGuard:{self.agent_name}] Stale PID file found "
                    f"(PID {existing_pid} not running), cleaning up"
                )

        # Write our PID
        self._write_pid()
        self._acquired = True
        print(
            f"[PIDGuard:{self.agent_name}] Lock acquired (PID: {os.getpid()})"
        )
        return True

    def release(self) -> None:
        """Release the lock by removing the PID file."""
        if self._acquired and self.pid_path.exists():
            try:
                # Only remove if it's our PID
                stored_pid = self._read_pid()
                if stored_pid == os.getpid():
                    self.pid_path.unlink()
                    print(
                        f"[PIDGuard:{self.agent_name}] Lock released"
                    )
            except OSError as e:
                print(
                    f"[PIDGuard:{self.agent_name}] Error releasing lock: {e}"
                )
        self._acquired = False

    def _read_pid(self) -> Optional[int]:
        """Read PID from the PID file."""
        if not self.pid_path.exists():
            return None
        try:
            content = self.pid_path.read_text().strip()
            return int(content)
        except (ValueError, OSError):
            return None

    def _write_pid(self) -> None:
        """Write current PID to the PID file."""
        self.pid_path.write_text(str(os.getpid()))

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """
        Check if a process with the given PID is still running.

        Args:
            pid: Process ID to check

        Returns:
            True if process exists and is running
        """
        try:
            # Signal 0 doesn't actually send a signal — just checks existence
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # No such process
            return False
        except PermissionError:
            # Process exists but we can't signal it (still running)
            return True
        except OSError:
            return False

    @staticmethod
    def status(agent_name: str, state_dir: str = "state") -> Optional[int]:
        """
        Check if an agent-tick instance is running.

        Args:
            agent_name: Name of the agent
            state_dir: Directory containing PID files

        Returns:
            PID if running, None if not
        """
        pid_path = Path(state_dir) / f"{agent_name}.pid"
        if not pid_path.exists():
            return None
        try:
            pid = int(pid_path.read_text().strip())
            if PIDGuard._is_process_running(pid):
                return pid
        except (ValueError, OSError):
            pass
        return None

    @staticmethod
    def stop(agent_name: str, state_dir: str = "state") -> bool:
        """
        Send SIGTERM to a running agent-tick instance.

        Args:
            agent_name: Name of the agent
            state_dir: Directory containing PID files

        Returns:
            True if signal sent, False if not running
        """
        pid = PIDGuard.status(agent_name, state_dir)
        if pid is None:
            print(f"[PIDGuard] No running instance found for '{agent_name}'")
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            print(f"[PIDGuard] Sent SIGTERM to PID {pid}")
            return True
        except (ProcessLookupError, PermissionError) as e:
            print(f"[PIDGuard] Could not signal PID {pid}: {e}")
            return False
