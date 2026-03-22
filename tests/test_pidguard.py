"""
Tests for single-instance PID guard (Issue #2).

Covers:
- PID file creation and cleanup
- Detection of running/stale processes
- Force override
- Status and stop helpers
"""

import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agenttick.pidguard import PIDGuard


@pytest.fixture
def state_dir():
    """Temporary state directory for PID files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestPIDGuard:
    def test_acquire_creates_pid_file(self, state_dir):
        """Acquiring the lock creates a PID file."""
        guard = PIDGuard("test-agent", state_dir=state_dir)
        assert guard.acquire() is True

        pid_path = Path(state_dir) / "test-agent.pid"
        assert pid_path.exists()
        assert int(pid_path.read_text().strip()) == os.getpid()

        guard.release()

    def test_release_removes_pid_file(self, state_dir):
        """Releasing the lock removes the PID file."""
        guard = PIDGuard("test-agent", state_dir=state_dir)
        guard.acquire()
        guard.release()

        pid_path = Path(state_dir) / "test-agent.pid"
        assert not pid_path.exists()

    def test_blocks_second_instance(self, state_dir):
        """Second acquire fails when first is still 'running'."""
        guard1 = PIDGuard("test-agent", state_dir=state_dir)
        assert guard1.acquire() is True

        guard2 = PIDGuard("test-agent", state_dir=state_dir)
        # Our own PID is running, so this should block
        assert guard2.acquire() is False

        guard1.release()

    def test_force_override(self, state_dir):
        """Force flag allows overriding existing lock."""
        guard1 = PIDGuard("test-agent", state_dir=state_dir)
        guard1.acquire()

        guard2 = PIDGuard("test-agent", state_dir=state_dir)
        assert guard2.acquire(force=True) is True

        # PID file now has our PID
        pid_path = Path(state_dir) / "test-agent.pid"
        assert int(pid_path.read_text().strip()) == os.getpid()

        guard2.release()

    def test_stale_pid_cleanup(self, state_dir):
        """Stale PID file (process not running) is cleaned up."""
        pid_path = Path(state_dir) / "test-agent.pid"
        # Write a PID that definitely doesn't exist
        pid_path.write_text("999999999")

        guard = PIDGuard("test-agent", state_dir=state_dir)
        # Should acquire since PID 999999999 is not running
        with patch.object(PIDGuard, "_is_process_running", return_value=False):
            assert guard.acquire() is True

        guard.release()

    def test_different_agents_dont_conflict(self, state_dir):
        """Different agent names use different PID files."""
        guard_a = PIDGuard("agent-a", state_dir=state_dir)
        guard_b = PIDGuard("agent-b", state_dir=state_dir)

        assert guard_a.acquire() is True
        assert guard_b.acquire() is True

        guard_a.release()
        guard_b.release()

    def test_creates_state_dir(self):
        """PID guard creates state directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "deep", "nested", "state")
            guard = PIDGuard("test", state_dir=nested)
            assert guard.acquire() is True
            assert Path(nested).exists()
            guard.release()

    def test_release_only_removes_own_pid(self, state_dir):
        """Release only removes PID file if it contains our PID."""
        guard = PIDGuard("test-agent", state_dir=state_dir)
        guard._acquired = True  # Pretend we acquired

        pid_path = Path(state_dir) / "test-agent.pid"
        pid_path.write_text("12345")  # Not our PID

        guard.release()
        # File should still exist since it's not our PID
        assert pid_path.exists()


class TestPIDGuardStatus:
    def test_status_running(self, state_dir):
        """Status returns PID when process is running."""
        guard = PIDGuard("test-agent", state_dir=state_dir)
        guard.acquire()

        pid = PIDGuard.status("test-agent", state_dir=state_dir)
        assert pid == os.getpid()

        guard.release()

    def test_status_not_running(self, state_dir):
        """Status returns None when no instance is running."""
        pid = PIDGuard.status("test-agent", state_dir=state_dir)
        assert pid is None

    def test_status_stale(self, state_dir):
        """Status returns None for stale PID files."""
        pid_path = Path(state_dir) / "test-agent.pid"
        pid_path.write_text("999999999")

        with patch.object(PIDGuard, "_is_process_running", return_value=False):
            pid = PIDGuard.status("test-agent", state_dir=state_dir)
            assert pid is None


class TestIsProcessRunning:
    def test_current_process_running(self):
        """Current process is detected as running."""
        assert PIDGuard._is_process_running(os.getpid()) is True

    def test_nonexistent_process(self):
        """Non-existent PID returns False."""
        assert PIDGuard._is_process_running(999999999) is False

    def test_pid_zero(self):
        """PID 0 is special (kernel) — may raise PermissionError."""
        # This varies by OS; just ensure it doesn't crash
        result = PIDGuard._is_process_running(0)
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
