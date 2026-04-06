"""Registry of tools available to Anubis agents.

Maps tool definitions to their Python implementations so the agent
framework can call them when the LLM requests a tool invocation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

logger = structlog.get_logger("anubis.tools")


@dataclass
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    requires_admin: bool = False
    requires_confirmation: bool = False


class ToolRegistry:
    """Central registry of all tools available to agents."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
        requires_admin: bool = False,
        requires_confirmation: bool = False,
    ) -> None:
        """Register a tool for agent use."""
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            requires_admin=requires_admin,
            requires_confirmation=requires_confirmation,
        )

    def get(self, name: str) -> RegisteredTool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[RegisteredTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def to_ollama_format(self) -> list[dict]:
        """Export all tools in Ollama function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with given arguments.

        Returns the result as a JSON string for the LLM.
        """
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"})

        logger.info("tool_execute", tool=name, args=arguments)

        try:
            result = tool.handler(**arguments)
            # Handle both sync and async handlers
            if hasattr(result, "__await__"):
                result = await result

            # Convert dataclass results to dicts
            if hasattr(result, "__dataclass_fields__"):
                import dataclasses
                result = dataclasses.asdict(result)
            elif isinstance(result, list) and result and hasattr(result[0], "__dataclass_fields__"):
                import dataclasses
                result = [dataclasses.asdict(r) for r in result]

            return json.dumps(result, default=str)
        except Exception as e:
            logger.error("tool_error", tool=name, error=str(e))
            return json.dumps({"error": str(e)})


def build_default_registry() -> ToolRegistry:
    """Build the default tool registry with all Anubis tools."""
    from anubis.tools import (
        cleanup,
        disk_health,
        drivers,
        event_logs,
        performance,
        processes,
        services,
        system_health,
    )

    registry = ToolRegistry()

    # --- System Health Tools ---
    registry.register(
        name="get_system_snapshot",
        description="Get a full system health snapshot including CPU, memory, disk, network, and temperatures",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=system_health.get_system_snapshot,
    )
    registry.register(
        name="get_cpu_info",
        description="Get current CPU utilization, frequency, and core count",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=system_health.get_cpu_info,
    )
    registry.register(
        name="get_memory_info",
        description="Get current memory and swap usage",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=system_health.get_memory_info,
    )
    registry.register(
        name="get_disk_info",
        description="Get usage info for all mounted disk partitions",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=system_health.get_disk_info,
    )

    # --- Process Tools ---
    registry.register(
        name="get_top_processes",
        description="Get top resource-consuming processes sorted by CPU or memory",
        parameters={
            "type": "object",
            "properties": {
                "sort_by": {"type": "string", "enum": ["cpu", "memory"], "default": "cpu"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
        handler=processes.get_top_processes,
    )
    registry.register(
        name="kill_process",
        description="Terminate a process by its PID",
        parameters={
            "type": "object",
            "properties": {"pid": {"type": "integer", "description": "Process ID to kill"}},
            "required": ["pid"],
        },
        handler=processes.kill_process,
        requires_confirmation=True,
    )
    registry.register(
        name="get_startup_programs",
        description="Get programs configured to run at Windows startup",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=processes.get_startup_programs,
    )

    # --- Service Tools ---
    registry.register(
        name="get_services",
        description="Get all Windows services and their status",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=services.get_services,
    )
    registry.register(
        name="get_failed_services",
        description="Get auto-start services that are currently stopped (potential failures)",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=services.get_failed_services,
    )
    registry.register(
        name="restart_service",
        description="Restart a Windows service by name (requires admin)",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Service name"}},
            "required": ["name"],
        },
        handler=services.restart_service,
        requires_admin=True,
        requires_confirmation=True,
    )
    registry.register(
        name="identify_bloatware_services",
        description="Identify running services commonly considered bloatware",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=services.identify_bloatware_services,
    )

    # --- Driver Tools ---
    registry.register(
        name="get_all_drivers",
        description="Get all installed drivers with version, manufacturer, and signing status",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=drivers.get_all_drivers,
    )
    registry.register(
        name="get_problem_drivers",
        description="Get drivers with errors or that are unsigned",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=drivers.get_problem_drivers,
    )
    registry.register(
        name="get_driver_summary",
        description="Get a summary of overall driver health",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=drivers.get_driver_summary,
    )

    # --- Event Log / Fault Tools ---
    registry.register(
        name="get_recent_errors",
        description="Get recent error and critical events from Windows event logs",
        parameters={
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 24, "description": "Hours to look back"},
            },
            "required": [],
        },
        handler=event_logs.get_recent_errors,
    )
    registry.register(
        name="get_bsod_events",
        description="Get Blue Screen of Death (BSOD) crash events",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=event_logs.get_bsod_events,
    )
    registry.register(
        name="get_crash_dumps",
        description="List available crash dump files for analysis",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=event_logs.get_crash_dumps,
    )
    registry.register(
        name="get_event_log_summary",
        description="Get a count summary of errors, warnings, and critical events",
        parameters={
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 24},
            },
            "required": [],
        },
        handler=event_logs.get_event_log_summary,
    )

    # --- Disk Health Tools ---
    registry.register(
        name="get_disk_health",
        description="Get SMART health data for all physical disks",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=disk_health.get_disk_health,
    )
    registry.register(
        name="get_disk_health_summary",
        description="Get a quick summary of disk health across all drives",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=disk_health.get_disk_health_summary,
    )

    # --- Cleanup Tools ---
    registry.register(
        name="scan_temp_files",
        description="Scan common temp file locations and report sizes for potential cleanup",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=cleanup.scan_temp_files,
    )
    registry.register(
        name="clean_temp_files",
        description="Delete temp files from a specific path",
        parameters={
            "type": "object",
            "properties": {
                "target_path": {"type": "string", "description": "Path to clean"},
            },
            "required": ["target_path"],
        },
        handler=cleanup.clean_temp_files,
        requires_confirmation=True,
    )
    registry.register(
        name="flush_dns_cache",
        description="Flush the DNS resolver cache",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=cleanup.flush_dns_cache,
    )
    registry.register(
        name="get_recycle_bin_size",
        description="Get the size and item count of the recycle bin",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=cleanup.get_recycle_bin_size,
    )

    # --- Performance Tools ---
    registry.register(
        name="get_power_plans",
        description="Get available Windows power plans and which is active",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=performance.get_power_plans,
    )
    registry.register(
        name="set_power_plan",
        description="Set the active Windows power plan",
        parameters={
            "type": "object",
            "properties": {
                "guid": {"type": "string", "description": "Power plan GUID"},
            },
            "required": ["guid"],
        },
        handler=performance.set_power_plan,
        requires_confirmation=True,
    )
    registry.register(
        name="get_memory_diagnostics",
        description="Get memory usage diagnostics with top consumers",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=performance.get_memory_diagnostics,
    )
    registry.register(
        name="get_system_boot_time",
        description="Get last boot time and performance data",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=performance.get_system_boot_time,
    )

    return registry
