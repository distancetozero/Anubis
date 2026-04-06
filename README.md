# Anubis - PC Guardian

AI-powered Windows PC optimization assistant using local LLMs and multi-agent orchestration.

Anubis is an open-source tool that uses a swarm of specialist AI agents running on a **local LLM** (no cloud dependencies) to monitor, diagnose, and optimize your Windows PC.

## What It Does

- **System Health Monitoring** - CPU, memory, disk, network, temperatures
- **Service Management** - Audit services, detect failures, identify bloatware
- **Driver Analysis** - Find outdated, unsigned, or problematic drivers
- **Fault Diagnostics** - Parse event logs, BSOD analysis, crash dump investigation
- **Performance Tuning** - Power plans, startup optimization, boot time analysis
- **Disk Cleanup** - Temp files, large file scanning, recycle bin management

## Architecture

Anubis uses a **supervisor multi-agent pattern** powered by [LangGraph](https://github.com/langchain-ai/langgraph):

```
User Query
    |
    v
[Orchestrator Agent] -- routes to specialist -->
    |
    +-- [Health Monitor Agent]
    +-- [Service Manager Agent]
    +-- [Driver Analyst Agent]
    +-- [Fault Diagnostician Agent]
    +-- [Performance Tuner Agent]
    +-- [Cleanup Agent]
    |
    v
[Orchestrator] -- synthesizes findings --> Response
```

Each specialist agent has access to specific system tools (PowerShell, WMI, psutil) scoped to its domain. The orchestrator decides which specialist(s) to invoke based on the user's query.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Orchestration | LangGraph |
| Local LLM | Ollama (Qwen3, Mistral, etc.) |
| System Monitoring | psutil, WMI, PowerShell |
| Data Storage | SQLite + SQLAlchemy |
| API | FastAPI |
| CLI | Typer + Rich |
| Config | Pydantic + YAML |

## Prerequisites

- **Windows 10/11**
- **Python 3.11+**
- **[Ollama](https://ollama.ai)** installed and running

## Quick Start

### 1. Install Ollama and pull a model

```bash
# Install Ollama from https://ollama.ai
# Then pull a model with tool-calling support:
ollama pull qwen3:14b
```

### 2. Install Anubis

```bash
git clone https://github.com/YOUR_USERNAME/Anubis.git
cd Anubis
pip install -e ".[dev]"
```

### 3. Run a quick system scan

```bash
anubis scan
```

### 4. Start interactive chat

```bash
anubis chat
```

### 5. Start the web dashboard

```bash
anubis serve
```

## Configuration

Create a config file with defaults:

```bash
anubis init
```

This creates `anubis.yaml`:

```yaml
ollama:
  host: http://localhost:11434
  model: qwen3:14b
  temperature: 0.1
  context_length: 32768

monitoring:
  poll_interval_seconds: 30
  cpu_alert_threshold: 90.0
  memory_alert_threshold: 85.0
  disk_usage_alert_threshold: 90.0

agents:
  orchestrator_mode: supervisor
  max_agent_iterations: 10
  enable_auto_fix: false  # Requires confirmation for destructive actions
```

## Recommended Models

| Model | Size | VRAM | Best For |
|-------|------|------|----------|
| `qwen3:14b` | ~8GB | 10GB+ | Best overall for tool calling |
| `qwen3:7b` | ~4GB | 6GB+ | Good balance of speed/quality |
| `mistral:7b` | ~4GB | 6GB+ | Fast, solid tool calling |
| `command-r:35b` | ~20GB | 24GB+ | Best quality, needs big GPU |

## API Endpoints

When running `anubis serve`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Check Ollama connectivity |
| `/chat` | POST | Send a query to the agent system |
| `/snapshot` | GET | Real-time system health snapshot |
| `/services` | GET | List all Windows services |
| `/services/failed` | GET | List failed auto-start services |
| `/drivers/summary` | GET | Driver health summary |
| `/events/errors` | GET | Recent error events |
| `/disks/health` | GET | Disk SMART health data |
| `/processes/top` | GET | Top resource-consuming processes |
| `/cleanup/scan` | GET | Scan for cleanable temp files |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/
```

## Safety

Anubis is designed with safety in mind:

- **No auto-fix by default** - Destructive actions require explicit user confirmation
- **No cloud dependency** - All LLM inference runs locally via Ollama
- **Scoped tool access** - Each agent only has access to tools relevant to its domain
- **Admin actions flagged** - Operations requiring admin privileges are clearly marked
- **Read-first approach** - Agents gather data and recommend before acting

## License

MIT License - see [LICENSE](LICENSE) for details.
