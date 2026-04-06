"""Tests for system health monitoring tools."""

from anubis.tools.system_health import (
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_network_info,
    get_system_snapshot,
)


def test_get_cpu_info():
    cpu = get_cpu_info()
    assert 0 <= cpu.usage_percent <= 100
    assert cpu.core_count_physical > 0
    assert cpu.core_count_logical >= cpu.core_count_physical


def test_get_memory_info():
    mem = get_memory_info()
    assert mem.total_gb > 0
    assert 0 <= mem.usage_percent <= 100
    assert mem.used_gb <= mem.total_gb


def test_get_disk_info():
    disks = get_disk_info()
    assert len(disks) > 0
    for disk in disks:
        assert disk.total_gb > 0
        assert 0 <= disk.usage_percent <= 100


def test_get_network_info():
    net = get_network_info()
    assert net.bytes_sent >= 0
    assert net.bytes_recv >= 0


def test_get_system_snapshot():
    snapshot = get_system_snapshot()
    assert snapshot.hostname
    assert snapshot.os_version
    assert snapshot.cpu.core_count_physical > 0
    assert snapshot.memory.total_gb > 0
    assert len(snapshot.disks) > 0
    assert snapshot.uptime_hours >= 0
