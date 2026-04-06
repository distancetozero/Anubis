"""System cleanup utilities: temp files, disk space recovery."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanupTarget:
    path: str
    size_mb: float
    file_count: int
    description: str


@dataclass
class CleanupResult:
    targets_cleaned: int
    space_freed_mb: float
    errors: list[str]


def scan_temp_files() -> list[CleanupTarget]:
    """Scan common temp file locations and report sizes."""
    targets = []
    temp_paths = {
        "Windows Temp": Path(os.environ.get("TEMP", "C:/Windows/Temp")),
        "User Temp": Path.home() / "AppData" / "Local" / "Temp",
        "Prefetch": Path("C:/Windows/Prefetch"),
        "Windows Update Cache": Path("C:/Windows/SoftwareDistribution/Download"),
        "Thumbnail Cache": Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Explorer",
    }

    for desc, path in temp_paths.items():
        if path.exists():
            size, count = _get_dir_size(path)
            if size > 0:
                targets.append(
                    CleanupTarget(
                        path=str(path),
                        size_mb=round(size / (1024**2), 1),
                        file_count=count,
                        description=desc,
                    )
                )

    return targets


def scan_large_files(min_size_mb: int = 500, search_path: str = "C:\\") -> list[dict]:
    """Find large files that might be candidates for cleanup."""
    script = f"""
    Get-ChildItem -Path '{search_path}' -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {{ $_.Length -gt {min_size_mb * 1024 * 1024} }} |
        Sort-Object Length -Descending |
        Select-Object -First 20 FullName, Length,
            @{{N='SizeMB'; E={{[math]::Round($_.Length / 1MB, 1)}}}},
            LastWriteTime |
        ConvertTo-Json -Compress
    """
    result = _run_powershell(script, timeout=120)
    if not result:
        return []

    import json

    data = json.loads(result)
    if isinstance(data, dict):
        data = [data]
    return data


def clean_temp_files(target_path: str) -> CleanupResult:
    """Clean temp files from a specific path. Returns cleanup results."""
    errors = []
    freed = 0
    cleaned = 0
    path = Path(target_path)

    if not path.exists():
        return CleanupResult(0, 0, [f"Path not found: {target_path}"])

    for item in path.iterdir():
        try:
            if item.is_file():
                size = item.stat().st_size
                item.unlink()
                freed += size
                cleaned += 1
            elif item.is_dir():
                size = _get_dir_size(item)[0]
                import shutil
                shutil.rmtree(item, ignore_errors=True)
                freed += size
                cleaned += 1
        except (PermissionError, OSError) as e:
            errors.append(f"{item.name}: {e}")

    return CleanupResult(
        targets_cleaned=cleaned,
        space_freed_mb=round(freed / (1024**2), 1),
        errors=errors[:10],  # Cap error list
    )


def flush_dns_cache() -> str:
    """Flush the DNS resolver cache."""
    result = _run_powershell("Clear-DnsClientCache; Write-Output 'DNS cache flushed'")
    return result or "Failed to flush DNS cache"


def get_recycle_bin_size() -> dict:
    """Get the size of the recycle bin."""
    script = """
    $shell = New-Object -ComObject Shell.Application
    $bin = $shell.Namespace(10)
    $size = 0; $count = 0
    $bin.Items() | ForEach-Object { $size += $_.Size; $count++ }
    @{ SizeMB = [math]::Round($size / 1MB, 1); ItemCount = $count } | ConvertTo-Json
    """
    result = _run_powershell(script)
    if not result:
        return {"SizeMB": 0, "ItemCount": 0}

    import json
    return json.loads(result)


def _get_dir_size(path: Path) -> tuple[int, int]:
    """Calculate total size and file count of a directory."""
    total = 0
    count = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                    count += 1
                except OSError:
                    continue
    except (PermissionError, OSError):
        pass
    return total, count


def _run_powershell(script: str, timeout: int = 30) -> str:
    """Execute a PowerShell script and return stdout."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
