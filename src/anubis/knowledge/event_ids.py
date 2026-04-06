"""Windows Event ID knowledge base.

Maps common Windows event log entries to human-readable explanations
and recommended actions. Used by the Fault Diagnostician agent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EventIDEntry:
    event_id: int
    source: str  # Provider name
    log: str  # System, Application, Security
    level: str  # Error, Warning, Critical
    title: str
    description: str
    common_causes: list[str]
    recommended_actions: list[str]


EVENT_ID_DATABASE: dict[tuple[int, str], EventIDEntry] = {
    # === System Log — Critical / Error Events ===
    (41, "Microsoft-Windows-Kernel-Power"): EventIDEntry(
        event_id=41,
        source="Microsoft-Windows-Kernel-Power",
        log="System",
        level="Critical",
        title="Unexpected Shutdown (Kernel-Power 41)",
        description="The system rebooted without cleanly shutting down first. "
        "This is the classic 'unexpected power loss' or 'crash reboot' event.",
        common_causes=[
            "Power supply failure or instability",
            "BSOD crash (check for preceding bugcheck events)",
            "Overheating causing emergency shutdown",
            "Power outage or loose power cable",
            "Unstable overclocking",
            "Driver crash that forced reboot",
        ],
        recommended_actions=[
            "Check for BSOD events (Event ID 1001) near the same timestamp",
            "Monitor CPU/GPU temperatures for overheating",
            "Test power supply unit (PSU) with a multimeter or swap test",
            "Remove any overclocking and test stability",
            "Check UPS/surge protector if applicable",
        ],
    ),
    (1001, "Windows Error Reporting"): EventIDEntry(
        event_id=1001,
        source="Windows Error Reporting",
        log="Application",
        level="Error",
        title="Windows Error Report",
        description="Application crash or fault report submitted to Windows Error Reporting.",
        common_causes=[
            "Application bug or crash",
            "Memory corruption",
            "DLL dependency issues",
            "Insufficient resources",
        ],
        recommended_actions=[
            "Check the faulting module name in the event details",
            "Update the crashing application",
            "Run 'sfc /scannow' if it's a system component",
            "Check for available application patches",
        ],
    ),
    (6008, "EventLog"): EventIDEntry(
        event_id=6008,
        source="EventLog",
        log="System",
        level="Error",
        title="Unexpected Shutdown",
        description="The previous system shutdown was unexpected.",
        common_causes=[
            "Power failure",
            "BSOD crash",
            "Hardware failure",
            "Forced shutdown (holding power button)",
        ],
        recommended_actions=[
            "Correlate with Event 41 (Kernel-Power) for details",
            "Check hardware temperatures and PSU health",
            "Review BSOD dump files if available",
        ],
    ),
    (7, "Microsoft-Windows-Kernel-Processor-Power"): EventIDEntry(
        event_id=7,
        source="Microsoft-Windows-Kernel-Processor-Power",
        log="System",
        level="Warning",
        title="Processor Speed Throttling",
        description="Processor speed is being limited by system firmware (thermal throttling).",
        common_causes=[
            "CPU overheating",
            "Insufficient cooling",
            "Dust buildup in heatsink/fans",
            "Failed thermal paste",
            "Power plan limiting CPU speed",
        ],
        recommended_actions=[
            "Check CPU temperatures immediately",
            "Clean dust from CPU heatsink and fans",
            "Reapply thermal paste if temps are high with clean cooler",
            "Check power plan isn't set to 'Power Saver'",
            "Ensure laptop vents aren't blocked",
        ],
    ),
    (7031, "Service Control Manager"): EventIDEntry(
        event_id=7031,
        source="Service Control Manager",
        log="System",
        level="Error",
        title="Service Crash and Recovery",
        description="A service terminated unexpectedly and a recovery action was taken.",
        common_causes=[
            "Service binary crash",
            "Dependency failure",
            "Corrupt service installation",
            "Resource exhaustion (memory/handles)",
        ],
        recommended_actions=[
            "Note which service crashed (in event details)",
            "Check if the service is still running",
            "Reinstall or update the associated application",
            "Check for memory leaks in the service process",
        ],
    ),
    (7034, "Service Control Manager"): EventIDEntry(
        event_id=7034,
        source="Service Control Manager",
        log="System",
        level="Error",
        title="Service Terminated Unexpectedly",
        description="A service terminated unexpectedly (multiple times).",
        common_causes=[
            "Recurring service crash",
            "Incompatible update",
            "Corrupt service executable",
            "Hardware-related failure",
        ],
        recommended_actions=[
            "Identify the failing service",
            "Check dependency services",
            "Repair or reinstall the application",
            "Check System File Checker: 'sfc /scannow'",
        ],
    ),
    (10016, "DistributedCOM"): EventIDEntry(
        event_id=10016,
        source="DistributedCOM",
        log="System",
        level="Error",
        title="DCOM Permission Error",
        description="DCOM component doesn't have required activation permissions.",
        common_causes=[
            "Windows permission misconfiguration (very common, usually harmless)",
            "Windows Update changing DCOM settings",
            "Third-party application installation",
        ],
        recommended_actions=[
            "This is usually SAFE TO IGNORE — it's one of the most common Windows errors",
            "Does not affect system performance or stability in most cases",
            "Fix via Component Services (dcomcnfg) if needed for a specific app",
        ],
    ),
    (1000, "Application Error"): EventIDEntry(
        event_id=1000,
        source="Application Error",
        log="Application",
        level="Error",
        title="Application Crash",
        description="An application has crashed with an unhandled exception.",
        common_causes=[
            "Software bug",
            "Corrupt installation",
            "Incompatible DLL versions",
            "Memory corruption",
            "Insufficient system resources",
        ],
        recommended_actions=[
            "Note the faulting application name and module",
            "Update the application to latest version",
            "Reinstall if updates don't help",
            "Check for corrupt system files with 'sfc /scannow'",
            "Run the application in compatibility mode if it's older software",
        ],
    ),
    (55, "Ntfs"): EventIDEntry(
        event_id=55,
        source="Ntfs",
        log="System",
        level="Error",
        title="NTFS File System Corruption Detected",
        description="The file system structure on disk is corrupt and unusable.",
        common_causes=[
            "Disk hardware failure",
            "Unexpected power loss during write",
            "Bad sectors on the drive",
            "Failing SATA/NVMe cable or connector",
        ],
        recommended_actions=[
            "Run 'chkdsk /f /r' on the affected volume IMMEDIATELY",
            "Check SMART data for disk health",
            "BACK UP YOUR DATA as soon as possible",
            "Consider replacing the drive if SMART shows warnings",
        ],
    ),
    (11, "Disk"): EventIDEntry(
        event_id=11,
        source="Disk",
        log="System",
        level="Error",
        title="Disk I/O Error",
        description="The driver detected a controller error on a device.",
        common_causes=[
            "Failing hard drive or SSD",
            "Loose or damaged SATA/USB cable",
            "Bad sectors on the disk",
            "Driver issues",
            "External drive disconnection during I/O",
        ],
        recommended_actions=[
            "Check SMART data for the affected disk",
            "Reseat SATA cables or try a different port",
            "Run 'chkdsk /f /r'",
            "If external drive: try a different USB cable/port",
            "Back up data and consider drive replacement if recurring",
        ],
    ),
    (153, "Disk"): EventIDEntry(
        event_id=153,
        source="Disk",
        log="System",
        level="Warning",
        title="Disk I/O Retry",
        description="The IO operation was retried at the disk level.",
        common_causes=[
            "Disk performance degradation",
            "Failing storage device",
            "Power management causing disk sleep issues",
            "Storage controller driver bug",
        ],
        recommended_actions=[
            "Check SMART data immediately",
            "Update storage controller drivers",
            "Disable disk power management in Device Manager",
            "If SSD: check for firmware updates",
        ],
    ),
}


def lookup_event(event_id: int, source: str = "") -> EventIDEntry | None:
    """Look up an event ID, optionally with source for exact match."""
    # Try exact match first
    if source:
        key = (event_id, source)
        if key in EVENT_ID_DATABASE:
            return EVENT_ID_DATABASE[key]

    # Try matching by event_id only
    for (eid, src), entry in EVENT_ID_DATABASE.items():
        if eid == event_id:
            return entry

    return None


def get_all_known_events() -> list[EventIDEntry]:
    """Get all known event entries."""
    return list(EVENT_ID_DATABASE.values())
