"""Windows Event Log analysis for fault diagnostics."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class EventLogEntry:
    time_created: str
    level: str  # Error, Warning, Critical, Information
    source: str
    event_id: int
    message: str
    log_name: str


def get_recent_errors(hours: int = 24, max_entries: int = 50) -> list[EventLogEntry]:
    """Get recent error and critical events from System and Application logs."""
    script = f"""
    $cutoff = (Get-Date).AddHours(-{hours})
    $events = @()
    foreach ($log in @('System', 'Application')) {{
        $events += Get-WinEvent -FilterHashtable @{{
            LogName = $log
            Level = @(1, 2)  # Critical, Error
            StartTime = $cutoff
        }} -MaxEvents {max_entries} -ErrorAction SilentlyContinue |
        Select-Object TimeCreated, LevelDisplayName, ProviderName, Id,
            @{{N='Msg'; E={{$_.Message.Substring(0, [Math]::Min(500, $_.Message.Length))}}}},
            LogName
    }}
    $events | Sort-Object TimeCreated -Descending |
        Select-Object -First {max_entries} |
        ConvertTo-Json -Compress
    """
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]

    return [
        EventLogEntry(
            time_created=_extract_date(e.get("TimeCreated", "")),
            level=e.get("LevelDisplayName", "Unknown"),
            source=e.get("ProviderName", ""),
            event_id=e.get("Id", 0),
            message=e.get("Msg", ""),
            log_name=e.get("LogName", ""),
        )
        for e in data
    ]


def get_bsod_events(max_entries: int = 10) -> list[EventLogEntry]:
    """Get Blue Screen of Death (BSOD) events from BugCheck."""
    script = f"""
    Get-WinEvent -FilterHashtable @{{
        LogName = 'System'
        ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting'
    }} -MaxEvents {max_entries} -ErrorAction SilentlyContinue |
    Select-Object TimeCreated, LevelDisplayName, ProviderName, Id,
        @{{N='Msg'; E={{$_.Message.Substring(0, [Math]::Min(500, $_.Message.Length))}}}},
        LogName |
    ConvertTo-Json -Compress
    """
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]

    return [
        EventLogEntry(
            time_created=_extract_date(e.get("TimeCreated", "")),
            level=e.get("LevelDisplayName", "Error"),
            source=e.get("ProviderName", ""),
            event_id=e.get("Id", 0),
            message=e.get("Msg", ""),
            log_name="System",
        )
        for e in data
    ]


def get_crash_dumps() -> list[dict]:
    """List available crash dump files."""
    script = """
    $dumps = @()
    $paths = @(
        "$env:SystemRoot\\Minidump",
        "$env:SystemRoot\\MEMORY.DMP"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            if ((Get-Item $p).PSIsContainer) {
                $dumps += Get-ChildItem $p -Filter *.dmp |
                    Select-Object Name, Length,
                        @{N='LastWriteTime'; E={$_.LastWriteTime.ToString('o')}}
            } else {
                $item = Get-Item $p
                $dumps += [PSCustomObject]@{
                    Name = $item.Name
                    Length = $item.Length
                    LastWriteTime = $item.LastWriteTime.ToString('o')
                }
            }
        }
    }
    $dumps | ConvertTo-Json -Compress
    """
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]
    return data


def get_event_log_summary(hours: int = 24) -> dict:
    """Get a summary of event log activity."""
    script = f"""
    $cutoff = (Get-Date).AddHours(-{hours})
    $summary = @{{}}
    foreach ($log in @('System', 'Application')) {{
        foreach ($level in @(1, 2, 3)) {{
            $count = (Get-WinEvent -FilterHashtable @{{
                LogName = $log
                Level = $level
                StartTime = $cutoff
            }} -ErrorAction SilentlyContinue | Measure-Object).Count
            $levelName = switch ($level) {{ 1 {{'Critical'}} 2 {{'Error'}} 3 {{'Warning'}} }}
            $summary["$log`_$levelName"] = $count
        }}
    }}
    $summary | ConvertTo-Json
    """
    result = _run_powershell(script)
    if not result:
        return {}

    import json

    return json.loads(result)


def _extract_date(date_str: str) -> str:
    """Extract ISO date from PowerShell date representation."""
    if isinstance(date_str, str):
        return date_str
    if isinstance(date_str, dict) and "DateTime" in date_str:
        return date_str["DateTime"]
    return str(date_str)


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
