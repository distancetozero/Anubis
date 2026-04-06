"""Tests for the knowledge base."""

from anubis.knowledge.bsod_codes import lookup_bsod, lookup_bsod_by_name
from anubis.knowledge.event_ids import lookup_event
from anubis.knowledge.lookup import get_knowledge_stats, search_knowledge_base
from anubis.knowledge.services_reference import get_bloatware_services, lookup_service


def test_lookup_bsod_by_code():
    entry = lookup_bsod("0x0000000A")
    assert entry is not None
    assert entry.name == "IRQL_NOT_LESS_OR_EQUAL"
    assert entry.severity == "high"


def test_lookup_bsod_short_code():
    entry = lookup_bsod("0xA")
    assert entry is not None
    assert entry.name == "IRQL_NOT_LESS_OR_EQUAL"


def test_lookup_bsod_by_name():
    entry = lookup_bsod_by_name("MEMORY_MANAGEMENT")
    assert entry is not None
    assert entry.code == "0x0000001A"


def test_lookup_bsod_unknown():
    assert lookup_bsod("0xFFFFFFFF") is None


def test_lookup_event_id():
    entry = lookup_event(41, "Microsoft-Windows-Kernel-Power")
    assert entry is not None
    assert "shutdown" in entry.title.lower() or "reboot" in entry.description.lower()


def test_lookup_event_id_only():
    entry = lookup_event(41)
    assert entry is not None


def test_lookup_service():
    svc = lookup_service("rpcss")
    assert svc is not None
    assert svc.disable_safety.value == "never"


def test_bloatware_services():
    bloat = get_bloatware_services()
    assert len(bloat) > 0
    names = [s.name for s in bloat]
    assert "diagtrack" in names


def test_search_knowledge_base():
    results = search_knowledge_base("MEMORY_MANAGEMENT")
    assert len(results) > 0
    assert results[0]["type"] == "bsod"


def test_knowledge_stats():
    stats = get_knowledge_stats()
    assert stats["bsod_codes"] > 10
    assert stats["event_ids"] > 5
    assert stats["service_references"] > 10
