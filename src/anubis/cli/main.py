"""Anubis CLI - Interactive PC optimization assistant."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from anubis.core.config import AnubisConfig

app = typer.Typer(
    name="anubis",
    help="AI-powered Windows PC optimization assistant",
    no_args_is_help=True,
)
console = Console()


@app.command()
def chat() -> None:
    """Start an interactive chat session with Anubis."""
    asyncio.run(_chat_loop())


async def _chat_loop() -> None:
    """Main interactive chat loop."""
    config = AnubisConfig.load()

    # Late imports to avoid slow startup for other commands
    from anubis.agents.graph import AnubisAgentGraph
    from anubis.core.guardrails import GuardrailEngine
    from anubis.core.logging import setup_logging
    from anubis.llm.router import LLMRouter
    from anubis.llm.tool_registry import build_default_registry

    setup_logging(debug=False)

    console.print(
        Panel.fit(
            "[bold cyan]Anubis[/bold cyan] - PC Guardian\n"
            "[dim]AI-powered Windows optimization assistant[/dim]\n\n"
            "Type your question or command. Type [bold]quit[/bold] to exit.\n"
            "Examples:\n"
            '  "Check my PC health"\n'
            '  "Why is my computer slow?"\n'
            '  "Are there any driver issues?"\n'
            '  "Clean up temp files"',
            border_style="cyan",
        )
    )

    # Initialize the LLM router (tries Ollama first, then Groq)
    router = LLMRouter(config)

    console.print("[dim]Checking available LLM providers...[/dim]")
    provider_status = await router.check_providers()

    connected = False
    for name, healthy in provider_status.items():
        status = "[green]connected[/green]" if healthy else "[red]unavailable[/red]"
        console.print(f"  {name}: {status}")
        if healthy:
            connected = True

    if not connected:
        console.print(
            "\n[bold red]No LLM providers available.[/bold red]\n"
            "Options:\n"
            "  1. Start Ollama locally: ollama serve\n"
            "  2. Set GROQ_API_KEY for free cloud inference: https://console.groq.com\n"
            "  3. Configure another provider in anubis.yaml"
        )
        await router.close()
        return

    console.print("[green]Ready![/green]\n")

    registry = build_default_registry()
    guardrails = GuardrailEngine()
    graph = AnubisAgentGraph(router, registry, guardrails)

    while True:
        try:
            query = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            break

        if query.lower() in ("quit", "exit", "q"):
            break

        if query.lower() == "status":
            _print_router_status(router)
            continue

        if query.lower() == "alerts":
            console.print("[dim]No watchdog alerts yet.[/dim]")
            continue

        if not query.strip():
            continue

        console.print("[dim]Thinking...[/dim]")

        try:
            response = await graph.run(query)
            console.print()
            console.print(Panel(Markdown(response), title="Anubis", border_style="green"))

            # Show pending actions if any
            # (accessed via graph state — in production this would be tracked)
            console.print()
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

    await router.close()
    console.print("[dim]Goodbye![/dim]")


def _print_router_status(router) -> None:
    """Print LLM router status."""
    from anubis.llm.router import LLMRouter

    status = router.get_status()
    table = Table(title="LLM Router Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Available")
    table.add_column("Requests")
    table.add_column("Failures")
    table.add_column("Avg Latency")
    table.add_column("Circuit Breaker")

    for name, info in status["providers"].items():
        avail = "[green]Yes[/green]" if info["available"] else "[red]No[/red]"
        cb = "[red]OPEN[/red]" if info["circuit_breaker_open"] else "[green]Closed[/green]"
        table.add_row(
            name,
            avail,
            str(info["total_requests"]),
            str(info["total_failures"]),
            f"{info['avg_latency_ms']}ms",
            cb,
        )
    console.print(table)


@app.command()
def scan() -> None:
    """Run a quick system health scan and print results."""
    asyncio.run(_quick_scan())


async def _quick_scan() -> None:
    """Perform a quick system health scan."""
    from anubis.tools.system_health import get_system_snapshot

    console.print("[bold cyan]Running system health scan...[/bold cyan]\n")

    snapshot = get_system_snapshot()

    # System info
    info_table = Table(title="System Info")
    info_table.add_column("Property", style="cyan")
    info_table.add_column("Value")
    info_table.add_row("Hostname", snapshot.hostname)
    info_table.add_row("OS", snapshot.os_version)
    info_table.add_row("Uptime", f"{snapshot.uptime_hours:.1f} hours")
    console.print(info_table)
    console.print()

    # CPU
    cpu_color = "green" if snapshot.cpu.usage_percent < 70 else "yellow" if snapshot.cpu.usage_percent < 90 else "red"
    console.print(
        f"[bold]CPU:[/bold] [{cpu_color}]{snapshot.cpu.usage_percent}%[/{cpu_color}] "
        f"({snapshot.cpu.core_count_physical}C/{snapshot.cpu.core_count_logical}T "
        f"@ {snapshot.cpu.frequency_mhz}MHz)"
    )

    # Memory
    mem_color = "green" if snapshot.memory.usage_percent < 70 else "yellow" if snapshot.memory.usage_percent < 85 else "red"
    console.print(
        f"[bold]Memory:[/bold] [{mem_color}]{snapshot.memory.usage_percent}%[/{mem_color}] "
        f"({snapshot.memory.used_gb}/{snapshot.memory.total_gb} GB)"
    )

    # Disks
    console.print("\n[bold]Disks:[/bold]")
    for disk in snapshot.disks:
        disk_color = "green" if disk.usage_percent < 80 else "yellow" if disk.usage_percent < 90 else "red"
        console.print(
            f"  {disk.mountpoint} [{disk_color}]{disk.usage_percent}%[/{disk_color}] "
            f"({disk.free_gb} GB free / {disk.total_gb} GB total)"
        )

    # Temperatures
    if snapshot.temperatures:
        console.print("\n[bold]Temperatures:[/bold]")
        for temp in snapshot.temperatures:
            temp_color = "green" if temp.current_celsius < 70 else "yellow" if temp.current_celsius < 85 else "red"
            console.print(f"  {temp.label}: [{temp_color}]{temp.current_celsius}C[/{temp_color}]")

    console.print()


@app.command()
def providers() -> None:
    """Check status of available LLM providers."""
    asyncio.run(_check_providers())


async def _check_providers() -> None:
    """Check all configured LLM providers."""
    config = AnubisConfig.load()
    from anubis.llm.router import LLMRouter

    router = LLMRouter(config)
    status = await router.check_providers()

    table = Table(title="LLM Provider Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Status")
    table.add_column("Model")
    table.add_column("Endpoint")

    for name, healthy in status.items():
        s = "[green]Available[/green]" if healthy else "[red]Unavailable[/red]"
        if name == "ollama":
            table.add_row(name, s, config.ollama.model, config.ollama.host)
        elif name == "groq":
            key_status = "key set" if config.groq.api_key or __import__("os").environ.get("GROQ_API_KEY") else "NO KEY"
            table.add_row(name, s, config.groq.model, f"{config.groq.base_url} ({key_status})")

    console.print(table)
    await router.close()


@app.command()
def config() -> None:
    """Show current configuration."""
    cfg = AnubisConfig.load()
    console.print_json(cfg.model_dump_json(indent=2))


@app.command()
def init() -> None:
    """Create a default configuration file."""
    cfg = AnubisConfig()
    cfg.save()
    console.print("[green]Created anubis.yaml with default settings.[/green]")
    console.print(
        "[dim]Tip: Set GROQ_API_KEY environment variable for free cloud LLM access.[/dim]"
    )


@app.command()
def serve() -> None:
    """Start the Anubis web dashboard."""
    import uvicorn

    config = AnubisConfig.load()
    console.print(
        f"[bold cyan]Starting Anubis dashboard at "
        f"http://{config.api.host}:{config.api.port}[/bold cyan]"
    )
    uvicorn.run(
        "anubis.api.app:create_app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        factory=True,
    )


@app.command()
def knowledge() -> None:
    """Show knowledge base statistics."""
    from anubis.knowledge.lookup import get_knowledge_stats

    stats = get_knowledge_stats()
    table = Table(title="Anubis Knowledge Base")
    table.add_column("Category", style="cyan")
    table.add_column("Entries", justify="right")
    table.add_row("BSOD Stop Codes", str(stats["bsod_codes"]))
    table.add_row("Event ID References", str(stats["event_ids"]))
    table.add_row("Service References", str(stats["service_references"]))
    table.add_row("Total", str(sum(stats.values())), style="bold")
    console.print(table)


if __name__ == "__main__":
    app()
