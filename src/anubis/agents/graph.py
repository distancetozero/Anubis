"""LangGraph-based agent orchestration for Anubis.

This module defines the agent graph that routes user queries
to specialist agents via a supervisor pattern. Integrates with:
- Multi-provider LLM router (Ollama, Groq, etc.)
- Guardrail engine for safety
- Knowledge base for enriched diagnostics
- Self-healing retry logic
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from anubis.agents.base import AGENT_SYSTEM_PROMPTS, AgentRole, AgentState
from anubis.core.guardrails import GuardrailEngine, RiskLevel
from anubis.knowledge.lookup import search_knowledge_base
from anubis.llm.router import LLMResponse, LLMRouter
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

    Integrates guardrails, knowledge base, and self-healing retry.
    """

    def __init__(
        self,
        llm: LLMRouter,
        registry: ToolRegistry,
        guardrails: GuardrailEngine | None = None,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.guardrails = guardrails or GuardrailEngine()

    async def run(self, user_query: str) -> str:
        """Run the agent graph on a user query.

        Returns the final response string.
        """
        state = AgentState(
            user_query=user_query,
            messages=[{"role": "user", "content": user_query}],
        )

        # Enrich with knowledge base context
        kb_results = search_knowledge_base(user_query)
        if kb_results:
            kb_context = "\n\nRelevant knowledge base entries:\n" + json.dumps(
                kb_results[:5], indent=2
            )
            state.messages.append({
                "role": "system",
                "content": f"Knowledge base context for this query:{kb_context}",
            })

        while state.iterations < state.max_iterations:
            state.iterations += 1
            logger.info(
                "agent_step",
                iteration=state.iterations,
                agent=state.next_agent.value,
            )

            try:
                if state.next_agent == AgentRole.ORCHESTRATOR:
                    state = await self._run_orchestrator(state)
                else:
                    state = await self._run_specialist(state, state.next_agent)
            except Exception as e:
                logger.error("agent_step_failed", error=str(e), agent=state.next_agent.value)
                # Self-healing: retry with orchestrator
                state.findings.append(f"[error] Agent {state.next_agent.value} failed: {e}")
                state.next_agent = AgentRole.ORCHESTRATOR
                continue

            # If orchestrator set a response, validate and return
            if state.response:
                # Output validation
                validation = self.guardrails.validate_llm_output(state.response)
                if not validation.allowed:
                    logger.error("output_blocked", reason=validation.reason)
                    return (
                        "I generated a response that was blocked by safety guardrails. "
                        f"Reason: {validation.reason}. Please rephrase your request."
                    )
                return state.response

        return (
            "I wasn't able to complete the analysis within the iteration limit. "
            "Here's what I found so far:\n\n" + "\n".join(state.findings)
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

        # Add pending actions context
        if state.pending_actions:
            context += "\n\nPending actions requiring user confirmation:\n"
            for action in state.pending_actions:
                context += f"- {action['description']} (tool: {action['tool']})\n"

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

        if not response.ok:
            logger.error("orchestrator_llm_failed", error=response.error)
            state.response = f"LLM error: {response.error}. Please check your LLM configuration."
            return state

        content = response.content

        # Parse the orchestrator's decision
        if content.startswith("ROUTE:"):
            agent_name = content.replace("ROUTE:", "").strip().lower()
            try:
                state.next_agent = AgentRole(agent_name)
                logger.info("routing", target=agent_name, provider=response.provider)
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

        # Enrich specialist prompt with knowledge base
        kb_context = ""
        kb_results = search_knowledge_base(state.user_query)
        if kb_results:
            relevant = [r for r in kb_results if self._kb_relevant_to_agent(r, role)]
            if relevant:
                kb_context = (
                    "\n\nRelevant knowledge base entries for your analysis:\n"
                    + json.dumps(relevant[:3], indent=2)
                )

        # Filter registry to only this agent's tools
        tools = [
            t
            for t in self.registry.to_ollama_format()
            if t["function"]["name"] in allowed_tools
        ]

        messages = [
            {"role": "system", "content": system_prompt + kb_context},
            {
                "role": "user",
                "content": f"User query: {state.user_query}\n\nPlease investigate using your tools and report your findings.",
            },
        ]

        # Tool-calling loop with self-healing retry
        for tool_round in range(5):  # Max 5 tool calls per specialist
            response = await self.llm.chat(messages, tools=tools)

            if not response.ok:
                logger.warning(
                    "specialist_llm_failed",
                    agent=role.value,
                    error=response.error,
                    round=tool_round,
                )
                # Self-healing: add error context and retry
                if tool_round < 4:
                    messages.append({
                        "role": "system",
                        "content": f"LLM request failed: {response.error}. Retrying...",
                    })
                    continue
                else:
                    state.findings.append(f"[{role.value}] LLM unavailable: {response.error}")
                    break

            # Check for tool calls
            if not response.has_tool_calls:
                # Agent is done, capture findings
                finding = response.content or "No findings"

                # Validate output
                validation = self.guardrails.validate_llm_output(finding)
                if not validation.allowed:
                    finding = f"[output blocked: {validation.reason}]"

                state.findings.append(f"[{role.value}] {finding}")
                state.messages.append({"role": "assistant", "content": finding})
                break

            # Execute tool calls
            messages.append(response.to_message_dict())
            for tc in response.tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {})

                # Parse string arguments if needed (Groq returns JSON string)
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                # === GUARDRAIL CHECK ===
                check = self.guardrails.check_tool_call(tool_name, tool_args)

                if not check.allowed:
                    # Blocked by guardrails
                    result = json.dumps({
                        "error": f"BLOCKED: {check.reason}",
                        "risk_level": check.risk_level.value,
                    })
                    self.guardrails.log_action(
                        tool_name, tool_args, check.risk_level,
                        approved=False, agent=role.value,
                    )
                    logger.warning(
                        "tool_blocked",
                        tool=tool_name,
                        reason=check.reason,
                        agent=role.value,
                    )
                elif check.requires_confirmation:
                    # Needs user confirmation
                    state.pending_actions.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "warning": check.warning,
                        "risk_level": check.risk_level.value,
                    })
                    result = json.dumps({
                        "status": "pending_confirmation",
                        "message": f"{check.warning} — requires user confirmation",
                    })
                else:
                    # Safe to execute
                    result = await self.registry.execute(tool_name, tool_args)
                    self.guardrails.log_action(
                        tool_name, tool_args, check.risk_level,
                        approved=True, result=result[:200], agent=role.value,
                    )

                messages.append({
                    "role": "tool",
                    "content": result,
                })

        # Return to orchestrator
        state.next_agent = AgentRole.ORCHESTRATOR
        return state

    @staticmethod
    def _kb_relevant_to_agent(kb_entry: dict, role: AgentRole) -> bool:
        """Check if a knowledge base entry is relevant to a specific agent."""
        entry_type = kb_entry.get("type", "")
        relevance_map = {
            AgentRole.FAULT_DIAGNOSTICIAN: {"bsod", "event_id"},
            AgentRole.SERVICE_MANAGER: {"service"},
            AgentRole.HEALTH_MONITOR: {"event_id"},
            AgentRole.DRIVER_ANALYST: {"bsod"},
        }
        relevant_types = relevance_map.get(role, set())
        return entry_type in relevant_types
