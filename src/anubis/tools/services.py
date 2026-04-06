"""Windows service monitoring and management."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class ServiceInfo:
    name: str
    display_name: str
    status: str  # Running, Stopped, Paused, etc.
    start_type: str  # Automatic, Manual, Disabled
    pid: int | None = None
    description: str = ""


def get_services() -> list[ServiceInfo]:
    """Get all Windows services and their status."""
    script = (
        "Get-Service | Select-Object Name, DisplayName, Status, StartType | "
        "ConvertTo-Json -Compress"
    )
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]

    services = []
    for svc in data:
        services.append(
            ServiceInfo(
                name=svc.get("Name", ""),
                display_name=svc.get("DisplayName", ""),
                status=str(svc.get("Status", "")),
                start_type=str(svc.get("StartType", "")),
            )
        )
    return services


def get_service_detail(name: str) -> ServiceInfo | None:
    """Get detailed info for a specific service."""
    script = (
        f"Get-Service -Name '{name}' -ErrorAction SilentlyContinue | "
        f"Select-Object Name, DisplayName, Status, StartType | ConvertTo-Json"
    )
    result = _run_powershell(script)
    if not result:
        return None

    import json

    svc = json.loads(result)
    return ServiceInfo(
        name=svc.get("Name", ""),
        display_name=svc.get("DisplayName", ""),
        status=str(svc.get("Status", "")),
        start_type=str(svc.get("StartType", "")),
    )


def get_failed_services() -> list[ServiceInfo]:
    """Get services that should be running but aren't (auto-start services that are stopped)."""
    script = (
        "Get-Service | Where-Object { $_.StartType -eq 'Automatic' -and $_.Status -ne 'Running' } | "
        "Select-Object Name, DisplayName, Status, StartType | ConvertTo-Json -Compress"
    )
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]

    return [
        ServiceInfo(
            name=svc.get("Name", ""),
            display_name=svc.get("DisplayName", ""),
            status=str(svc.get("Status", "")),
            start_type=str(svc.get("StartType", "")),
        )
        for svc in data
    ]


def restart_service(name: str) -> str:
    """Restart a Windows service. Requires admin privileges."""
    result = _run_powershell(f"Restart-Service -Name '{name}' -Force -PassThru | ConvertTo-Json")
    return result or f"Failed to restart service '{name}'"


def stop_service(name: str) -> str:
    """Stop a Windows service. Requires admin privileges."""
    result = _run_powershell(f"Stop-Service -Name '{name}' -Force -PassThru | ConvertTo-Json")
    return result or f"Failed to stop service '{name}'"


def start_service(name: str) -> str:
    """Start a Windows service. Requires admin privileges."""
    result = _run_powershell(f"Start-Service -Name '{name}' -PassThru | ConvertTo-Json")
    return result or f"Failed to start service '{name}'"


# Known bloatware / unnecessary services that are safe to disable
KNOWN_BLOATWARE_SERVICES = {
    "DiagTrack": "Connected User Experiences and Telemetry",
    "dmwappushservice": "WAP Push Message Routing Service",
    "SysMain": "Superfetch (can cause high disk on HDDs)",
    "WSearch": "Windows Search (high disk usage on HDDs)",
    "XblAuthManager": "Xbox Live Auth Manager",
    "XblGameSave": "Xbox Live Game Save",
    "XboxGipSvc": "Xbox Accessory Management",
    "XboxNetApiSvc": "Xbox Live Networking",
}


def identify_bloatware_services() -> list[ServiceInfo]:
    """Identify running services commonly considered bloatware."""
    all_services = get_services()
    return [
        svc
        for svc in all_services
        if svc.name in KNOWN_BLOATWARE_SERVICES and svc.status == "4"  # Running
    ]


def _run_powershell(script: str) -> str:
    """Execute a PowerShell script and return stdout."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
