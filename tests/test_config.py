"""
Tests for Pydantic config validation (Issue #1).

Covers:
- Valid config loading
- Legacy key mapping with deprecation warnings
- Invalid config error messages
- Default ignore patterns
- Watch options
- Backward compatibility (old configs still work)
"""

import warnings
import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError

from agenttick.config import (
    AgentConfig,
    TickIntervals,
    WatchOptions,
    load_and_validate_config,
    DEFAULT_IGNORE_PATTERNS,
    LEGACY_TICK_KEYS,
)


@pytest.fixture
def valid_config(tmp_path):
    """A fully valid modern config dict."""
    return {
        "agentName": "test-agent",
        "workspaceRoot": str(tmp_path),
        "stateBackend": "sqlite",
        "statePath": "state/test.db",
        "tickIntervals": {
            "active_interval_ms": 1000,
            "idle_interval_ms": 30000,
            "sleep_interval_ms": 300000,
            "sleep_hours": [2, 6],
            "system_load_threshold": 70,
        },
        "watchPaths": [str(tmp_path)],
        "watchOptions": {
            "autoPollingFallback": True,
            "pollingIntervalMs": 2000,
        },
        "ignorePatterns": ["/.git/", "/node_modules/"],
        "monitoring": {"git": {"enabled": True}},
        "handlers": [
            {
                "type": "freeze_detector",
                "config": {"freeze_threshold_ms": 1800000},
            }
        ],
    }


@pytest.fixture
def legacy_config(tmp_path):
    """A config using legacy tickIntervals keys (active, idle, sleep)."""
    return {
        "agentName": "legacy-agent",
        "workspaceRoot": str(tmp_path),
        "tickIntervals": {
            "active": 2000,
            "idle": 15000,
            "sleep": 600000,
        },
        "watchPaths": [str(tmp_path)],
    }


# --- Valid Config Tests ---


def test_valid_config_loads(valid_config):
    """Modern config loads without error."""
    cfg = load_and_validate_config(valid_config)
    assert cfg.agent_name == "test-agent"
    assert cfg.tick_intervals.active_interval_ms == 1000
    assert cfg.tick_intervals.sleep_hours == (2, 6)


def test_minimal_config(tmp_path):
    """Minimal config with just workspaceRoot and watchPaths."""
    cfg = load_and_validate_config(
        {"workspaceRoot": str(tmp_path), "watchPaths": [str(tmp_path)]}
    )
    assert cfg.agent_name == "agent"  # default
    assert cfg.tick_intervals.active_interval_ms == 1000  # default
    assert cfg.state_backend == "sqlite"  # default


def test_default_state_path_sqlite(tmp_path):
    """Default statePath is set from agent name and backend."""
    cfg = load_and_validate_config(
        {
            "agentName": "mybot",
            "workspaceRoot": str(tmp_path),
            "watchPaths": [],
        }
    )
    assert cfg.state_path == "state/mybot.db"


def test_default_state_path_json(tmp_path):
    """Default statePath for JSON backend."""
    cfg = load_and_validate_config(
        {
            "agentName": "mybot",
            "workspaceRoot": str(tmp_path),
            "stateBackend": "json",
            "watchPaths": [],
        }
    )
    assert cfg.state_path == "state/mybot.json"


def test_default_ignore_patterns(tmp_path):
    """Default ignore patterns are applied when none specified."""
    cfg = load_and_validate_config(
        {"workspaceRoot": str(tmp_path), "watchPaths": []}
    )
    assert cfg.ignore_patterns == DEFAULT_IGNORE_PATTERNS
    assert "/.git/" in cfg.ignore_patterns
    assert "/node_modules/" in cfg.ignore_patterns


def test_custom_ignore_patterns(tmp_path):
    """Custom ignore patterns override defaults."""
    cfg = load_and_validate_config(
        {
            "workspaceRoot": str(tmp_path),
            "watchPaths": [],
            "ignorePatterns": ["*.bak", "/build/"],
        }
    )
    assert cfg.ignore_patterns == ["*.bak", "/build/"]


def test_watch_options_defaults(tmp_path):
    """Watch options have sensible defaults."""
    cfg = load_and_validate_config(
        {"workspaceRoot": str(tmp_path), "watchPaths": []}
    )
    assert cfg.watch_options.auto_polling_fallback is True
    assert cfg.watch_options.polling_interval_ms == 2000


def test_watch_options_custom(tmp_path):
    """Custom watch options are respected."""
    cfg = load_and_validate_config(
        {
            "workspaceRoot": str(tmp_path),
            "watchPaths": [],
            "watchOptions": {
                "autoPollingFallback": False,
                "pollingIntervalMs": 5000,
            },
        }
    )
    assert cfg.watch_options.auto_polling_fallback is False
    assert cfg.watch_options.polling_interval_ms == 5000


def test_to_legacy_dict(valid_config):
    """to_legacy_dict produces the format existing components expect."""
    cfg = load_and_validate_config(valid_config)
    d = cfg.to_legacy_dict()

    assert d["agentName"] == "test-agent"
    assert d["tickIntervals"]["active_interval_ms"] == 1000
    assert d["watchOptions"]["autoPollingFallback"] is True
    assert d["ignorePatterns"] == ["/.git/", "/node_modules/"]
    assert len(d["handlers"]) == 1
    assert d["handlers"][0]["type"] == "freeze_detector"


def test_handlers_loaded(valid_config):
    """Handlers are parsed correctly."""
    cfg = load_and_validate_config(valid_config)
    assert len(cfg.handlers) == 1
    assert cfg.handlers[0].type == "freeze_detector"
    assert cfg.handlers[0].config["freeze_threshold_ms"] == 1800000


def test_extra_fields_allowed(tmp_path):
    """Extra fields (like publishing) don't cause errors."""
    cfg = load_and_validate_config(
        {
            "workspaceRoot": str(tmp_path),
            "watchPaths": [],
            "publishing": {"blog": {"enabled": True}},
            "healthCheckPort": 41114,
        }
    )
    assert cfg.health_check_port == 41114


# --- Legacy Key Mapping Tests ---


def test_legacy_keys_mapped(legacy_config):
    """Legacy keys (active, idle, sleep) are mapped to *_interval_ms."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cfg = load_and_validate_config(legacy_config)

        assert cfg.tick_intervals.active_interval_ms == 2000
        assert cfg.tick_intervals.idle_interval_ms == 15000
        assert cfg.tick_intervals.sleep_interval_ms == 600000

        # Check deprecation warning was emitted
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert "legacy keys" in str(deprecation_warnings[0].message).lower()


def test_legacy_keys_no_override(tmp_path):
    """Legacy keys don't override new keys if both present."""
    cfg = load_and_validate_config(
        {
            "workspaceRoot": str(tmp_path),
            "watchPaths": [],
            "tickIntervals": {
                "active": 999,
                "active_interval_ms": 1500,
            },
        }
    )
    # New key takes precedence (legacy key not mapped when new key exists)
    assert cfg.tick_intervals.active_interval_ms == 1500


def test_mira_json_backward_compatible(tmp_path):
    """The existing mira.json config (with legacy keys) still works."""
    mira_config = {
        "agentName": "mira",
        "workspaceRoot": str(tmp_path),
        "tickIntervals": {
            "active": 1000,
            "idle": 30000,
            "sleep": 300000,
        },
        "watchPaths": [str(tmp_path)],
        "monitoring": {"git": {"enabled": True, "interval": 5000}},
        "publishing": {
            "blog": {"enabled": True, "maxPerWeek": 2},
        },
        "healthCheckPort": 41114,
    }
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        cfg = load_and_validate_config(mira_config)

    assert cfg.agent_name == "mira"
    assert cfg.tick_intervals.active_interval_ms == 1000
    assert cfg.tick_intervals.idle_interval_ms == 30000


# --- Invalid Config Tests ---


def test_missing_workspace_root():
    """Missing workspaceRoot produces clear error."""
    with pytest.raises(ValidationError) as exc_info:
        load_and_validate_config({"watchPaths": []})

    errors = exc_info.value.errors()
    assert any("workspaceRoot" in str(e) for e in errors)


def test_invalid_sleep_hours(tmp_path):
    """Invalid sleep_hours produces clear error."""
    with pytest.raises(ValidationError) as exc_info:
        load_and_validate_config(
            {
                "workspaceRoot": str(tmp_path),
                "watchPaths": [],
                "tickIntervals": {"sleep_hours": [25, 6]},
            }
        )

    errors = exc_info.value.errors()
    assert any("sleep_hours" in str(e) for e in errors)


def test_invalid_sleep_hours_length(tmp_path):
    """sleep_hours with wrong number of elements."""
    with pytest.raises(ValidationError):
        load_and_validate_config(
            {
                "workspaceRoot": str(tmp_path),
                "watchPaths": [],
                "tickIntervals": {"sleep_hours": [2, 6, 10]},
            }
        )


def test_interval_too_low(tmp_path):
    """Intervals below minimum produce validation error."""
    with pytest.raises(ValidationError):
        load_and_validate_config(
            {
                "workspaceRoot": str(tmp_path),
                "watchPaths": [],
                "tickIntervals": {"active_interval_ms": 10},  # min is 100
            }
        )


def test_interval_too_high(tmp_path):
    """Intervals above maximum produce validation error."""
    with pytest.raises(ValidationError):
        load_and_validate_config(
            {
                "workspaceRoot": str(tmp_path),
                "watchPaths": [],
                "tickIntervals": {"active_interval_ms": 999999},  # max is 60000
            }
        )


def test_polling_interval_bounds(tmp_path):
    """Polling interval must be within bounds."""
    with pytest.raises(ValidationError):
        load_and_validate_config(
            {
                "workspaceRoot": str(tmp_path),
                "watchPaths": [],
                "watchOptions": {"pollingIntervalMs": 50},  # min is 100
            }
        )


def test_system_load_threshold_bounds(tmp_path):
    """System load threshold must be 10-100."""
    with pytest.raises(ValidationError):
        load_and_validate_config(
            {
                "workspaceRoot": str(tmp_path),
                "watchPaths": [],
                "tickIntervals": {"system_load_threshold": 5},
            }
        )


# --- TickIntervals Model Tests ---


def test_tick_intervals_defaults():
    """TickIntervals model has sensible defaults."""
    ti = TickIntervals()
    assert ti.active_interval_ms == 1000
    assert ti.idle_interval_ms == 30000
    assert ti.sleep_interval_ms == 300000
    assert ti.sleep_hours == (2, 6)
    assert ti.ultra_quiet_threshold_ms == 1800000
    assert ti.ultra_quiet_max_ms == 900000
    assert ti.system_load_threshold == 70


# --- WatchOptions Model Tests ---


def test_watch_options_defaults():
    """WatchOptions model has sensible defaults."""
    wo = WatchOptions()
    assert wo.auto_polling_fallback is True
    assert wo.polling_interval_ms == 2000
