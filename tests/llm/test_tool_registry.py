"""Tests for the tool registry."""

import pytest

from anubis.llm.tool_registry import ToolRegistry


def test_register_and_get():
    registry = ToolRegistry()
    registry.register(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "hello",
    )
    tool = registry.get("test_tool")
    assert tool is not None
    assert tool.name == "test_tool"
    assert tool.description == "A test tool"


def test_get_unknown_tool():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_to_ollama_format():
    registry = ToolRegistry()
    registry.register(
        name="my_tool",
        description="Does stuff",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
        handler=lambda x: x,
    )
    tools = registry.to_ollama_format()
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "my_tool"


@pytest.mark.asyncio
async def test_execute_tool():
    registry = ToolRegistry()
    registry.register(
        name="add",
        description="Add numbers",
        parameters={"type": "object", "properties": {}},
        handler=lambda a, b: a + b,
    )
    result = await registry.execute("add", {"a": 2, "b": 3})
    assert "5" in result


@pytest.mark.asyncio
async def test_execute_unknown_tool():
    registry = ToolRegistry()
    result = await registry.execute("nope", {})
    assert "error" in result.lower()
