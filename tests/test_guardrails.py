"""Tests for the guardrail safety system."""

from anubis.core.guardrails import GuardrailEngine, RiskLevel


def test_safe_tool_allowed():
    engine = GuardrailEngine()
    result = engine.check_tool_call("get_cpu_info", {})
    assert result.allowed
    assert result.risk_level == RiskLevel.SAFE
    assert not result.requires_confirmation


def test_dangerous_tool_requires_confirmation():
    engine = GuardrailEngine()
    result = engine.check_tool_call("kill_process", {"pid": 12345})
    assert result.allowed
    assert result.risk_level == RiskLevel.DANGEROUS
    assert result.requires_confirmation


def test_blocked_critical_process():
    engine = GuardrailEngine()
    # PID 4 is the System process — must never be killed
    result = engine.check_tool_call("kill_process", {"pid": 4})
    assert not result.allowed
    assert "critical" in result.reason.lower()


def test_blocked_critical_service():
    engine = GuardrailEngine()
    result = engine.check_tool_call("stop_service", {"name": "rpcss"})
    assert not result.allowed
    assert "critical" in result.reason.lower()


def test_blocked_protected_path():
    engine = GuardrailEngine()
    result = engine.check_tool_call("clean_temp_files", {"target_path": "C:\\Windows\\System32"})
    assert not result.allowed
    assert "protected" in result.reason.lower()


def test_unknown_tool_blocked():
    engine = GuardrailEngine()
    result = engine.check_tool_call("rm_rf_everything", {})
    assert not result.allowed


def test_output_validation_safe():
    engine = GuardrailEngine()
    result = engine.validate_llm_output("Your CPU is at 45% which is normal.")
    assert result.allowed


def test_output_validation_dangerous():
    engine = GuardrailEngine()
    result = engine.validate_llm_output("Run this command: rm -rf / to fix it")
    assert not result.allowed


def test_action_logging():
    engine = GuardrailEngine()
    engine.log_action("get_cpu_info", {}, RiskLevel.SAFE, approved=True, agent="health_monitor")
    log = engine.get_action_log()
    assert len(log) == 1
    assert log[0]["tool"] == "get_cpu_info"
    assert log[0]["approved"] is True
