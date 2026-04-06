"""FastAPI application for the Anubis web dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from anubis.agents.graph import AnubisAgentGraph
from anubis.core.config import AnubisConfig
from anubis.core.guardrails import GuardrailEngine
from anubis.llm.router import LLMRouter
from anubis.llm.tool_registry import build_default_registry


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str
    pending_actions: list[dict[str, Any]] = []


class HealthResponse(BaseModel):
    status: str
    providers: dict[str, bool]
    active_model: str


# Module-level state (set during lifespan)
_router: LLMRouter | None = None
_graph: AnubisAgentGraph | None = None
_guardrails: GuardrailEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global _router, _graph, _guardrails

    config = AnubisConfig.load()
    _router = LLMRouter(config)
    _guardrails = GuardrailEngine()
    registry = build_default_registry()
    _graph = AnubisAgentGraph(_router, registry, _guardrails)

    yield

    if _router:
        await _router.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Anubis",
        description="AI-powered Windows PC optimization assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Check system health and provider connectivity."""
        providers = await _router.check_providers() if _router else {}
        any_connected = any(providers.values())
        config = AnubisConfig.load()
        return HealthResponse(
            status="ok" if any_connected else "degraded",
            providers=providers,
            active_model=config.ollama.model,
        )

    @app.get("/router/status")
    async def router_status() -> dict:
        """Get LLM router status including circuit breaker state."""
        if not _router:
            return {"error": "Router not initialized"}
        return _router.get_status()

    @app.get("/guardrails/log")
    async def guardrail_log(limit: int = 50) -> list[dict]:
        """Get recent guardrail action log."""
        if not _guardrails:
            return []
        return _guardrails.get_action_log(limit=limit)

    @app.get("/knowledge/stats")
    async def knowledge_stats() -> dict:
        """Get knowledge base statistics."""
        from anubis.knowledge.lookup import get_knowledge_stats
        return get_knowledge_stats()

    @app.get("/knowledge/search")
    async def knowledge_search(q: str) -> list[dict]:
        """Search the knowledge base."""
        from anubis.knowledge.lookup import search_knowledge_base
        return search_knowledge_base(q)

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        """Send a query to the Anubis agent system."""
        if not _graph:
            return ChatResponse(response="Anubis is not initialized")

        response = await _graph.run(request.query)
        return ChatResponse(response=response)

    @app.get("/snapshot")
    async def system_snapshot() -> dict:
        """Get a real-time system health snapshot."""
        from anubis.tools.system_health import get_system_snapshot

        import dataclasses

        snapshot = get_system_snapshot()
        return dataclasses.asdict(snapshot)

    @app.get("/services")
    async def services_list() -> list[dict]:
        """Get all Windows services."""
        from anubis.tools.services import get_services

        import dataclasses

        return [dataclasses.asdict(s) for s in get_services()]

    @app.get("/services/failed")
    async def failed_services() -> list[dict]:
        """Get failed auto-start services."""
        from anubis.tools.services import get_failed_services

        import dataclasses

        return [dataclasses.asdict(s) for s in get_failed_services()]

    @app.get("/drivers/summary")
    async def driver_summary() -> dict:
        """Get driver health summary."""
        from anubis.tools.drivers import get_driver_summary

        return get_driver_summary()

    @app.get("/events/errors")
    async def recent_errors(hours: int = 24) -> list[dict]:
        """Get recent error events."""
        from anubis.tools.event_logs import get_recent_errors

        import dataclasses

        return [dataclasses.asdict(e) for e in get_recent_errors(hours=hours)]

    @app.get("/disks/health")
    async def disk_health() -> list[dict]:
        """Get disk health information."""
        from anubis.tools.disk_health import get_disk_health

        import dataclasses

        return [dataclasses.asdict(d) for d in get_disk_health()]

    @app.get("/processes/top")
    async def top_processes(sort_by: str = "cpu", limit: int = 20) -> list[dict]:
        """Get top resource-consuming processes."""
        from anubis.tools.processes import get_top_processes

        import dataclasses

        return [dataclasses.asdict(p) for p in get_top_processes(sort_by=sort_by, limit=limit)]

    @app.get("/cleanup/scan")
    async def cleanup_scan() -> list[dict]:
        """Scan for temp files that can be cleaned."""
        from anubis.tools.cleanup import scan_temp_files

        import dataclasses

        return [dataclasses.asdict(t) for t in scan_temp_files()]

    return app
