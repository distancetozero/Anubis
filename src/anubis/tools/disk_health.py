"""Disk health monitoring via SMART data and Windows storage APIs."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class SmartAttribute:
    id: int
    name: str
    value: int
    worst: int
    threshold: int
    raw_value: str


@dataclass
class DiskHealthInfo:
    device: str
    model: str
    serial: str
    firmware: str
    size_gb: float
    media_type: str  # SSD, HDD, NVMe
    health_status: str  # Healthy, Warning, Unhealthy
    temperature_celsius: float | None = None
    power_on_hours: int | None = None
    smart_attributes: list[SmartAttribute] | None = None


def get_disk_health() -> list[DiskHealthInfo]:
    """Get health information for all physical disks."""
    script = """
    $disks = Get-PhysicalDisk | Select-Object FriendlyName, SerialNumber,
        FirmwareRevision, Size, MediaType, HealthStatus |
        ConvertTo-Json -Compress

    $reliability = Get-PhysicalDisk | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue |
        Select-Object DeviceId, Temperature, PowerOnHours, ReadErrorsTotal,
        WriteErrorsTotal, Wear |
        ConvertTo-Json -Compress

    @{ Disks = $disks; Reliability = $reliability } | ConvertTo-Json -Compress
    """
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    disks_raw = json.loads(data.get("Disks", "[]"))
    reliability_raw = json.loads(data.get("Reliability", "[]"))

    if isinstance(disks_raw, dict):
        disks_raw = [disks_raw]
    if isinstance(reliability_raw, dict):
        reliability_raw = [reliability_raw]

    # Index reliability data by device ID
    reliability_map = {}
    for r in reliability_raw:
        dev_id = r.get("DeviceId", "")
        reliability_map[dev_id] = r

    disks = []
    for i, disk in enumerate(disks_raw):
        rel = reliability_map.get(str(i), {})
        disks.append(
            DiskHealthInfo(
                device=f"PhysicalDisk{i}",
                model=disk.get("FriendlyName", "Unknown"),
                serial=disk.get("SerialNumber", "").strip(),
                firmware=disk.get("FirmwareRevision", ""),
                size_gb=round(disk.get("Size", 0) / (1024**3), 1),
                media_type=_parse_media_type(disk.get("MediaType", "")),
                health_status=_parse_health(disk.get("HealthStatus", "")),
                temperature_celsius=rel.get("Temperature"),
                power_on_hours=rel.get("PowerOnHours"),
            )
        )
    return disks


def get_disk_health_summary() -> dict:
    """Get a quick summary of disk health across all drives."""
    disks = get_disk_health()
    return {
        "total_disks": len(disks),
        "healthy": sum(1 for d in disks if d.health_status == "Healthy"),
        "warning": sum(1 for d in disks if d.health_status == "Warning"),
        "unhealthy": sum(1 for d in disks if d.health_status == "Unhealthy"),
        "disks": [
            {
                "model": d.model,
                "size_gb": d.size_gb,
                "type": d.media_type,
                "health": d.health_status,
                "temp_c": d.temperature_celsius,
            }
            for d in disks
        ],
    }


def _parse_media_type(media_type: str | int) -> str:
    """Convert WMI MediaType enum to string."""
    mapping = {0: "Unspecified", 3: "HDD", 4: "SSD", 5: "SCM"}
    if isinstance(media_type, int):
        return mapping.get(media_type, "Unknown")
    return str(media_type)


def _parse_health(health: str | int) -> str:
    """Convert WMI HealthStatus enum to string."""
    mapping = {0: "Healthy", 1: "Warning", 2: "Unhealthy"}
    if isinstance(health, int):
        return mapping.get(health, "Unknown")
    return str(health)


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
