"""Performance tuning tools: power plans, memory, startup optimization."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class PowerPlan:
    guid: str
    name: str
    is_active: bool


def get_power_plans() -> list[PowerPlan]:
    """Get available power plans and which is active."""
    script = """
    $plans = powercfg /list
    $active = (powercfg /getactivescheme) -match '([a-f0-9-]{36})'
    $activeGuid = $Matches[1]
    $result = @()
    foreach ($line in $plans) {
        if ($line -match '([a-f0-9-]{36})\\s+\\((.+?)\\)') {
            $result += [PSCustomObject]@{
                Guid = $Matches[1]
                Name = $Matches[2]
                IsActive = ($Matches[1] -eq $activeGuid)
            }
        }
    }
    $result | ConvertTo-Json -Compress
    """
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]

    return [
        PowerPlan(
            guid=p.get("Guid", ""),
            name=p.get("Name", ""),
            is_active=p.get("IsActive", False),
        )
        for p in data
    ]


def set_power_plan(guid: str) -> str:
    """Set the active power plan by GUID."""
    result = _run_powershell(f"powercfg /setactive {guid}; Write-Output 'Power plan set'")
    return result or "Failed to set power plan"


def get_memory_diagnostics() -> dict:
    """Get memory usage diagnostics."""
    script = """
    $os = Get-CimInstance Win32_OperatingSystem
    $procs = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 Name,
        @{N='MemoryMB'; E={[math]::Round($_.WorkingSet64 / 1MB, 1)}},
        @{N='PrivateMB'; E={[math]::Round($_.PrivateMemorySize64 / 1MB, 1)}}

    @{
        TotalVisibleMB = [math]::Round($os.TotalVisibleMemorySize / 1KB, 0)
        FreePhysicalMB = [math]::Round($os.FreePhysicalMemory / 1KB, 0)
        TotalVirtualMB = [math]::Round($os.TotalVirtualMemorySize / 1KB, 0)
        FreeVirtualMB = [math]::Round($os.FreeVirtualMemory / 1KB, 0)
        TopConsumers = $procs
    } | ConvertTo-Json -Compress -Depth 3
    """
    result = _run_powershell(script)
    if not result:
        return {}

    import json
    return json.loads(result)


def get_startup_impact() -> list[dict]:
    """Get startup programs with their impact assessment."""
    script = """
    Get-CimInstance Win32_StartupCommand |
        Select-Object Name, Command, Location, User |
        ConvertTo-Json -Compress
    """
    result = _run_powershell(script)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]
    return data


def optimize_visual_effects() -> str:
    """Set Windows visual effects to 'Adjust for best performance'.

    This modifies registry keys to disable animations, transparency, etc.
    """
    script = """
    $path = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects'
    Set-ItemProperty -Path $path -Name 'VisualFXSetting' -Value 2 -ErrorAction SilentlyContinue
    Write-Output 'Visual effects set to best performance'
    """
    return _run_powershell(script) or "Failed to optimize visual effects"


def get_system_boot_time() -> dict:
    """Analyze system boot time and what's slowing it down."""
    script = """
    $boot = Get-WinEvent -FilterHashtable @{
        LogName = 'Microsoft-Windows-Diagnostics-Performance/Operational'
        Id = 100
    } -MaxEvents 1 -ErrorAction SilentlyContinue

    if ($boot) {
        $xml = [xml]$boot.ToXml()
        $ns = New-Object Xml.XmlNamespaceManager($xml.NameTable)
        $ns.AddNamespace('e', $xml.DocumentElement.NamespaceURI)
        $bootTime = $xml.SelectSingleNode('//e:EventData/e:Data[@Name="BootTime"]', $ns).'#text'

        @{
            LastBootTimeMs = $bootTime
            LastBootTimeSec = [math]::Round([int]$bootTime / 1000, 1)
            EventTime = $boot.TimeCreated.ToString('o')
        } | ConvertTo-Json
    } else {
        @{ Error = 'Boot performance data not available' } | ConvertTo-Json
    }
    """
    result = _run_powershell(script)
    if not result:
        return {"Error": "Could not retrieve boot time data"}

    import json
    return json.loads(result)


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
