"""LangGraph-based agent orchestration for Anubis.

This module defines the agent graph that routes user queries
to specialist agents via a supervisor pattern.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from anubis.agents.base import AGENT_SYSTEM_PROMPTS, AgentRole, AgentState
from anubis.llm.ollama_client import OllamaClient
from anubis.llm.tool_registry import ToolRegistry

logger = structlog.get_logger("anubis.agents")

# Map agent roles to their allowed tools
AGENT_TOOLS: dict[AgentRole, list[str]] = {
    AgentRole.ORCHESTRATOR: [],  # Orchestrator doesn't call tools directly
    AgentRole.HEALTH_MONITOR: [
        "get_system_snapshot",
        "get_cpu_info",
        "get_memory_info",
        "get_disk_info",
    ],
    AgentRole.SERVICE_MANAGER: [
        "get_services",
        "get_failed_services",
        "restart_service",
        "identify_bloatware_services",
    ],
    AgentRole.DRIVER_ANALYST: [
        "get_all_drivers",
        "get_problem_drivers",
        "get_driver_summary",
    ],
    AgentRole.FAULT_DIAGNOSTICIAN: [
        "get_recent_errors",
        "get_bsod_events",
        "get_crash_dumps",
        "get_event_log_summary",
    ],
    AgentRole.PERFORMANCE_TUNER: [
        "get_power_plans",
        "set_power_plan",
        "get_memory_diagnostics",
        "get_system_boot_time",
        "get_startup_programs",
    ],
    AgentRole.CLEANUP_AGENT: [
        "scan_temp_files",
        "clean_temp_files",
        "flush_dns_cache",
        "get_recycle_bin_size",
    ],
}


class AnubisAgentGraph:
    """The main agent orchestration graph.

    Uses a supervisor pattern where the orchestrator agent decides
    which specialist to invoke based on the user's query.
    """

    def __init__(self, llm: OllamaClient, registry: ToolRegistry) -> None:
        self.llm = llm
        self.registry = registry

    async def run(self, user_query: str) -> str:
        """Run the agent graph on a user query.

        Returns the final response string.
        """
        state = AgentState(
            user_query=user_query,
            messages=[{"role": "user", "content": user_query}],
        )

        while state.iterations < state.max_iterations:
            state.iterations += 1
            logger.info(
                "agent_step",
                iteration=state.iterations,
                agent=state.next_agent.value,
            )

            if state.next_agent == AgentRole.ORCHESTRATOR:
                state = await self._run_orchestrator(state)
            else:
                state = await self._run_specialist(state, state.next_agent)

            # If orchestrator set a response, we're done
            if state.response:
                return state.response

        return "I wasn't able to complete the analysis within the iteration limit. Here's what I found so far:\n\n" + "\n".join(
            state.findings
        )

    async def _run_orchestrator(self, state: AgentState) -> AgentState:
        """Run the orchestrator to decide routing or produce final response."""
        system_prompt = AGENT_SYSTEM_PROMPTS[AgentRole.ORCHESTRATOR]

        # Build context with any findings so far
        context = ""
        if state.findings:
            context = "\n\nFindings from specialists so far:\n" + "\n".join(
                f"- {f}" for f in state.findings
            )

        messages = [
            {"role": "system", "content": system_prompt + context},
            *state.messages,
        ]

        # Ask orchestrator what to do
        routing_prompt = {
            "role": "user",
            "content": (
                "Based on the user's query and any findings so far, decide what to do next.\n"
                "Reply with EXACTLY one of:\n"
                "- ROUTE:health_monitor\n"
                "- ROUTE:service_manager\n"
                "- ROUTE:driver_analyst\n"
                "- ROUTE:fault_diagnostician\n"
                "- ROUTE:performance_tuner\n"
                "- ROUTE:cleanup_agent\n"
                "- RESPOND:<your final response to the user>\n\n"
                "Use ROUTE if more information is needed. Use RESPOND if you have enough "
                "findings to give the user a complete answer."
            ),
        }
        messages.append(routing_prompt)

        response = await self.llm.chat(messages)
        content = response.get("message", {}).get("content", "")

        # Parse the orchestrator's decision
        if content.startswith("ROUTE:"):
            agent_name = content.replace("ROUTE:", "").strip().lower()
            try:
                state.next_agent = AgentRole(agent_name)
                logger.info("routing", target=agent_name)
            except ValueError:
                logger.warning("invalid_route", attempted=agent_name)
                state.next_agent = AgentRole.HEALTH_MONITOR
        elif content.startswith("RESPOND:"):
            state.response = content.replace("RESPOND:", "").strip()
        else:
            # LLM didn't follow the format exactly — treat as response
            state.response = content

        return state

    async def _run_specialist(self, state: AgentState, role: AgentRole) -> AgentState:
        """Run a specialist agent with its assigned tools."""
        system_prompt = AGENT_SYSTEM_PROMPTS[role]
        allowed_tools = AGENT_TOOLS.get(role, [])

        # Filter registry to only this agent's tools
        tools = [
            t
            for t in self.registry.to_ollama_format()
            if t["function"]["name"] in allowed_tools
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"User query: {state.user_query}\n\nPlease investigate using your tools and report your findings.",
            },
        ]

        # Tool-calling loop
        for _ in range(5):  # Max 5 tool calls per specialist
            response = await self.llm.chat(messages, tools=tools)
            msg = response.get("message", {})

            # Check for tool calls
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                # Agent is done, capture findings
                finding = msg.get("content", "No findings")
                state.findings.append(f"[{role.value}] {finding}")
                state.messages.append({"role": "assistant", "content": finding})
                break

            # Execute tool calls
            messages.append(msg)
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {})

                # Safety check: confirm destructive actions
                tool_def = self.registry.get(tool_name)
                if tool_def and tool_def.requires_confirmation:
                    state.pending_actions.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "description": tool_def.description,
                    })
                    result = json.dumps({
                        "status": "pending_confirmation",
                        "message": f"Action '{tool_name}' requires user confirmation",
                    })
                else:
                    result = await self.registry.execute(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "content": result,
                })

        # Return to orchestrator
        state.next_agent = AgentRole.ORCHESTRATOR
        return state
