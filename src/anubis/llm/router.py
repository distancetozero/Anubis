"""Multi-provider LLM router with failover, retry, and circuit breaking.

Routes requests through available providers in priority order:
1. Local Ollama (free, private, no internet)
2. Groq (free tier, blazing fast)
3. Any OpenAI-compatible provider

All providers speak the same OpenAI chat completions format.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from anubis.core.config import AnubisConfig, GroqConfig, LLMRouterConfig, OllamaConfig

logger = structlog.get_logger("anubis.llm.router")


@dataclass
class ProviderState:
    """Runtime state for a provider (circuit breaker tracking)."""

    name: str
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False  # Circuit breaker open = provider disabled
    total_requests: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0


@dataclass
class LLMResponse:
    """Unified response from any provider."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def to_message_dict(self) -> dict[str, Any]:
        """Convert to a message dict for appending to conversation history."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg


class LLMProvider:
    """Base class for LLM providers using OpenAI-compatible API."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )

    async def check_health(self) -> bool:
        """Check if the provider is reachable."""
        raise NotImplementedError

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a chat request. Returns unified LLMResponse."""
        raise NotImplementedError

    async def close(self) -> None:
        await self._http.aclose()


class OllamaProvider(LLMProvider):
    """Local Ollama provider."""

    def __init__(self, config: OllamaConfig) -> None:
        super().__init__(
            name="ollama",
            base_url=config.host,
            model=config.model,
            temperature=config.temperature,
            timeout=config.timeout,
        )
        self._config = config

    async def check_health(self) -> bool:
        try:
            resp = await self._http.get("/api/tags")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        start = time.monotonic()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_ctx": self._config.context_length,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await self._http.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            elapsed = (time.monotonic() - start) * 1000

            return LLMResponse(
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls", []),
                provider="ollama",
                model=self.model,
                latency_ms=elapsed,
            )
        except (httpx.HTTPError, Exception) as e:
            elapsed = (time.monotonic() - start) * 1000
            return LLMResponse(
                provider="ollama",
                model=self.model,
                latency_ms=elapsed,
                error=str(e),
            )


class GroqProvider(LLMProvider):
    """Groq cloud provider (OpenAI-compatible)."""

    def __init__(self, config: GroqConfig) -> None:
        api_key = config.api_key or os.environ.get("GROQ_API_KEY", "")
        super().__init__(
            name="groq",
            base_url=config.base_url,
            model=config.model,
            api_key=api_key,
            temperature=config.temperature,
            timeout=config.timeout,
        )
        self._config = config
        self._has_key = bool(api_key)

    async def check_health(self) -> bool:
        if not self._has_key:
            logger.debug("groq_no_api_key")
            return False
        try:
            resp = await self._http.get("/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        if not self._has_key:
            return LLMResponse(provider="groq", model=self.model, error="No API key")

        start = time.monotonic()

        # OpenAI-compatible format
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await self._http.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            elapsed = (time.monotonic() - start) * 1000

            # Normalize tool calls format (preserve id/type for OpenAI-compat APIs)
            tool_calls = []
            for tc in msg.get("tool_calls", []):
                normalized = {
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", {}),
                    }
                }
                # Preserve id and type — required by OpenAI-compatible APIs
                if "id" in tc:
                    normalized["id"] = tc["id"]
                if "type" in tc:
                    normalized["type"] = tc["type"]
                tool_calls.append(normalized)

            return LLMResponse(
                content=msg.get("content", "") or "",
                tool_calls=tool_calls,
                provider="groq",
                model=data.get("model", self.model),
                latency_ms=elapsed,
            )
        except httpx.HTTPStatusError as e:
            elapsed = (time.monotonic() - start) * 1000
            error_body = ""
            try:
                error_body = e.response.json().get("error", {}).get("message", str(e))
            except Exception:
                error_body = str(e)
            return LLMResponse(
                provider="groq",
                model=self.model,
                latency_ms=elapsed,
                error=f"Groq API error: {error_body}",
            )
        except (httpx.HTTPError, Exception) as e:
            elapsed = (time.monotonic() - start) * 1000
            return LLMResponse(
                provider="groq",
                model=self.model,
                latency_ms=elapsed,
                error=str(e),
            )


class OpenAICompatibleProvider(LLMProvider):
    """Generic OpenAI-compatible provider (Together, Fireworks, etc.)."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> None:
        super().__init__(
            name=name,
            base_url=base_url,
            model=model,
            api_key=api_key,
            temperature=temperature,
            timeout=timeout,
        )

    async def check_health(self) -> bool:
        try:
            resp = await self._http.get("/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        start = time.monotonic()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await self._http.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            elapsed = (time.monotonic() - start) * 1000

            tool_calls = []
            for tc in msg.get("tool_calls", []):
                normalized = {
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", {}),
                    }
                }
                if "id" in tc:
                    normalized["id"] = tc["id"]
                if "type" in tc:
                    normalized["type"] = tc["type"]
                tool_calls.append(normalized)

            return LLMResponse(
                content=msg.get("content", "") or "",
                tool_calls=tool_calls,
                provider=self.name,
                model=data.get("model", self.model),
                latency_ms=elapsed,
            )
        except (httpx.HTTPError, Exception) as e:
            elapsed = (time.monotonic() - start) * 1000
            return LLMResponse(
                provider=self.name, model=self.model, latency_ms=elapsed, error=str(e)
            )


class LLMRouter:
    """Multi-provider LLM router with failover and circuit breaking.

    Tries providers in priority order. If one fails, falls back to the next.
    Circuit breaker disables a provider after N consecutive failures.
    """

    def __init__(self, config: AnubisConfig) -> None:
        self.config = config
        self._providers: dict[str, LLMProvider] = {}
        self._states: dict[str, ProviderState] = {}
        self._router_config = config.llm_router

        # Initialize providers based on priority
        for name in config.llm_router.provider_priority:
            if name == "ollama":
                self._providers["ollama"] = OllamaProvider(config.ollama)
            elif name == "groq":
                self._providers["groq"] = GroqProvider(config.groq)

            self._states[name] = ProviderState(name=name)

    @property
    def available_providers(self) -> list[str]:
        """List providers that aren't circuit-broken."""
        now = time.monotonic()
        available = []
        for name in self._router_config.provider_priority:
            state = self._states.get(name)
            if not state:
                continue
            if state.is_open:
                # Check if circuit breaker reset time has elapsed
                elapsed = now - state.last_failure_time
                if elapsed > self._router_config.circuit_breaker_reset_seconds:
                    state.is_open = False
                    state.consecutive_failures = 0
                    logger.info("circuit_breaker_reset", provider=name)
                else:
                    continue
            available.append(name)
        return available

    async def check_providers(self) -> dict[str, bool]:
        """Check health of all configured providers."""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.check_health()
        return results

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a chat request, trying providers in priority order.

        Returns the first successful response, or the last error.
        """
        last_error = LLMResponse(error="No providers available")

        for provider_name in self.available_providers:
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            state = self._states[provider_name]

            # Retry loop for this provider
            for attempt in range(self._router_config.max_retries_per_provider):
                logger.debug(
                    "llm_request",
                    provider=provider_name,
                    attempt=attempt + 1,
                    model=provider.model,
                )

                response = await provider.chat(messages, tools=tools, temperature=temperature)
                state.total_requests += 1

                if response.ok:
                    # Success — reset failure counter
                    state.consecutive_failures = 0
                    # Update running average latency
                    state.avg_latency_ms = (
                        state.avg_latency_ms * 0.9 + response.latency_ms * 0.1
                    )
                    logger.info(
                        "llm_response",
                        provider=provider_name,
                        model=response.model,
                        latency_ms=round(response.latency_ms),
                        has_tool_calls=response.has_tool_calls,
                    )
                    return response

                # Failure
                state.total_failures += 1
                state.consecutive_failures += 1
                state.last_failure_time = time.monotonic()
                last_error = response

                logger.warning(
                    "llm_request_failed",
                    provider=provider_name,
                    attempt=attempt + 1,
                    error=response.error,
                )

                # Check circuit breaker
                if state.consecutive_failures >= self._router_config.circuit_breaker_threshold:
                    state.is_open = True
                    logger.error(
                        "circuit_breaker_opened",
                        provider=provider_name,
                        failures=state.consecutive_failures,
                    )
                    break  # Move to next provider

                # Exponential backoff before retry
                if attempt < self._router_config.max_retries_per_provider - 1:
                    delay = self._router_config.retry_delay_seconds * (2**attempt)
                    await asyncio.sleep(delay)

        return last_error

    def get_status(self) -> dict[str, Any]:
        """Get router status for diagnostics."""
        return {
            "providers": {
                name: {
                    "available": name in self.available_providers,
                    "circuit_breaker_open": state.is_open,
                    "consecutive_failures": state.consecutive_failures,
                    "total_requests": state.total_requests,
                    "total_failures": state.total_failures,
                    "avg_latency_ms": round(state.avg_latency_ms),
                }
                for name, state in self._states.items()
            }
        }

    async def close(self) -> None:
        """Close all provider HTTP clients."""
        for provider in self._providers.values():
            await provider.close()
