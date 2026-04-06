"""Tests for configuration management."""

from anubis.core.config import AnubisConfig, OllamaConfig


def test_default_config():
    config = AnubisConfig()
    assert config.ollama.model == "qwen3:14b"
    assert config.ollama.host == "http://localhost:11434"
    assert config.monitoring.poll_interval_seconds == 30
    assert config.agents.enable_auto_fix is False


def test_ollama_config_override():
    config = OllamaConfig(model="mistral:7b", temperature=0.5)
    assert config.model == "mistral:7b"
    assert config.temperature == 0.5
