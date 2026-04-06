"""FastAPI application for the Anubis web dashboard.

Serves both the JSON API and the HTMX-powered web UI.
"""

from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from anubis.agents.graph import AnubisAgentGraph
from anubis.core.config import AnubisConfig
from anubis.core.guardrails import GuardrailEngine
from anubis.core.watchdog import Watchdog
from anubis.llm.router import LLMRouter
from anubis.llm.tool_registry import build_default_registry

# Paths
TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


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
_watchdog: Watchdog | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global _router, _graph, _guardrails, _watchdog

    config = AnubisConfig.load()
    _router = LLMRouter(config)
    _guardrails = GuardrailEngine()
    registry = build_default_registry()
    _graph = AnubisAgentGraph(_router, registry, _guardrails)

    # Start watchdog
    _watchdog = Watchdog(config.monitoring)
    if config.monitoring.enable_watchdog:
        await _watchdog.start()

    yield

    if _watchdog:
        await _watchdog.stop()
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

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # =========================================================================
    # UI Pages (full HTML)
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        """Main dashboard page."""
        from anubis.tools.system_health import get_system_snapshot

        snapshot = get_system_snapshot()
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"active_page": "dashboard", "snapshot": snapshot},
        )

    @app.get("/ui/chat", response_class=HTMLResponse)
    async def chat_page(request: Request):
        """Chat interface page."""
        return templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={"active_page": "chat"},
        )

    @app.get("/ui/services", response_class=HTMLResponse)
    async def services_page(request: Request):
        """Services management page."""
        return templates.TemplateResponse(
            request=request,
            name="services.html",
            context={"active_page": "services"},
        )

    @app.get("/ui/drivers", response_class=HTMLResponse)
    async def drivers_page(request: Request):
        """Driver analysis page."""
        return templates.TemplateResponse(
            request=request,
            name="drivers.html",
            context={"active_page": "drivers"},
        )

    @app.get("/ui/events", response_class=HTMLResponse)
    async def events_page(request: Request):
        """Event log analysis page."""
        return templates.TemplateResponse(
            request=request,
            name="events.html",
            context={"active_page": "events"},
        )

    @app.get("/ui/cleanup", response_class=HTMLResponse)
    async def cleanup_page(request: Request):
        """Disk cleanup page."""
        return templates.TemplateResponse(
            request=request,
            name="cleanup.html",
            context={"active_page": "cleanup"},
        )

    @app.get("/ui/alerts", response_class=HTMLResponse)
    async def alerts_page(request: Request):
        """Alerts and action log page."""
        return templates.TemplateResponse(
            request=request,
            name="alerts.html",
            context={"active_page": "alerts"},
        )

    # =========================================================================
    # HTMX Partials (HTML fragments for dynamic updates)
    # =========================================================================

    @app.get("/ui/partials/gauges", response_class=HTMLResponse)
    async def partial_gauges():
        """Live CPU/Memory/Disk gauges."""
        from anubis.tools.system_health import get_cpu_info, get_memory_info, get_disk_info

        cpu = get_cpu_info()
        mem = get_memory_info()
        disks = get_disk_info()
        max_disk = max((d.usage_percent for d in disks), default=0)

        def gauge_color(val):
            if val < 60: return "text-success"
            if val < 80: return "text-warning"
            return "text-error"

        return f"""
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="card bg-base-100 shadow-xl">
                <div class="card-body items-center text-center">
                    <div class="radial-progress {gauge_color(cpu.usage_percent)}" style="--value:{cpu.usage_percent}; --size:8rem; --thickness:0.8rem;" role="progressbar">
                        <span class="text-2xl font-bold">{cpu.usage_percent}%</span>
                    </div>
                    <h3 class="card-title mt-2">CPU</h3>
                    <p class="text-sm opacity-70">{cpu.frequency_mhz:.0f} MHz &bull; {cpu.core_count_logical} threads</p>
                </div>
            </div>
            <div class="card bg-base-100 shadow-xl">
                <div class="card-body items-center text-center">
                    <div class="radial-progress {gauge_color(mem.usage_percent)}" style="--value:{mem.usage_percent}; --size:8rem; --thickness:0.8rem;" role="progressbar">
                        <span class="text-2xl font-bold">{mem.usage_percent}%</span>
                    </div>
                    <h3 class="card-title mt-2">Memory</h3>
                    <p class="text-sm opacity-70">{mem.used_gb} / {mem.total_gb} GB</p>
                </div>
            </div>
            <div class="card bg-base-100 shadow-xl">
                <div class="card-body items-center text-center">
                    <div class="radial-progress {gauge_color(max_disk)}" style="--value:{max_disk}; --size:8rem; --thickness:0.8rem;" role="progressbar">
                        <span class="text-2xl font-bold">{max_disk:.0f}%</span>
                    </div>
                    <h3 class="card-title mt-2">Disk (Max)</h3>
                    <p class="text-sm opacity-70">{len(disks)} volume(s)</p>
                </div>
            </div>
        </div>
        """

    @app.get("/ui/partials/processes", response_class=HTMLResponse)
    async def partial_processes():
        """Top processes table fragment."""
        from anubis.tools.processes import get_top_processes

        procs = get_top_processes(sort_by="cpu", limit=8)
        rows = ""
        for p in procs:
            cpu_badge = "badge-success" if p.cpu_percent < 20 else "badge-warning" if p.cpu_percent < 50 else "badge-error"
            rows += f"""
            <tr>
                <td class="font-mono text-sm">{p.name}</td>
                <td><span class="badge {cpu_badge} badge-sm">{p.cpu_percent}%</span></td>
                <td>{p.memory_mb} MB</td>
                <td class="opacity-50">{p.pid}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto">
            <table class="table table-xs">
                <thead><tr><th>Process</th><th>CPU</th><th>Memory</th><th>PID</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    @app.get("/ui/partials/alerts", response_class=HTMLResponse)
    async def partial_alerts():
        """Recent alerts fragment."""
        alerts = _watchdog.get_recent_alerts(limit=10) if _watchdog else []
        if not alerts:
            return '<div class="text-center py-4 opacity-50">No alerts yet. System is being monitored.</div>'

        items = ""
        for a in reversed(alerts):
            icon = {"critical": "error", "warning": "warning", "info": "info"}.get(a["severity"], "info")
            color = {"critical": "alert-error", "warning": "alert-warning", "info": "alert-info"}.get(a["severity"], "")
            items += f"""
            <div class="alert {color} py-2 mb-2">
                <span class="text-xs opacity-70">{a['timestamp'][:19]}</span>
                <span class="font-semibold">{a['title']}</span>
                <span class="text-sm">{a['message']}</span>
            </div>"""
        return items

    @app.get("/ui/partials/provider-badge", response_class=HTMLResponse)
    async def partial_provider_badge():
        """Provider status badge for navbar."""
        providers = await _router.check_providers() if _router else {}
        connected = [n for n, h in providers.items() if h]
        if connected:
            names = ", ".join(connected)
            return f'<div class="badge badge-success gap-1"><span class="text-xs">LLM: {names}</span></div>'
        return '<div class="badge badge-error gap-1"><span class="text-xs">LLM: offline</span></div>'

    @app.get("/ui/partials/services-table", response_class=HTMLResponse)
    async def partial_services_table():
        """Full services table fragment."""
        from anubis.tools.services import get_services

        services = get_services()
        rows = ""
        for s in services[:100]:  # Cap at 100 for performance
            status_badge = "badge-success" if s.status == "4" else "badge-error" if s.status == "1" else "badge-warning"
            status_text = {
                "1": "Stopped", "2": "Starting", "3": "Stopping",
                "4": "Running", "5": "Continuing", "6": "Pausing", "7": "Paused"
            }.get(s.status, s.status)
            rows += f"""
            <tr>
                <td class="font-mono text-xs">{s.name}</td>
                <td class="text-sm">{s.display_name}</td>
                <td><span class="badge {status_badge} badge-sm">{status_text}</span></td>
                <td class="text-xs">{s.start_type}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto max-h-[600px]">
            <table class="table table-xs table-pin-rows">
                <thead><tr><th>Name</th><th>Display Name</th><th>Status</th><th>Start Type</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <div class="p-2 text-sm opacity-50">Showing {min(len(services), 100)} of {len(services)} services</div>
        """

    @app.get("/ui/partials/failed-services", response_class=HTMLResponse)
    async def partial_failed_services():
        """Failed services table fragment."""
        from anubis.tools.services import get_failed_services

        failed = get_failed_services()
        if not failed:
            return '<div class="p-4 text-center text-success">All auto-start services are running normally.</div>'

        rows = ""
        for s in failed:
            rows += f"""
            <tr class="bg-error/10">
                <td class="font-mono text-xs">{s.name}</td>
                <td class="text-sm">{s.display_name}</td>
                <td><span class="badge badge-error badge-sm">Stopped</span></td>
                <td>{s.start_type}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto">
            <table class="table table-xs">
                <thead><tr><th>Name</th><th>Display Name</th><th>Status</th><th>Start Type</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <div class="p-2 text-sm text-error">{len(failed)} auto-start service(s) not running</div>
        """

    @app.get("/ui/partials/bloatware-alert", response_class=HTMLResponse)
    async def partial_bloatware_alert():
        """Bloatware detection alert."""
        from anubis.knowledge.services_reference import get_bloatware_services

        bloatware = get_bloatware_services()
        if not bloatware:
            return ""

        names = ", ".join(s.display_name for s in bloatware)
        return f"""
        <div class="alert alert-warning">
            <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
            <div>
                <h3 class="font-bold">Bloatware Detected</h3>
                <div class="text-sm">These services can be safely disabled: {names}</div>
            </div>
            <a href="/ui/chat?q=Identify+bloatware+services+and+tell+me+which+to+disable" class="btn btn-sm btn-warning">Analyze</a>
        </div>
        """

    @app.get("/ui/partials/driver-summary", response_class=HTMLResponse)
    async def partial_driver_summary():
        """Driver health summary."""
        from anubis.tools.drivers import get_driver_summary

        summary = get_driver_summary()
        total = summary.get("total_drivers", 0)
        healthy = summary.get("healthy_drivers", 0)
        problems = summary.get("problem_drivers", 0)
        unsigned = summary.get("unsigned_drivers", 0)

        health_color = "text-success" if problems == 0 else "text-warning" if problems < 3 else "text-error"

        return f"""
        <div class="stats shadow w-full">
            <div class="stat">
                <div class="stat-title">Total Drivers</div>
                <div class="stat-value">{total}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Healthy</div>
                <div class="stat-value text-success">{healthy}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Problems</div>
                <div class="stat-value {health_color}">{problems}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Unsigned</div>
                <div class="stat-value text-warning">{unsigned}</div>
            </div>
        </div>
        """

    @app.get("/ui/partials/problem-drivers", response_class=HTMLResponse)
    async def partial_problem_drivers():
        """Problem drivers list."""
        from anubis.tools.drivers import get_problem_drivers

        problems = get_problem_drivers()
        if not problems:
            return '<div class="text-center py-4 text-success">All drivers are healthy and signed.</div>'

        rows = ""
        for d in problems[:20]:
            signed = '<span class="badge badge-success badge-xs">Signed</span>' if d.is_signed else '<span class="badge badge-error badge-xs">Unsigned</span>'
            rows += f"""
            <tr>
                <td class="text-sm">{d.device_name}</td>
                <td class="font-mono text-xs">{d.driver_version}</td>
                <td class="text-xs">{d.manufacturer}</td>
                <td><span class="badge badge-warning badge-sm">{d.status}</span></td>
                <td>{signed}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto">
            <table class="table table-xs">
                <thead><tr><th>Device</th><th>Version</th><th>Manufacturer</th><th>Status</th><th>Signed</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    @app.get("/ui/partials/event-summary", response_class=HTMLResponse)
    async def partial_event_summary(hours: int = 24):
        """Event log summary stats."""
        from anubis.tools.event_logs import get_event_log_summary

        summary = get_event_log_summary(hours=hours)
        if not summary:
            return '<div class="text-center py-4 opacity-50">Could not retrieve event summary.</div>'

        return f"""
        <div class="stats shadow w-full">
            <div class="stat">
                <div class="stat-title">System Critical</div>
                <div class="stat-value text-error">{summary.get('System_Critical', 0)}</div>
            </div>
            <div class="stat">
                <div class="stat-title">System Errors</div>
                <div class="stat-value text-warning">{summary.get('System_Error', 0)}</div>
            </div>
            <div class="stat">
                <div class="stat-title">System Warnings</div>
                <div class="stat-value">{summary.get('System_Warning', 0)}</div>
            </div>
            <div class="stat">
                <div class="stat-title">App Errors</div>
                <div class="stat-value text-warning">{summary.get('Application_Error', 0)}</div>
            </div>
        </div>
        """

    @app.get("/ui/partials/event-list", response_class=HTMLResponse)
    async def partial_event_list(hours: int = 24):
        """Event log entries list."""
        from anubis.tools.event_logs import get_recent_errors
        from anubis.knowledge.event_ids import lookup_event

        events = get_recent_errors(hours=hours, max_entries=30)
        if not events:
            return '<div class="text-center py-4 text-success">No errors or critical events in this period.</div>'

        rows = ""
        for e in events:
            level_badge = {
                "Critical": "badge-error",
                "Error": "badge-warning",
            }.get(e.level, "badge-info")

            # Check knowledge base
            kb = lookup_event(e.event_id, e.source)
            kb_tip = f' <div class="tooltip tooltip-left" data-tip="{kb.title}"><span class="badge badge-info badge-xs">KB</span></div>' if kb else ""

            rows += f"""
            <tr>
                <td class="text-xs whitespace-nowrap">{e.time_created[:19]}</td>
                <td><span class="badge {level_badge} badge-sm">{e.level}</span></td>
                <td class="text-xs">{e.source}</td>
                <td>{e.event_id}{kb_tip}</td>
                <td class="text-xs max-w-md truncate">{e.message[:150]}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto max-h-[500px]">
            <table class="table table-xs table-pin-rows">
                <thead><tr><th>Time</th><th>Level</th><th>Source</th><th>ID</th><th>Message</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    @app.get("/ui/partials/cleanup-scan", response_class=HTMLResponse)
    async def partial_cleanup_scan():
        """Cleanup scan results."""
        from anubis.tools.cleanup import scan_temp_files

        targets = scan_temp_files()
        if not targets:
            return '<div class="text-center py-4 text-success">No significant temp files found.</div>'

        total_mb = sum(t.size_mb for t in targets)
        total_files = sum(t.file_count for t in targets)

        cards = ""
        for t in targets:
            cards += f"""
            <div class="card bg-base-200 compact">
                <div class="card-body">
                    <h4 class="card-title text-sm">{t.description}</h4>
                    <p class="text-xs font-mono opacity-70">{t.path}</p>
                    <div class="flex justify-between items-center mt-1">
                        <span class="text-lg font-bold text-warning">{t.size_mb} MB</span>
                        <span class="text-sm opacity-50">{t.file_count} files</span>
                    </div>
                </div>
            </div>"""

        return f"""
        <div class="alert alert-info mb-4">
            <span>Found <strong>{total_mb:.1f} MB</strong> in <strong>{total_files}</strong> temp files across {len(targets)} locations</span>
            <a href="/ui/chat?q=Clean+up+all+temp+files+safely" class="btn btn-sm btn-info">Clean via Chat</a>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">{cards}</div>
        """

    @app.get("/ui/partials/recycle-bin", response_class=HTMLResponse)
    async def partial_recycle_bin():
        """Recycle bin info."""
        from anubis.tools.cleanup import get_recycle_bin_size

        info = get_recycle_bin_size()
        size = info.get("SizeMB", 0)
        count = info.get("ItemCount", 0)

        return f"""
        <div class="flex justify-between items-center">
            <div>
                <span class="text-lg font-bold">{size} MB</span>
                <span class="text-sm opacity-50 ml-2">({count} items)</span>
            </div>
        </div>
        """

    @app.get("/ui/partials/disk-health", response_class=HTMLResponse)
    async def partial_disk_health():
        """Disk SMART health."""
        from anubis.tools.disk_health import get_disk_health

        disks = get_disk_health()
        if not disks:
            return '<div class="opacity-50">Could not retrieve disk health data (may need admin privileges).</div>'

        cards = ""
        for d in disks:
            health_badge = {
                "Healthy": "badge-success",
                "Warning": "badge-warning",
                "Unhealthy": "badge-error",
            }.get(d.health_status, "badge-ghost")
            temp = f"{d.temperature_celsius}C" if d.temperature_celsius else "N/A"

            cards += f"""
            <div class="flex justify-between items-center py-2 border-b border-base-300">
                <div>
                    <span class="font-semibold">{d.model}</span>
                    <span class="text-sm opacity-50 ml-2">{d.size_gb} GB {d.media_type}</span>
                </div>
                <div class="flex gap-2 items-center">
                    <span class="text-sm">{temp}</span>
                    <span class="badge {health_badge}">{d.health_status}</span>
                </div>
            </div>"""

        return cards

    @app.get("/ui/partials/action-log", response_class=HTMLResponse)
    async def partial_action_log():
        """Guardrail action log."""
        log = _guardrails.get_action_log(limit=20) if _guardrails else []
        if not log:
            return '<div class="text-center py-4 opacity-50">No actions recorded yet.</div>'

        rows = ""
        for entry in reversed(log):
            risk_badge = {
                "safe": "badge-success",
                "caution": "badge-warning",
                "dangerous": "badge-error",
            }.get(entry["risk"], "badge-ghost")
            approved = '<span class="text-success">Approved</span>' if entry["approved"] else '<span class="text-error">Blocked</span>'
            rows += f"""
            <tr>
                <td class="text-xs">{entry['timestamp'][:19]}</td>
                <td class="font-mono text-xs">{entry['tool']}</td>
                <td><span class="badge {risk_badge} badge-xs">{entry['risk']}</span></td>
                <td>{approved}</td>
                <td class="text-xs">{entry['agent']}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto">
            <table class="table table-xs">
                <thead><tr><th>Time</th><th>Tool</th><th>Risk</th><th>Status</th><th>Agent</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    @app.get("/ui/partials/router-status", response_class=HTMLResponse)
    async def partial_router_status():
        """LLM router status."""
        if not _router:
            return '<div class="opacity-50">Router not initialized.</div>'

        status = _router.get_status()
        rows = ""
        for name, info in status["providers"].items():
            avail = '<span class="badge badge-success badge-sm">Online</span>' if info["available"] else '<span class="badge badge-error badge-sm">Offline</span>'
            cb = '<span class="text-error">OPEN</span>' if info["circuit_breaker_open"] else '<span class="text-success">OK</span>'
            rows += f"""
            <tr>
                <td class="font-semibold">{name}</td>
                <td>{avail}</td>
                <td>{info['total_requests']}</td>
                <td>{info['total_failures']}</td>
                <td>{info['avg_latency_ms']}ms</td>
                <td>{cb}</td>
            </tr>"""

        return f"""
        <div class="overflow-x-auto">
            <table class="table table-xs">
                <thead><tr><th>Provider</th><th>Status</th><th>Requests</th><th>Failures</th><th>Avg Latency</th><th>Circuit Breaker</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    @app.get("/ui/partials/kb-stats", response_class=HTMLResponse)
    async def partial_kb_stats():
        """Knowledge base statistics."""
        from anubis.knowledge.lookup import get_knowledge_stats

        stats = get_knowledge_stats()
        return f"""
        <div class="stats shadow w-full">
            <div class="stat">
                <div class="stat-title">BSOD Codes</div>
                <div class="stat-value">{stats['bsod_codes']}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Event IDs</div>
                <div class="stat-value">{stats['event_ids']}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Service Refs</div>
                <div class="stat-value">{stats['service_references']}</div>
            </div>
        </div>
        """

    # =========================================================================
    # Chat endpoint (HTMX form submission)
    # =========================================================================

    @app.post("/ui/chat/send", response_class=HTMLResponse)
    async def chat_send(query: str = Form(...)):
        """Handle chat form submission, return HTML fragments."""
        # User message bubble
        user_html = f"""
        <div class="chat chat-end fade-in">
            <div class="chat-bubble">{query}</div>
        </div>
        """

        # Show thinking indicator
        thinking_id = f"thinking-{hash(query) % 10000}"

        if not _graph:
            return user_html + """
            <div class="chat chat-start fade-in">
                <div class="chat-bubble chat-bubble-error">Anubis is not initialized. Check LLM provider status.</div>
            </div>"""

        try:
            response = await _graph.run(query)
            # Convert markdown-like formatting to simple HTML
            response_html = response.replace("\n", "<br>").replace("**", "<strong>").replace("- ", "&bull; ")

            return user_html + f"""
            <div class="chat chat-start fade-in">
                <div class="chat-bubble chat-bubble-primary">{response_html}</div>
            </div>
            """
        except Exception as e:
            return user_html + f"""
            <div class="chat chat-start fade-in">
                <div class="chat-bubble chat-bubble-error">Error: {str(e)}</div>
            </div>
            """

    # =========================================================================
    # JSON API (unchanged from before)
    # =========================================================================

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        providers = await _router.check_providers() if _router else {}
        any_connected = any(providers.values())
        config = AnubisConfig.load()
        return HealthResponse(
            status="ok" if any_connected else "degraded",
            providers=providers,
            active_model=config.ollama.model,
        )

    @app.get("/router/status")
    async def router_status_api() -> dict:
        if not _router:
            return {"error": "Router not initialized"}
        return _router.get_status()

    @app.post("/chat", response_model=ChatResponse)
    async def chat_api(request: ChatRequest) -> ChatResponse:
        if not _graph:
            return ChatResponse(response="Anubis is not initialized")
        response = await _graph.run(request.query)
        return ChatResponse(response=response)

    @app.get("/snapshot")
    async def system_snapshot() -> dict:
        from anubis.tools.system_health import get_system_snapshot
        snapshot = get_system_snapshot()
        return dataclasses.asdict(snapshot)

    @app.get("/processes/top")
    async def top_processes(sort_by: str = "cpu", limit: int = 20) -> list[dict]:
        from anubis.tools.processes import get_top_processes
        return [dataclasses.asdict(p) for p in get_top_processes(sort_by=sort_by, limit=limit)]

    return app


# Module-level app instance for uvicorn (uvicorn anubis.api.app:app)
app = create_app()
