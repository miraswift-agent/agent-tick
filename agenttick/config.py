"""
Pydantic-based configuration validation for Agent Tick.

Provides:
- Strict schema validation with helpful error messages
- Backward-compatible mapping for legacy tickIntervals keys
- Default ignore patterns for noisy directories
- WSL/polling fallback options
"""

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# Default ignore patterns for noisy directories
DEFAULT_IGNORE_PATTERNS: List[str] = [
    "/.git/",
    "/node_modules/",
    "/.venv/",
    "/__pycache__/",
    "**/*.log",
]

# Legacy key mapping: old key -> new key
LEGACY_TICK_KEYS = {
    "active": "active_interval_ms",
    "idle": "idle_interval_ms",
    "sleep": "sleep_interval_ms",
}


class WatchOptions(BaseModel):
    """Configuration for file watching behavior."""

    auto_polling_fallback: bool = Field(
        default=True,
        alias="autoPollingFallback",
        description="Auto-detect WSL/mounted paths and fall back to PollingObserver",
    )
    polling_interval_ms: int = Field(
        default=2000,
        alias="pollingIntervalMs",
        ge=100,
        le=60000,
        description="Polling interval in ms when using PollingObserver",
    )

    model_config = {"populate_by_name": True}


class TickIntervals(BaseModel):
    """Tick interval configuration with legacy key support."""

    active_interval_ms: int = Field(
        default=1000,
        ge=100,
        le=60000,
        description="Tick interval when active (ms)",
    )
    idle_interval_ms: int = Field(
        default=30000,
        ge=1000,
        le=600000,
        description="Tick interval when idle (ms)",
    )
    sleep_interval_ms: int = Field(
        default=300000,
        ge=10000,
        le=3600000,
        description="Tick interval during sleep hours (ms)",
    )
    sleep_hours: Tuple[int, int] = Field(
        default=(2, 6),
        description="Sleep hours range [start, end] in 24h format",
    )
    ultra_quiet_threshold_ms: int = Field(
        default=1800000,
        ge=60000,
        description="Idle duration before ultra-quiet mode (ms)",
    )
    ultra_quiet_max_ms: int = Field(
        default=900000,
        ge=60000,
        description="Maximum interval in ultra-quiet mode (ms)",
    )
    system_load_threshold: int = Field(
        default=70,
        ge=10,
        le=100,
        description="CPU percentage to trigger throttling",
    )

    @field_validator("sleep_hours", mode="before")
    @classmethod
    def validate_sleep_hours(cls, v: Any) -> Tuple[int, int]:
        """Validate sleep hours are valid 24h range."""
        if isinstance(v, (list, tuple)):
            if len(v) != 2:
                raise ValueError("sleep_hours must be [start, end] (two integers)")
            start, end = int(v[0]), int(v[1])
            if not (0 <= start <= 23 and 0 <= end <= 23):
                raise ValueError(
                    f"sleep_hours values must be 0-23, got [{start}, {end}]"
                )
            return (start, end)
        raise ValueError("sleep_hours must be a list or tuple of two integers")


class GitMonitoring(BaseModel):
    """Git monitoring configuration."""

    enabled: bool = True
    interval: int = Field(default=5000, ge=1000)


class MonitoringConfig(BaseModel):
    """Monitoring section configuration."""

    git: GitMonitoring = Field(default_factory=GitMonitoring)


class HandlerConfig(BaseModel):
    """Handler configuration."""

    type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """
    Complete agent configuration with validation.

    Supports backward-compatible mapping for legacy tickIntervals keys
    (active, idle, sleep) to their *_interval_ms equivalents.
    """

    agent_name: str = Field(alias="agentName", default="agent")
    workspace_root: str = Field(alias="workspaceRoot")
    state_backend: str = Field(alias="stateBackend", default="sqlite")
    state_path: str = Field(alias="statePath", default="")

    tick_intervals: TickIntervals = Field(
        alias="tickIntervals", default_factory=TickIntervals
    )
    watch_paths: List[str] = Field(alias="watchPaths", default_factory=list)
    watch_options: WatchOptions = Field(
        alias="watchOptions", default_factory=WatchOptions
    )
    ignore_patterns: List[str] = Field(
        alias="ignorePatterns", default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS)
    )

    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    handlers: List[HandlerConfig] = Field(default_factory=list)
    health_check_port: Optional[int] = Field(alias="healthCheckPort", default=None)

    model_config = {"populate_by_name": True, "extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def map_legacy_tick_keys(cls, data: Any) -> Any:
        """Map legacy tickIntervals keys to new format with deprecation warning."""
        if not isinstance(data, dict):
            return data

        tick = data.get("tickIntervals", {})
        if not isinstance(tick, dict):
            return data

        mapped_any = False
        for old_key, new_key in LEGACY_TICK_KEYS.items():
            if old_key in tick and new_key not in tick:
                tick[new_key] = tick.pop(old_key)
                mapped_any = True

        if mapped_any:
            warnings.warn(
                "tickIntervals uses legacy keys (active, idle, sleep). "
                "Please update to active_interval_ms, idle_interval_ms, "
                "sleep_interval_ms. Legacy keys will be removed in v3.0.",
                DeprecationWarning,
                stacklevel=2,
            )

        data["tickIntervals"] = tick
        return data

    @field_validator("workspace_root", mode="after")
    @classmethod
    def validate_workspace_root(cls, v: str) -> str:
        """Validate workspace root exists."""
        expanded = str(Path(v).expanduser())
        if not Path(expanded).exists():
            warnings.warn(
                f"workspaceRoot does not exist: {expanded}",
                UserWarning,
                stacklevel=2,
            )
        return expanded

    @model_validator(mode="after")
    def set_default_state_path(self) -> "AgentConfig":
        """Set default state path based on agent name and backend."""
        if not self.state_path:
            ext = "db" if self.state_backend == "sqlite" else "json"
            self.state_path = f"state/{self.agent_name}.{ext}"
        return self

    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Convert back to the dict format expected by existing components.

        This allows validated config to be passed to components that
        still expect raw dict access.
        """
        return {
            "agentName": self.agent_name,
            "workspaceRoot": self.workspace_root,
            "stateBackend": self.state_backend,
            "statePath": self.state_path,
            "tickIntervals": {
                "active_interval_ms": self.tick_intervals.active_interval_ms,
                "idle_interval_ms": self.tick_intervals.idle_interval_ms,
                "sleep_interval_ms": self.tick_intervals.sleep_interval_ms,
                "sleep_hours": list(self.tick_intervals.sleep_hours),
                "ultra_quiet_threshold_ms": self.tick_intervals.ultra_quiet_threshold_ms,
                "ultra_quiet_max_ms": self.tick_intervals.ultra_quiet_max_ms,
                "system_load_threshold": self.tick_intervals.system_load_threshold,
            },
            "watchPaths": self.watch_paths,
            "watchOptions": {
                "autoPollingFallback": self.watch_options.auto_polling_fallback,
                "pollingIntervalMs": self.watch_options.polling_interval_ms,
            },
            "ignorePatterns": self.ignore_patterns,
            "monitoring": {
                "git": {
                    "enabled": self.monitoring.git.enabled,
                    "interval": self.monitoring.git.interval,
                }
            },
            "handlers": [
                {"type": h.type, "config": h.config} for h in self.handlers
            ],
            "healthCheckPort": self.health_check_port,
        }


def load_and_validate_config(raw_config: Dict[str, Any]) -> AgentConfig:
    """
    Load and validate agent configuration.

    Args:
        raw_config: Raw configuration dictionary (from JSON file)

    Returns:
        Validated AgentConfig instance

    Raises:
        pydantic.ValidationError: If config is invalid
    """
    return AgentConfig(**raw_config)
