"""Anubis configuration management."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    name: str = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: str = ""  # Empty for Ollama, required for cloud providers
    model: str = "qwen3:14b"
    temperature: float = 0.1
    context_length: int = 32768
    timeout: int = 120
    api_format: Literal["ollama", "openai"] = "ollama"  # API compatibility format


class OllamaConfig(BaseModel):
    """Configuration for Ollama LLM backend (legacy, still used for direct access)."""

    host: str = "http://localhost:11434"
    model: str = "qwen3:14b"
    temperature: float = 0.1
    context_length: int = 32768
    timeout: int = 120


class GroqConfig(BaseModel):
    """Configuration for Groq cloud LLM backend."""

    api_key: str = ""  # Set via GROQ_API_KEY env var or config
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    fallback_model: str = "qwen/qwen3-32b"
    temperature: float = 0.1
    timeout: int = 60
    max_retries: int = 3


class LLMRouterConfig(BaseModel):
    """Configuration for the multi-provider LLM router."""

    # Priority order: first available provider wins
    provider_priority: list[str] = Field(
        default_factory=lambda: ["ollama", "groq"]
    )
    # Retry settings
    max_retries_per_provider: int = 3
    retry_delay_seconds: float = 1.0
    # Circuit breaker: disable provider after N consecutive failures
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: int = 300


class MonitoringConfig(BaseModel):
    """Configuration for system monitoring."""

    poll_interval_seconds: int = 30
    cpu_alert_threshold: float = 90.0
    memory_alert_threshold: float = 85.0
    disk_usage_alert_threshold: float = 90.0
    temp_alert_threshold_celsius: float = 85.0
    enable_smart_monitoring: bool = True
    enable_event_log_monitoring: bool = True
    # Scheduled monitoring
    enable_watchdog: bool = True
    watchdog_interval_minutes: int = 5
    hourly_event_scan: bool = True
    daily_health_report: bool = True


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
    create_restore_points: bool = True  # Create restore point before destructive actions


class AnubisConfig(BaseModel):
    """Root configuration for Anubis."""

    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    groq: GroqConfig = Field(default_factory=GroqConfig)
    llm_router: LLMRouterConfig = Field(default_factory=LLMRouterConfig)
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
