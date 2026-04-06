"""Anubis configuration management."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    """Configuration for Ollama LLM backend."""

    host: str = "http://localhost:11434"
    model: str = "qwen3:14b"
    temperature: float = 0.1
    context_length: int = 32768
    timeout: int = 120


class MonitoringConfig(BaseModel):
    """Configuration for system monitoring."""

    poll_interval_seconds: int = 30
    cpu_alert_threshold: float = 90.0
    memory_alert_threshold: float = 85.0
    disk_usage_alert_threshold: float = 90.0
    temp_alert_threshold_celsius: float = 85.0
    enable_smart_monitoring: bool = True
    enable_event_log_monitoring: bool = True


class DatabaseConfig(BaseModel):
    """Configuration for telemetry database."""

    url: str = "sqlite+aiosqlite:///anubis_telemetry.db"
    echo: bool = False


class ApiConfig(BaseModel):
    """Configuration for the FastAPI dashboard."""

    host: str = "127.0.0.1"
    port: int = 8484
    reload: bool = False


class AgentConfig(BaseModel):
    """Configuration for the agent system."""

    orchestrator_mode: Literal["supervisor", "hierarchical"] = "supervisor"
    max_agent_iterations: int = 10
    enable_auto_fix: bool = False  # Safety: require confirmation before fixes


class AnubisConfig(BaseModel):
    """Root configuration for Anubis."""

    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> AnubisConfig:
        """Load config from YAML file, falling back to defaults."""
        if path is None:
            path = Path("anubis.yaml")
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls.model_validate(data)
        return cls()

    def save(self, path: Path | None = None) -> None:
        """Save current config to YAML file."""
        if path is None:
            path = Path("anubis.yaml")
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)
