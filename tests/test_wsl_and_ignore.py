"""
Tests for WSL-aware file watcher and ignore patterns (Issue #1).

Covers:
- WSL detection logic
- Windows-mounted path detection
- PollingObserver fallback decision
- Ignore pattern matching (substring, glob, fnmatch)
- FileWatchHandler filtering
- EventDetector with ignore patterns
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from agenttick.detector import (
    Event,
    EventDetector,
    FileWatchHandler,
    is_wsl,
    is_windows_mounted_path,
    should_use_polling,
    matches_ignore_pattern,
)
from agenttick.config import DEFAULT_IGNORE_PATTERNS


# --- WSL Detection Tests ---


class TestWSLDetection:
    """Tests for WSL environment detection."""

    @patch(
        "builtins.open",
        create=True,
    )
    def test_is_wsl_true(self, mock_open):
        """Detects WSL from /proc/version containing 'microsoft'."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(
            return_value="Linux version 5.15.0-1-microsoft-standard-WSL2"
        )
        assert is_wsl() is True

    @patch(
        "builtins.open",
        create=True,
    )
    def test_is_wsl_false(self, mock_open):
        """Non-WSL Linux returns False."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(
            return_value="Linux version 6.1.0-generic (gcc)"
        )
        assert is_wsl() is False

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_is_wsl_no_proc(self, mock_open):
        """Returns False if /proc/version doesn't exist (e.g., macOS)."""
        assert is_wsl() is False


class TestWindowsMountedPath:
    """Tests for /mnt/* Windows path detection."""

    def test_mnt_c(self):
        assert is_windows_mounted_path("/mnt/c/Users/tom") is True

    def test_mnt_d(self):
        assert is_windows_mounted_path("/mnt/d/projects") is True

    def test_not_mnt(self):
        assert is_windows_mounted_path("/home/user/workspace") is False

    def test_mnt_short(self):
        """Bare /mnt/ without a drive letter is not a Windows mount."""
        assert is_windows_mounted_path("/mnt/") is False

    def test_mnt_numeric(self):
        """/mnt/1 is not a Windows-style mount (drive letters are alpha)."""
        assert is_windows_mounted_path("/mnt/1/data") is False


class TestShouldUsePolling:
    """Tests for the polling fallback decision logic."""

    @patch("agenttick.detector.is_wsl", return_value=True)
    def test_wsl_with_mnt_path(self, mock_wsl):
        """WSL + /mnt/* path -> polling."""
        assert should_use_polling(["/mnt/c/code"], auto_fallback=True) is True

    @patch("agenttick.detector.is_wsl", return_value=True)
    def test_wsl_without_mnt_path(self, mock_wsl):
        """WSL + native Linux path -> no polling."""
        assert should_use_polling(["/home/user/code"], auto_fallback=True) is False

    @patch("agenttick.detector.is_wsl", return_value=False)
    def test_no_wsl(self, mock_wsl):
        """Non-WSL -> no polling regardless of path."""
        assert should_use_polling(["/mnt/c/code"], auto_fallback=True) is False

    @patch("agenttick.detector.is_wsl", return_value=True)
    def test_disabled_fallback(self, mock_wsl):
        """auto_fallback=False disables polling even in WSL with /mnt paths."""
        assert should_use_polling(["/mnt/c/code"], auto_fallback=False) is False

    @patch("agenttick.detector.is_wsl", return_value=True)
    def test_mixed_paths(self, mock_wsl):
        """If any path is /mnt/*, use polling."""
        paths = ["/home/user/workspace", "/mnt/c/shared"]
        assert should_use_polling(paths, auto_fallback=True) is True


# --- Ignore Pattern Tests ---


class TestIgnorePatterns:
    """Tests for the ignore pattern matching logic."""

    def test_substring_git(self):
        """/.git/ matches paths containing that substring."""
        assert matches_ignore_pattern("/home/user/repo/.git/config", ["/.git/"]) is True

    def test_substring_node_modules(self):
        assert (
            matches_ignore_pattern(
                "/project/node_modules/express/index.js", ["/node_modules/"]
            )
            is True
        )

    def test_substring_venv(self):
        assert (
            matches_ignore_pattern("/project/.venv/lib/python3.12/site.py", ["/.venv/"])
            is True
        )

    def test_substring_pycache(self):
        assert (
            matches_ignore_pattern(
                "/project/src/__pycache__/mod.cpython-312.pyc", ["/__pycache__/"]
            )
            is True
        )

    def test_glob_log_files(self):
        """**/*.log matches any .log file."""
        assert matches_ignore_pattern("/var/log/app.log", ["**/*.log"]) is True

    def test_glob_no_match(self):
        """Non-matching glob."""
        assert matches_ignore_pattern("/home/user/readme.md", ["**/*.log"]) is False

    def test_fnmatch_pyc(self):
        """*.pyc matches .pyc files by filename."""
        assert matches_ignore_pattern("/project/module.pyc", ["*.pyc"]) is True

    def test_no_pattern_match(self):
        """Clean path doesn't match any default patterns."""
        assert (
            matches_ignore_pattern(
                "/home/user/workspace/src/main.py", DEFAULT_IGNORE_PATTERNS
            )
            is False
        )

    def test_default_patterns_filter_git(self):
        assert (
            matches_ignore_pattern(
                "/repo/.git/objects/pack/p1", DEFAULT_IGNORE_PATTERNS
            )
            is True
        )

    def test_default_patterns_filter_node_modules(self):
        assert (
            matches_ignore_pattern(
                "/repo/node_modules/lodash/index.js", DEFAULT_IGNORE_PATTERNS
            )
            is True
        )

    def test_default_patterns_filter_venv(self):
        assert (
            matches_ignore_pattern(
                "/repo/.venv/bin/python3", DEFAULT_IGNORE_PATTERNS
            )
            is True
        )

    def test_default_patterns_filter_pycache(self):
        assert (
            matches_ignore_pattern(
                "/repo/src/__pycache__/main.cpython-312.pyc", DEFAULT_IGNORE_PATTERNS
            )
            is True
        )

    def test_default_patterns_filter_log(self):
        assert (
            matches_ignore_pattern("/repo/output/debug.log", DEFAULT_IGNORE_PATTERNS)
            is True
        )

    def test_empty_patterns(self):
        """Empty pattern list matches nothing."""
        assert matches_ignore_pattern("/any/path.py", []) is False


# --- EventDetector Ignore Integration ---


class TestEventDetectorIgnore:
    """Tests for EventDetector with ignore patterns configured."""

    def test_detector_has_default_patterns(self):
        """EventDetector uses default ignore patterns if none specified."""
        config = {
            "workspaceRoot": "/tmp",
            "watchPaths": [],
        }
        detector = EventDetector(config, "test")
        assert detector.ignore_patterns == DEFAULT_IGNORE_PATTERNS

    def test_detector_custom_patterns(self):
        """EventDetector uses custom ignore patterns when specified."""
        config = {
            "workspaceRoot": "/tmp",
            "watchPaths": [],
            "ignorePatterns": ["*.bak"],
        }
        detector = EventDetector(config, "test")
        assert detector.ignore_patterns == ["*.bak"]

    def test_file_watch_handler_filters(self):
        """FileWatchHandler skips events for ignored paths."""
        config = {
            "workspaceRoot": "/tmp",
            "watchPaths": [],
            "ignorePatterns": ["/.git/"],
        }
        detector = EventDetector(config, "test")
        handler = FileWatchHandler(detector)

        # Create a mock file event from .git directory
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/repo/.git/refs/heads/main"

        handler.on_modified(mock_event)

        # No events should be queued
        assert len(detector.event_queue) == 0

    def test_file_watch_handler_passes_normal(self):
        """FileWatchHandler allows events for non-ignored paths."""
        config = {
            "workspaceRoot": "/tmp",
            "watchPaths": [],
            "ignorePatterns": ["/.git/"],
        }
        detector = EventDetector(config, "test")
        handler = FileWatchHandler(detector)

        # Create a mock file event from a normal path
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/repo/src/main.py"

        handler.on_modified(mock_event)

        # Event should be queued
        assert len(detector.event_queue) == 1
        assert detector.event_queue[0].data["path"] == "/repo/src/main.py"

    def test_detector_watch_options(self):
        """EventDetector reads watchOptions from config."""
        config = {
            "workspaceRoot": "/tmp",
            "watchPaths": [],
            "watchOptions": {
                "autoPollingFallback": False,
                "pollingIntervalMs": 5000,
            },
        }
        detector = EventDetector(config, "test")
        assert detector.auto_polling_fallback is False
        assert detector.polling_interval_ms == 5000

    def test_detector_default_watch_options(self):
        """EventDetector uses default watchOptions."""
        config = {
            "workspaceRoot": "/tmp",
            "watchPaths": [],
        }
        detector = EventDetector(config, "test")
        assert detector.auto_polling_fallback is True
        assert detector.polling_interval_ms == 2000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
