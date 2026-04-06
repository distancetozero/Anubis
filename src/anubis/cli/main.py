"""Anubis CLI - Interactive PC optimization assistant."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.live import Live
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
    from anubis.core.logging import setup_logging
    from anubis.llm.ollama_client import OllamaClient
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

    llm = OllamaClient(config.ollama)

    # Check Ollama connectivity
    console.print("[dim]Checking Ollama connection...[/dim]")
    if not await llm.check_health():
        console.print(
            "[bold red]Cannot connect to Ollama.[/bold red]\n"
            f"Make sure Ollama is running at {config.ollama.host}\n"
            "Install: https://ollama.ai\n"
            f"Then run: ollama pull {config.ollama.model}"
        )
        await llm.close()
        return

    # Ensure model is available
    console.print(f"[dim]Checking model {config.ollama.model}...[/dim]")
    if not await llm.ensure_model():
        console.print(
            f"[bold red]Model {config.ollama.model} not available.[/bold red]\n"
            f"Run: ollama pull {config.ollama.model}"
        )
        await llm.close()
        return

    console.print("[green]Connected to Ollama. Ready![/green]\n")

    registry = build_default_registry()
    graph = AnubisAgentGraph(llm, registry)

    while True:
        try:
            query = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            break

        if query.lower() in ("quit", "exit", "q"):
            break

        if not query.strip():
            continue

        console.print("[dim]Thinking...[/dim]")

        try:
            response = await graph.run(query)
            console.print()
            console.print(Panel(Markdown(response), title="Anubis", border_style="green"))
            console.print()
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

    await llm.close()
    console.print("[dim]Goodbye![/dim]")


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
    console.print(f"[bold]CPU:[/bold] [{cpu_color}]{snapshot.cpu.usage_percent}%[/{cpu_color}] "
                  f"({snapshot.cpu.core_count_physical}C/{snapshot.cpu.core_count_logical}T @ {snapshot.cpu.frequency_mhz}MHz)")

    # Memory
    mem_color = "green" if snapshot.memory.usage_percent < 70 else "yellow" if snapshot.memory.usage_percent < 85 else "red"
    console.print(f"[bold]Memory:[/bold] [{mem_color}]{snapshot.memory.usage_percent}%[/{mem_color}] "
                  f"({snapshot.memory.used_gb}/{snapshot.memory.total_gb} GB)")

    # Disks
    console.print(f"\n[bold]Disks:[/bold]")
    for disk in snapshot.disks:
        disk_color = "green" if disk.usage_percent < 80 else "yellow" if disk.usage_percent < 90 else "red"
        console.print(f"  {disk.mountpoint} [{disk_color}]{disk.usage_percent}%[/{disk_color}] "
                      f"({disk.free_gb} GB free / {disk.total_gb} GB total)")

    # Temperatures
    if snapshot.temperatures:
        console.print(f"\n[bold]Temperatures:[/bold]")
        for temp in snapshot.temperatures:
            temp_color = "green" if temp.current_celsius < 70 else "yellow" if temp.current_celsius < 85 else "red"
            console.print(f"  {temp.label}: [{temp_color}]{temp.current_celsius}C[/{temp_color}]")

    console.print()


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


@app.command()
def serve() -> None:
    """Start the Anubis web dashboard."""
    import uvicorn

    config = AnubisConfig.load()
    console.print(
        f"[bold cyan]Starting Anubis dashboard at http://{config.api.host}:{config.api.port}[/bold cyan]"
    )
    uvicorn.run(
        "anubis.api.app:create_app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        factory=True,
    )


if __name__ == "__main__":
    app()
