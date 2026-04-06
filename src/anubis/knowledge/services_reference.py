"""Windows services reference knowledge base.

Describes what common Windows services do, whether they're safe to disable,
and their impact. Used by the Service Manager agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DisableSafety(str, Enum):
    NEVER = "never"  # Critical — system will break
    CAUTION = "caution"  # Might cause issues for some users
    SAFE = "safe"  # Generally safe to disable
    RECOMMENDED = "recommended"  # Recommended to disable (bloatware)


@dataclass
class ServiceReference:
    name: str  # Service name (short name)
    display_name: str
    description: str
    category: str  # networking, security, media, gaming, telemetry, etc.
    disable_safety: DisableSafety
    disable_impact: str  # What happens if disabled
    notes: str = ""


SERVICE_DATABASE: dict[str, ServiceReference] = {
    # === NEVER DISABLE ===
    "rpcss": ServiceReference(
        name="rpcss", display_name="Remote Procedure Call (RPC)",
        description="The RPC endpoint mapper and COM service. Almost every Windows component depends on it.",
        category="core", disable_safety=DisableSafety.NEVER,
        disable_impact="System will not boot properly",
    ),
    "dcomlaunch": ServiceReference(
        name="dcomlaunch", display_name="DCOM Server Process Launcher",
        description="Launches COM and DCOM servers. Critical system infrastructure.",
        category="core", disable_safety=DisableSafety.NEVER,
        disable_impact="Many applications and system functions will fail",
    ),
    "eventlog": ServiceReference(
        name="eventlog", display_name="Windows Event Log",
        description="Manages events and event logs. Required for diagnostics.",
        category="core", disable_safety=DisableSafety.NEVER,
        disable_impact="No event logging — impossible to diagnose issues",
    ),
    "windefend": ServiceReference(
        name="windefend", display_name="Windows Defender Antivirus Service",
        description="Real-time antimalware protection built into Windows.",
        category="security", disable_safety=DisableSafety.NEVER,
        disable_impact="System exposed to malware without alternative antivirus",
        notes="Only disable if using a third-party antivirus",
    ),
    "mpssvc": ServiceReference(
        name="mpssvc", display_name="Windows Defender Firewall",
        description="Network firewall that blocks unauthorized inbound connections.",
        category="security", disable_safety=DisableSafety.NEVER,
        disable_impact="System exposed to network attacks",
    ),
    "wuauserv": ServiceReference(
        name="wuauserv", display_name="Windows Update",
        description="Enables detection, download, and installation of updates.",
        category="core", disable_safety=DisableSafety.NEVER,
        disable_impact="No security patches — system becomes vulnerable over time",
    ),

    # === CAUTION ===
    "wsearch": ServiceReference(
        name="wsearch", display_name="Windows Search",
        description="Provides content indexing for fast file search.",
        category="utility", disable_safety=DisableSafety.CAUTION,
        disable_impact="File search in Start Menu and Explorer will be very slow",
        notes="Disabling can help HDD performance but hurts SSD users. Safe to disable on HDDs.",
    ),
    "sysmain": ServiceReference(
        name="sysmain", display_name="SysMain (Superfetch)",
        description="Preloads frequently-used apps into memory for faster launch.",
        category="performance", disable_safety=DisableSafety.CAUTION,
        disable_impact="Apps may take slightly longer to open initially",
        notes="Disabling helps on HDDs with high disk usage. Keep enabled on SSDs.",
    ),
    "spooler": ServiceReference(
        name="spooler", display_name="Print Spooler",
        description="Manages print jobs sent to printers.",
        category="utility", disable_safety=DisableSafety.CAUTION,
        disable_impact="Cannot print to any printer",
        notes="Safe to disable if you don't use a printer. Historical security vulnerability target.",
    ),
    "wmpnetworksvc": ServiceReference(
        name="wmpnetworksvc", display_name="Windows Media Player Network Sharing",
        description="Shares Windows Media Player libraries to other networked devices.",
        category="media", disable_safety=DisableSafety.SAFE,
        disable_impact="Cannot share media library over network",
    ),

    # === SAFE TO DISABLE ===
    "fax": ServiceReference(
        name="fax", display_name="Fax",
        description="Enables sending and receiving faxes.",
        category="utility", disable_safety=DisableSafety.SAFE,
        disable_impact="Cannot send/receive faxes (almost nobody uses this)",
    ),
    "retaildemo": ServiceReference(
        name="retaildemo", display_name="Retail Demo Service",
        description="Controls the retail demo experience in stores.",
        category="bloatware", disable_safety=DisableSafety.SAFE,
        disable_impact="None for home/business users",
    ),
    "mapsbrokersvc": ServiceReference(
        name="mapsbrokersvc", display_name="Downloaded Maps Manager",
        description="Manages downloaded offline maps.",
        category="utility", disable_safety=DisableSafety.SAFE,
        disable_impact="Cannot use offline maps in Windows Maps app",
    ),

    # === RECOMMENDED TO DISABLE (BLOATWARE / TELEMETRY) ===
    "diagtrack": ServiceReference(
        name="diagtrack", display_name="Connected User Experiences and Telemetry",
        description="Collects and sends diagnostic/usage data to Microsoft.",
        category="telemetry", disable_safety=DisableSafety.RECOMMENDED,
        disable_impact="Stops sending telemetry data to Microsoft",
        notes="Privacy improvement. No impact on system functionality.",
    ),
    "dmwappushservice": ServiceReference(
        name="dmwappushservice", display_name="WAP Push Message Routing Service",
        description="Routes WAP push messages for device management telemetry.",
        category="telemetry", disable_safety=DisableSafety.RECOMMENDED,
        disable_impact="Stops telemetry push routing",
    ),
    "xblauthmgr": ServiceReference(
        name="xblauthmgr", display_name="Xbox Live Auth Manager",
        description="Provides authentication and authorization for Xbox Live.",
        category="gaming", disable_safety=DisableSafety.RECOMMENDED,
        disable_impact="Cannot sign into Xbox Live or use Xbox features",
        notes="Safe to disable if you don't use Xbox/Game Pass on this PC.",
    ),
    "xblgamesave": ServiceReference(
        name="xblgamesave", display_name="Xbox Live Game Save",
        description="Syncs save data for Xbox Live enabled games.",
        category="gaming", disable_safety=DisableSafety.RECOMMENDED,
        disable_impact="Game saves won't sync to cloud via Xbox",
        notes="Safe to disable if you don't use Xbox gaming.",
    ),
    "xboxgipsvc": ServiceReference(
        name="xboxgipsvc", display_name="Xbox Accessory Management Service",
        description="Manages connected Xbox accessories.",
        category="gaming", disable_safety=DisableSafety.RECOMMENDED,
        disable_impact="Xbox controllers may not be managed optimally",
        notes="Safe unless you use Xbox controllers.",
    ),
    "xboxnetapisvc": ServiceReference(
        name="xboxnetapisvc", display_name="Xbox Live Networking Service",
        description="Manages Xbox Live networking features.",
        category="gaming", disable_safety=DisableSafety.RECOMMENDED,
        disable_impact="Xbox Live multiplayer networking won't work",
    ),
}


def lookup_service(name: str) -> ServiceReference | None:
    """Look up a service by its short name."""
    return SERVICE_DATABASE.get(name.lower())


def get_safe_to_disable() -> list[ServiceReference]:
    """Get services that are safe or recommended to disable."""
    return [
        svc for svc in SERVICE_DATABASE.values()
        if svc.disable_safety in (DisableSafety.SAFE, DisableSafety.RECOMMENDED)
    ]


def get_bloatware_services() -> list[ServiceReference]:
    """Get services classified as bloatware/telemetry."""
    return [
        svc for svc in SERVICE_DATABASE.values()
        if svc.disable_safety == DisableSafety.RECOMMENDED
    ]
