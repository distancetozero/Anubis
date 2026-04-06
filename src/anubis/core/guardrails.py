"""Safety guardrails for Anubis agent actions.

Implements a layered safety system:
  Layer 1: Tool risk classification (safe / caution / dangerous)
  Layer 2: Confirmation gates for risky actions
  Layer 3: Blocklists — things we NEVER touch
  Layer 4: Output validation — catch bad LLM decisions before execution
  Layer 5: Action logging — audit trail of everything done
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger("anubis.guardrails")


class RiskLevel(str, Enum):
    SAFE = "safe"  # Read-only operations
    CAUTION = "caution"  # Reversible changes, requires confirmation
    DANGEROUS = "dangerous"  # Destructive or hard to reverse


@dataclass
class ActionRecord:
    """Audit log entry for an action taken by an agent."""

    timestamp: str
    tool_name: str
    arguments: dict[str, Any]
    risk_level: RiskLevel
    approved: bool
    result: str = ""
    agent: str = ""


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""

    allowed: bool
    reason: str = ""
    risk_level: RiskLevel = RiskLevel.SAFE
    requires_confirmation: bool = False
    warning: str = ""


# =============================================================================
# Layer 1: Tool Risk Classification
# =============================================================================

TOOL_RISK_MAP: dict[str, RiskLevel] = {
    # Safe — read-only
    "get_system_snapshot": RiskLevel.SAFE,
    "get_cpu_info": RiskLevel.SAFE,
    "get_memory_info": RiskLevel.SAFE,
    "get_disk_info": RiskLevel.SAFE,
    "get_top_processes": RiskLevel.SAFE,
    "get_process_detail": RiskLevel.SAFE,
    "get_services": RiskLevel.SAFE,
    "get_failed_services": RiskLevel.SAFE,
    "get_service_detail": RiskLevel.SAFE,
    "identify_bloatware_services": RiskLevel.SAFE,
    "get_all_drivers": RiskLevel.SAFE,
    "get_problem_drivers": RiskLevel.SAFE,
    "get_driver_summary": RiskLevel.SAFE,
    "get_recent_errors": RiskLevel.SAFE,
    "get_bsod_events": RiskLevel.SAFE,
    "get_crash_dumps": RiskLevel.SAFE,
    "get_event_log_summary": RiskLevel.SAFE,
    "get_disk_health": RiskLevel.SAFE,
    "get_disk_health_summary": RiskLevel.SAFE,
    "scan_temp_files": RiskLevel.SAFE,
    "get_recycle_bin_size": RiskLevel.SAFE,
    "get_power_plans": RiskLevel.SAFE,
    "get_memory_diagnostics": RiskLevel.SAFE,
    "get_system_boot_time": RiskLevel.SAFE,
    "get_startup_programs": RiskLevel.SAFE,

    # Caution — reversible but impactful
    "restart_service": RiskLevel.CAUTION,
    "start_service": RiskLevel.CAUTION,
    "stop_service": RiskLevel.CAUTION,
    "set_power_plan": RiskLevel.CAUTION,
    "flush_dns_cache": RiskLevel.CAUTION,
    "optimize_visual_effects": RiskLevel.CAUTION,

    # Dangerous — destructive or hard to reverse
    "kill_process": RiskLevel.DANGEROUS,
    "clean_temp_files": RiskLevel.DANGEROUS,
    "scan_large_files": RiskLevel.CAUTION,
}

# =============================================================================
# Layer 3: Blocklists — NEVER touch these
# =============================================================================

# Critical Windows processes that must never be killed
PROTECTED_PROCESSES: set[str] = {
    "system",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "dwm.exe",
    "explorer.exe",
    "taskmgr.exe",
    "registry",
    "memory compression",
    "system idle process",
    "secure system",
    "ntoskrnl.exe",
    "conhost.exe",
    "dllhost.exe",
    "sihost.exe",
    "fontdrvhost.exe",
    "spoolsv.exe",
}

# Critical services that must never be stopped/disabled
PROTECTED_SERVICES: set[str] = {
    "wuauserv",  # Windows Update
    "rpcss",  # RPC
    "dcomlaunch",  # DCOM
    "eventlog",  # Event Log
    "plugplay",  # Plug and Play
    "samss",  # Security Accounts Manager
    "schedule",  # Task Scheduler
    "sens",  # System Event Notification
    "windefend",  # Windows Defender
    "mpssvc",  # Windows Firewall
    "bits",  # Background Intelligent Transfer
    "cryptsvc",  # Cryptographic Services
    "dnscache",  # DNS Client
    "dhcp",  # DHCP Client
    "nsi",  # Network Store Interface
    "lanmanserver",  # Server (file sharing)
    "lanmanworkstation",  # Workstation
    "netlogon",  # Net Logon
    "power",  # Power
    "profisvc",  # User Profile Service
    "audiosrv",  # Windows Audio
    "spooler",  # Print Spooler
    "themes",  # Themes
    "winmgmt",  # WMI
}

# Paths that must NEVER be deleted from
PROTECTED_PATHS: set[str] = {
    "c:\\windows\\system32",
    "c:\\windows\\syswow64",
    "c:\\windows\\winsxs",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\users\\default",
    "c:\\windows\\boot",
    "c:\\windows\\servicing",
    "c:\\windows\\assembly",
}

# PIDs that must never be killed
PROTECTED_PIDS: set[int] = {0, 4}  # System Idle Process, System


# =============================================================================
# Layer 4: Output Validation
# =============================================================================

class GuardrailEngine:
    """Central guardrail engine that validates all agent actions."""

    def __init__(self) -> None:
        self._action_log: list[ActionRecord] = []

    def check_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> GuardrailResult:
        """Validate a tool call before execution.

        Returns a GuardrailResult indicating whether the action is allowed.
        """
        # Unknown tool — block by default
        risk = TOOL_RISK_MAP.get(tool_name)
        if risk is None:
            return GuardrailResult(
                allowed=False,
                reason=f"Unknown tool '{tool_name}' — blocked by default",
                risk_level=RiskLevel.DANGEROUS,
            )

        # Safe tools always allowed
        if risk == RiskLevel.SAFE:
            return GuardrailResult(allowed=True, risk_level=RiskLevel.SAFE)

        # Run specific validators
        block_result = self._check_blocklists(tool_name, arguments)
        if not block_result.allowed:
            return block_result

        # Caution and Dangerous tools require confirmation
        return GuardrailResult(
            allowed=True,
            risk_level=risk,
            requires_confirmation=True,
            warning=self._build_warning(tool_name, arguments, risk),
        )

    def _check_blocklists(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> GuardrailResult:
        """Check hard blocklists — these are never allowed."""

        # Kill process checks
        if tool_name == "kill_process":
            pid = arguments.get("pid", 0)
            if pid in PROTECTED_PIDS:
                return GuardrailResult(
                    allowed=False,
                    reason=f"PID {pid} is a critical system process and cannot be killed",
                    risk_level=RiskLevel.DANGEROUS,
                )

            # Try to check process name
            try:
                import psutil

                proc = psutil.Process(pid)
                name = proc.name().lower()
                if name in PROTECTED_PROCESSES:
                    return GuardrailResult(
                        allowed=False,
                        reason=f"Process '{name}' (PID {pid}) is a critical system process",
                        risk_level=RiskLevel.DANGEROUS,
                    )
            except Exception:
                pass  # Process may not exist, let it fail at execution

        # Service management checks
        if tool_name in ("stop_service", "restart_service"):
            service_name = arguments.get("name", "").lower()
            if service_name in PROTECTED_SERVICES:
                return GuardrailResult(
                    allowed=False,
                    reason=f"Service '{service_name}' is a critical system service",
                    risk_level=RiskLevel.DANGEROUS,
                )

        # File cleanup path checks
        if tool_name == "clean_temp_files":
            target_path = arguments.get("target_path", "").lower().replace("/", "\\")
            for protected in PROTECTED_PATHS:
                if target_path.startswith(protected):
                    return GuardrailResult(
                        allowed=False,
                        reason=f"Path '{target_path}' is a protected system directory",
                        risk_level=RiskLevel.DANGEROUS,
                    )

        return GuardrailResult(allowed=True)

    def _build_warning(
        self, tool_name: str, arguments: dict[str, Any], risk: RiskLevel
    ) -> str:
        """Build a human-readable warning for a risky action."""
        warnings = {
            "kill_process": f"Kill process PID {arguments.get('pid', '?')}",
            "stop_service": f"Stop service '{arguments.get('name', '?')}'",
            "restart_service": f"Restart service '{arguments.get('name', '?')}'",
            "start_service": f"Start service '{arguments.get('name', '?')}'",
            "clean_temp_files": f"Delete files in '{arguments.get('target_path', '?')}'",
            "set_power_plan": f"Change power plan to GUID {arguments.get('guid', '?')}",
            "optimize_visual_effects": "Set visual effects to 'best performance'",
            "flush_dns_cache": "Flush DNS resolver cache",
        }
        action = warnings.get(tool_name, f"Execute {tool_name}")
        risk_label = "WARNING" if risk == RiskLevel.CAUTION else "DANGER"
        return f"[{risk_label}] {action}"

    def log_action(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: RiskLevel,
        approved: bool,
        result: str = "",
        agent: str = "",
    ) -> None:
        """Log an action to the audit trail."""
        record = ActionRecord(
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level,
            approved=approved,
            result=result[:500],  # Cap result size
            agent=agent,
        )
        self._action_log.append(record)
        logger.info(
            "action_logged",
            tool=tool_name,
            risk=risk_level.value,
            approved=approved,
            agent=agent,
        )

    def get_action_log(self, limit: int = 50) -> list[dict]:
        """Get recent action log entries."""
        entries = self._action_log[-limit:]
        return [
            {
                "timestamp": e.timestamp,
                "tool": e.tool_name,
                "args": e.arguments,
                "risk": e.risk_level.value,
                "approved": e.approved,
                "result": e.result,
                "agent": e.agent,
            }
            for e in entries
        ]

    def validate_llm_output(self, content: str) -> GuardrailResult:
        """Validate LLM text output for dangerous patterns.

        Catches cases where the LLM tries to do something risky
        outside of the tool-calling framework.
        """
        dangerous_patterns = [
            (r"rm\s+-rf\s+/", "Attempted recursive delete of root"),
            (r"format\s+[a-z]:", "Attempted drive format"),
            (r"del\s+/s\s+/q\s+c:\\windows", "Attempted Windows directory deletion"),
            (r"reg\s+delete\s+hklm", "Attempted registry deletion"),
            (r"bcdedit\s+/delete", "Attempted boot config modification"),
            (r"diskpart", "Attempted disk partitioning"),
            (r"cipher\s+/w", "Attempted drive wipe"),
        ]

        lower_content = content.lower()
        for pattern, description in dangerous_patterns:
            if re.search(pattern, lower_content):
                return GuardrailResult(
                    allowed=False,
                    reason=f"Dangerous pattern detected: {description}",
                    risk_level=RiskLevel.DANGEROUS,
                )

        return GuardrailResult(allowed=True)
