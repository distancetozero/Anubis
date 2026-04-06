"""Unified knowledge base lookup for agents.

Provides a single interface for agents to search across all
knowledge bases (BSOD codes, event IDs, services).
"""

from __future__ import annotations

from typing import Any

from anubis.knowledge.bsod_codes import BSOD_DATABASE, lookup_bsod, lookup_bsod_by_name
from anubis.knowledge.event_ids import EVENT_ID_DATABASE, lookup_event
from anubis.knowledge.services_reference import (
    SERVICE_DATABASE,
    get_bloatware_services,
    get_safe_to_disable,
    lookup_service,
)


def search_knowledge_base(query: str) -> list[dict[str, Any]]:
    """Search across all knowledge bases for relevant information.

    Used by agents to enrich their responses with known information.
    """
    results: list[dict[str, Any]] = []
    query_lower = query.lower()

    # Search BSOD codes
    for code, entry in BSOD_DATABASE.items():
        if (
            code.lower() in query_lower
            or entry.name.lower() in query_lower
            or any(cause.lower() in query_lower for cause in entry.common_causes)
        ):
            results.append({
                "type": "bsod",
                "code": entry.code,
                "name": entry.name,
                "description": entry.description,
                "causes": entry.common_causes,
                "fixes": entry.recommended_fixes,
                "severity": entry.severity,
            })

    # Search event IDs
    for (eid, source), entry in EVENT_ID_DATABASE.items():
        if (
            str(eid) in query
            or entry.title.lower() in query_lower
            or source.lower() in query_lower
        ):
            results.append({
                "type": "event_id",
                "event_id": entry.event_id,
                "source": entry.source,
                "title": entry.title,
                "description": entry.description,
                "causes": entry.common_causes,
                "actions": entry.recommended_actions,
            })

    # Search services
    for name, entry in SERVICE_DATABASE.items():
        if (
            name in query_lower
            or entry.display_name.lower() in query_lower
        ):
            results.append({
                "type": "service",
                "name": entry.name,
                "display_name": entry.display_name,
                "description": entry.description,
                "disable_safety": entry.disable_safety.value,
                "disable_impact": entry.disable_impact,
            })

    return results


def get_knowledge_stats() -> dict[str, int]:
    """Get stats about the knowledge base."""
    return {
        "bsod_codes": len(BSOD_DATABASE),
        "event_ids": len(EVENT_ID_DATABASE),
        "service_references": len(SERVICE_DATABASE),
    }
