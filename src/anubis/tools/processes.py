"""Process monitoring and management."""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    status: str
    username: str | None = None
    create_time: str = ""
    cmdline: str = ""


def get_top_processes(sort_by: str = "cpu", limit: int = 20) -> list[ProcessInfo]:
    """Get top resource-consuming processes.

    Args:
        sort_by: Sort by "cpu" or "memory"
        limit: Max number of processes to return
    """
    procs = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_info", "memory_percent", "status", "username"]
    ):
        try:
            info = proc.info
            procs.append(
                ProcessInfo(
                    pid=info["pid"],
                    name=info["name"] or "Unknown",
                    cpu_percent=info["cpu_percent"] or 0.0,
                    memory_mb=round((info["memory_info"].rss if info["memory_info"] else 0) / (1024**2), 1),
                    memory_percent=round(info["memory_percent"] or 0.0, 1),
                    status=info["status"] or "unknown",
                    username=info.get("username"),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    key = "cpu_percent" if sort_by == "cpu" else "memory_mb"
    procs.sort(key=lambda p: getattr(p, key), reverse=True)
    return procs[:limit]


def get_process_detail(pid: int) -> ProcessInfo | None:
    """Get detailed information about a specific process."""
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            mem = proc.memory_info()
            return ProcessInfo(
                pid=proc.pid,
                name=proc.name(),
                cpu_percent=proc.cpu_percent(interval=0.5),
                memory_mb=round(mem.rss / (1024**2), 1),
                memory_percent=round(proc.memory_percent(), 1),
                status=proc.status(),
                username=proc.username(),
                create_time=str(proc.create_time()),
                cmdline=" ".join(proc.cmdline()),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def kill_process(pid: int) -> str:
    """Kill a process by PID. Returns status message."""
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        proc.wait(timeout=5)
        return f"Process '{name}' (PID {pid}) terminated successfully"
    except psutil.NoSuchProcess:
        return f"Process with PID {pid} not found"
    except psutil.AccessDenied:
        return f"Access denied: cannot terminate PID {pid} (try running as admin)"
    except psutil.TimeoutExpired:
        try:
            proc.kill()
            return f"Process PID {pid} force-killed after timeout"
        except psutil.NoSuchProcess:
            return f"Process PID {pid} already exited"


def get_startup_programs() -> list[dict]:
    """Get programs configured to run at startup."""
    import subprocess

    script = """
    $startup = @()
    # Registry Run keys
    foreach ($path in @(
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run',
        'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run'
    )) {
        if (Test-Path $path) {
            $items = Get-ItemProperty $path -ErrorAction SilentlyContinue
            $items.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object {
                $startup += [PSCustomObject]@{
                    Name = $_.Name
                    Command = $_.Value
                    Location = $path
                }
            }
        }
    }
    $startup | ConvertTo-Json -Compress
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if not result.stdout.strip():
            return []

        import json

        data = json.loads(result.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        return data
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
