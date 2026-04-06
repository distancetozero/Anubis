"""System health monitoring: CPU, memory, disk, network, temperatures."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime

import psutil


@dataclass
class CpuInfo:
    usage_percent: float
    usage_per_core: list[float]
    frequency_mhz: float
    core_count_physical: int
    core_count_logical: int


@dataclass
class MemoryInfo:
    total_gb: float
    available_gb: float
    used_gb: float
    usage_percent: float
    swap_total_gb: float
    swap_used_gb: float
    swap_percent: float


@dataclass
class DiskInfo:
    device: str
    mountpoint: str
    filesystem: str
    total_gb: float
    used_gb: float
    free_gb: float
    usage_percent: float


@dataclass
class NetworkInfo:
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errors_in: int
    errors_out: int


@dataclass
class TemperatureReading:
    label: str
    current_celsius: float
    high_celsius: float | None = None
    critical_celsius: float | None = None


@dataclass
class SystemSnapshot:
    timestamp: str
    hostname: str
    os_version: str
    cpu: CpuInfo
    memory: MemoryInfo
    disks: list[DiskInfo]
    network: NetworkInfo
    temperatures: list[TemperatureReading] = field(default_factory=list)
    boot_time: str = ""
    uptime_hours: float = 0.0


def _bytes_to_gb(b: int) -> float:
    return round(b / (1024**3), 2)


def get_cpu_info() -> CpuInfo:
    """Get current CPU utilization and specs."""
    freq = psutil.cpu_freq()
    return CpuInfo(
        usage_percent=psutil.cpu_percent(interval=1),
        usage_per_core=psutil.cpu_percent(interval=0, percpu=True),
        frequency_mhz=round(freq.current, 0) if freq else 0.0,
        core_count_physical=psutil.cpu_count(logical=False) or 0,
        core_count_logical=psutil.cpu_count(logical=True) or 0,
    )


def get_memory_info() -> MemoryInfo:
    """Get current memory and swap usage."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return MemoryInfo(
        total_gb=_bytes_to_gb(mem.total),
        available_gb=_bytes_to_gb(mem.available),
        used_gb=_bytes_to_gb(mem.used),
        usage_percent=mem.percent,
        swap_total_gb=_bytes_to_gb(swap.total),
        swap_used_gb=_bytes_to_gb(swap.used),
        swap_percent=swap.percent,
    )


def get_disk_info() -> list[DiskInfo]:
    """Get usage info for all mounted partitions."""
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(
                DiskInfo(
                    device=part.device,
                    mountpoint=part.mountpoint,
                    filesystem=part.fstype,
                    total_gb=_bytes_to_gb(usage.total),
                    used_gb=_bytes_to_gb(usage.used),
                    free_gb=_bytes_to_gb(usage.free),
                    usage_percent=usage.percent,
                )
            )
        except PermissionError:
            continue
    return disks


def get_network_info() -> NetworkInfo:
    """Get network I/O counters."""
    net = psutil.net_io_counters()
    return NetworkInfo(
        bytes_sent=net.bytes_sent,
        bytes_recv=net.bytes_recv,
        packets_sent=net.packets_sent,
        packets_recv=net.packets_recv,
        errors_in=net.errin,
        errors_out=net.errout,
    )


def get_temperatures() -> list[TemperatureReading]:
    """Get temperature sensor readings (if available)."""
    temps = []
    try:
        sensor_data = psutil.sensors_temperatures()
        for name, entries in sensor_data.items():
            for entry in entries:
                temps.append(
                    TemperatureReading(
                        label=f"{name}/{entry.label or 'unknown'}",
                        current_celsius=entry.current,
                        high_celsius=entry.high,
                        critical_celsius=entry.critical,
                    )
                )
    except AttributeError:
        # psutil.sensors_temperatures() not available on all platforms
        pass
    return temps


def get_system_snapshot() -> SystemSnapshot:
    """Capture a full system health snapshot."""
    boot = datetime.fromtimestamp(psutil.boot_time())
    uptime = (datetime.now() - boot).total_seconds() / 3600

    return SystemSnapshot(
        timestamp=datetime.now().isoformat(),
        hostname=platform.node(),
        os_version=platform.platform(),
        cpu=get_cpu_info(),
        memory=get_memory_info(),
        disks=get_disk_info(),
        network=get_network_info(),
        temperatures=get_temperatures(),
        boot_time=boot.isoformat(),
        uptime_hours=round(uptime, 1),
    )
