"""Tests for process monitoring tools."""

from anubis.tools.processes import get_process_detail, get_top_processes


def test_get_top_processes_cpu():
    procs = get_top_processes(sort_by="cpu", limit=5)
    assert len(procs) > 0
    assert len(procs) <= 5
    for p in procs:
        assert p.pid > 0
        assert p.name


def test_get_top_processes_memory():
    procs = get_top_processes(sort_by="memory", limit=10)
    assert len(procs) > 0
    # Should be sorted by memory descending
    for i in range(len(procs) - 1):
        assert procs[i].memory_mb >= procs[i + 1].memory_mb


def test_get_process_detail():
    import os

    detail = get_process_detail(os.getpid())
    assert detail is not None
    assert detail.pid == os.getpid()
    assert detail.memory_mb > 0
