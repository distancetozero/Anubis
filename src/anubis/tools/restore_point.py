"""Windows System Restore point management.

Creates restore points before destructive operations so users
can roll back if something goes wrong.
"""

from __future__ import annotations

import subprocess

import structlog

logger = structlog.get_logger("anubis.tools.restore")


def create_restore_point(description: str = "Anubis: Before system changes") -> str:
    """Create a Windows System Restore point.

    Requires administrator privileges.

    Args:
        description: Description for the restore point

    Returns:
        Status message
    """
    script = f"""
    # Enable System Restore on C: if not already enabled
    Enable-ComputerRestore -Drive "C:\\" -ErrorAction SilentlyContinue

    # Create the restore point
    try {{
        Checkpoint-Computer -Description "{description}" -RestorePointType "MODIFY_SETTINGS" -ErrorAction Stop
        Write-Output "SUCCESS: Restore point created - {description}"
    }} catch {{
        # Windows limits restore points to one every 24 hours (unless registry is modified)
        if ($_.Exception.Message -like "*frequency*" -or $_.Exception.Message -like "*1400*") {{
            Write-Output "SKIPPED: Restore point already created within last 24 hours"
        }} else {{
            Write-Output "FAILED: $($_.Exception.Message)"
        }}
    }}
    """
    result = _run_powershell_admin(script)
    logger.info("restore_point_created", result=result, description=description)
    return result or "Failed to create restore point (need admin privileges?)"


def list_restore_points() -> list[dict]:
    """List available system restore points."""
    script = """
    Get-ComputerRestorePoint -ErrorAction SilentlyContinue |
        Select-Object SequenceNumber, Description, CreationTime,
            @{N='Type'; E={
                switch ($_.RestorePointType) {
                    0 {'Application Install'}
                    1 {'Application Uninstall'}
                    6 {'Restore'}
                    7 {'Checkpoint'}
                    10 {'Device Driver Install'}
                    12 {'Modify Settings'}
                    13 {'Cancelled Operation'}
                    default {'Unknown'}
                }
            }} |
        Sort-Object SequenceNumber -Descending |
        Select-Object -First 10 |
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


def check_restore_enabled() -> dict:
    """Check if System Restore is enabled on the system drive."""
    script = """
    $status = Get-ComputerRestorePoint -ErrorAction SilentlyContinue
    $protection = vssadmin list shadowstorage 2>$null

    @{
        Enabled = ($status -ne $null -or $LASTEXITCODE -eq 0)
        RestorePointCount = @($status).Count
    } | ConvertTo-Json
    """
    result = _run_powershell(script)
    if not result:
        return {"Enabled": False, "RestorePointCount": 0}

    import json
    return json.loads(result)


def _run_powershell(script: str) -> str:
    """Execute a PowerShell script."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _run_powershell_admin(script: str) -> str:
    """Execute a PowerShell script (attempts with current privileges)."""
    # Note: In production, Anubis should run elevated for restore points
    return _run_powershell(script)
