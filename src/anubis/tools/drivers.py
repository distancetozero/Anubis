"""Windows driver analysis and monitoring."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class DriverInfo:
    device_name: str
    driver_name: str
    driver_version: str
    manufacturer: str
    driver_date: str
    status: str  # OK, Error, Degraded, etc.
    is_signed: bool
    inf_name: str = ""


def get_all_drivers() -> list[DriverInfo]:
    """Get all installed drivers with their details."""
    script = (
        "Get-WmiObject Win32_PnPSignedDriver | "
        "Where-Object { $_.DeviceName -ne $null } | "
        "Select-Object DeviceName, DriverName, DriverVersion, Manufacturer, "
        "DriverDate, Status, IsSigned, InfName | "
        "ConvertTo-Json -Compress"
    )
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]

    return [
        DriverInfo(
            device_name=d.get("DeviceName", "Unknown"),
            driver_name=d.get("DriverName", ""),
            driver_version=d.get("DriverVersion", ""),
            manufacturer=d.get("Manufacturer", ""),
            driver_date=_parse_wmi_date(d.get("DriverDate", "")),
            status=d.get("Status", "Unknown"),
            is_signed=bool(d.get("IsSigned", False)),
            inf_name=d.get("InfName", ""),
        )
        for d in data
    ]


def get_problem_drivers() -> list[DriverInfo]:
    """Get drivers with errors or that are unsigned."""
    all_drivers = get_all_drivers()
    return [
        d
        for d in all_drivers
        if d.status != "OK" or not d.is_signed
    ]


def get_outdated_drivers(days_threshold: int = 365) -> list[DriverInfo]:
    """Get drivers older than the specified threshold."""
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=days_threshold)
    all_drivers = get_all_drivers()

    outdated = []
    for driver in all_drivers:
        if not driver.driver_date:
            continue
        try:
            driver_dt = datetime.fromisoformat(driver.driver_date)
            if driver_dt < cutoff:
                outdated.append(driver)
        except ValueError:
            continue
    return outdated


def get_driver_summary() -> dict:
    """Get a summary of driver health."""
    drivers = get_all_drivers()
    problem = [d for d in drivers if d.status != "OK"]
    unsigned = [d for d in drivers if not d.is_signed]

    return {
        "total_drivers": len(drivers),
        "healthy_drivers": len(drivers) - len(problem),
        "problem_drivers": len(problem),
        "unsigned_drivers": len(unsigned),
        "problems": [
            {"device": d.device_name, "status": d.status, "signed": d.is_signed}
            for d in problem
        ],
    }


def _parse_wmi_date(wmi_date: str) -> str:
    """Convert WMI date format (yyyyMMddHHmmss.ffffff+zzz) to ISO format."""
    if not wmi_date or len(wmi_date) < 8:
        return ""
    try:
        return f"{wmi_date[:4]}-{wmi_date[4:6]}-{wmi_date[6:8]}"
    except (IndexError, ValueError):
        return ""


def _run_powershell(script: str) -> str:
    """Execute a PowerShell script and return stdout."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
