"""Ollama LLM client for Anubis agents."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from pydantic import BaseModel

from anubis.core.config import OllamaConfig

logger = structlog.get_logger("anubis.llm")


class OllamaClient:
    """Client for interacting with a local Ollama instance."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()
        self._http = httpx.AsyncClient(
            base_url=self.config.host,
            timeout=self.config.timeout,
        )

    async def check_health(self) -> bool:
        """Check if Ollama is running and reachable."""
        try:
            resp = await self._http.get("/api/tags")
            return resp.status_code == 200
        except httpx.ConnectError:
            logger.warning("ollama_unreachable", host=self.config.host)
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models on the Ollama instance."""
        try:
            resp = await self._http.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
        except (httpx.HTTPError, KeyError):
            return []

    async def ensure_model(self) -> bool:
        """Check if the configured model is available, pull if not."""
        models = await self.list_models()
        model_names = [m.get("name", "") for m in models]

        if self.config.model in model_names:
            return True

        # Check for partial match (model without tag)
        base_name = self.config.model.split(":")[0]
        if any(base_name in name for name in model_names):
            return True

        logger.info("pulling_model", model=self.config.model)
        try:
            resp = await self._http.post(
                "/api/pull",
                json={"name": self.config.model},
                timeout=600,  # Model pulls can be slow
            )
            return resp.status_code == 200
        except httpx.HTTPError as e:
            logger.error("model_pull_failed", model=self.config.model, error=str(e))
            return False

    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request to Ollama.

        Args:
            messages: Chat messages in OpenAI format
            tools: Tool definitions for function calling
            temperature: Override default temperature

        Returns:
            Ollama response dict with message and optional tool_calls
        """
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_ctx": self.config.context_length,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await self._http.post("/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("chat_failed", error=str(e))
            return {"error": str(e)}

    async def generate(self, prompt: str, system: str = "") -> str:
        """Simple text generation (no chat format)."""
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_ctx": self.config.context_length,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = await self._http.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except httpx.HTTPError as e:
            logger.error("generate_failed", error=str(e))
            return f"Error: {e}"

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()


class ToolDefinition(BaseModel):
    """Schema for defining tools that agents can call."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_ollama_format(self) -> dict:
        """Convert to Ollama tool calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
