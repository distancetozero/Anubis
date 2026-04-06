"""BSOD (Blue Screen of Death) stop code knowledge base.

Maps Windows stop codes to human-readable descriptions, common causes,
and recommended fixes. Used by the Fault Diagnostician agent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BSODEntry:
    code: str  # e.g., "0x0000001E"
    name: str
    description: str
    common_causes: list[str]
    recommended_fixes: list[str]
    severity: str  # "low", "medium", "high", "critical"


BSOD_DATABASE: dict[str, BSODEntry] = {
    "0x0000000A": BSODEntry(
        code="0x0000000A",
        name="IRQL_NOT_LESS_OR_EQUAL",
        description="A kernel-mode process or driver attempted to access a memory address "
        "without proper permissions at a raised IRQL.",
        common_causes=[
            "Faulty or incompatible device drivers",
            "Defective hardware (especially RAM)",
            "Incompatible software (antivirus, VPN, virtualization)",
            "Windows Update conflicts",
        ],
        recommended_fixes=[
            "Update all device drivers, especially network and GPU",
            "Run Windows Memory Diagnostic (mdsched.exe)",
            "Uninstall recently installed software or drivers",
            "Run 'sfc /scannow' to check system files",
            "Check for Windows Updates",
        ],
        severity="high",
    ),
    "0x0000001A": BSODEntry(
        code="0x0000001A",
        name="MEMORY_MANAGEMENT",
        description="A severe memory management error occurred, indicating problems with "
        "system memory.",
        common_causes=[
            "Defective RAM modules",
            "Driver memory corruption",
            "Disk errors affecting virtual memory (pagefile)",
            "Overclocked or unstable RAM settings",
        ],
        recommended_fixes=[
            "Run Windows Memory Diagnostic (mdsched.exe)",
            "Test RAM with MemTest86",
            "Reset BIOS/UEFI to default (disable XMP if enabled)",
            "Run 'chkdsk /f /r' on system drive",
            "Update chipset and storage drivers",
        ],
        severity="critical",
    ),
    "0x0000001E": BSODEntry(
        code="0x0000001E",
        name="KMODE_EXCEPTION_NOT_HANDLED",
        description="A kernel-mode program generated an exception that the error handler "
        "did not catch.",
        common_causes=[
            "Outdated or corrupt device drivers",
            "Hardware incompatibility",
            "Corrupt system files",
            "Memory issues",
        ],
        recommended_fixes=[
            "Update or rollback recently changed drivers",
            "Run 'sfc /scannow' and 'DISM /Online /Cleanup-Image /RestoreHealth'",
            "Boot into Safe Mode to isolate the cause",
            "Check Event Viewer for related errors before the crash",
        ],
        severity="high",
    ),
    "0x00000024": BSODEntry(
        code="0x00000024",
        name="NTFS_FILE_SYSTEM",
        description="A problem occurred within the NTFS file system driver.",
        common_causes=[
            "Disk corruption",
            "Bad sectors on the hard drive",
            "Failing storage device",
            "Antivirus filter driver conflicts",
            "Corrupted NTFS volume",
        ],
        recommended_fixes=[
            "Run 'chkdsk /f /r' on the affected drive",
            "Check SMART data for disk health issues",
            "Back up data immediately if disk is failing",
            "Disable antivirus temporarily to test",
            "Update storage controller drivers",
        ],
        severity="critical",
    ),
    "0x0000003B": BSODEntry(
        code="0x0000003B",
        name="SYSTEM_SERVICE_EXCEPTION",
        description="An exception happened while executing a routine that transitions "
        "from non-privileged to privileged code.",
        common_causes=[
            "GPU driver issues (most common)",
            "Antivirus software conflicts",
            "Corrupt system files",
            "Windows Update issues",
        ],
        recommended_fixes=[
            "Update GPU drivers (clean install with DDU)",
            "Update or temporarily disable antivirus",
            "Run 'sfc /scannow'",
            "Install latest Windows Updates",
            "Check Event Viewer for the faulting module name",
        ],
        severity="high",
    ),
    "0x00000050": BSODEntry(
        code="0x00000050",
        name="PAGE_FAULT_IN_NONPAGED_AREA",
        description="A page fault occurred in a non-paged area of memory, meaning the "
        "system tried to access memory that doesn't exist.",
        common_causes=[
            "Faulty RAM",
            "Corrupt NTFS volume",
            "Failing hardware device",
            "Buggy device driver",
            "Antivirus interference",
        ],
        recommended_fixes=[
            "Run Windows Memory Diagnostic",
            "Test with MemTest86",
            "Run 'chkdsk /f /r'",
            "Remove recently installed hardware",
            "Update all drivers",
        ],
        severity="high",
    ),
    "0x0000007E": BSODEntry(
        code="0x0000007E",
        name="SYSTEM_THREAD_EXCEPTION_NOT_HANDLED",
        description="A system thread generated an exception that the error handler "
        "did not catch. Usually caused by a driver.",
        common_causes=[
            "Incompatible or corrupt driver",
            "Insufficient disk space",
            "BIOS incompatibility",
            "Corrupt system files",
        ],
        recommended_fixes=[
            "Note the driver file name from the BSOD screen",
            "Update or uninstall the faulting driver",
            "Ensure at least 15% free space on system drive",
            "Update BIOS/UEFI firmware",
            "Run 'sfc /scannow'",
        ],
        severity="high",
    ),
    "0x0000007F": BSODEntry(
        code="0x0000007F",
        name="UNEXPECTED_KERNEL_MODE_TRAP",
        description="A trap was generated by the CPU that the kernel failed to handle.",
        common_causes=[
            "Hardware failure (RAM, CPU)",
            "Overheating CPU",
            "Overclocking instability",
            "Kernel-mode driver bug",
        ],
        recommended_fixes=[
            "Check CPU temperatures under load",
            "Remove any overclocking (CPU/RAM/GPU)",
            "Test RAM with MemTest86",
            "Ensure adequate cooling and airflow",
            "Update BIOS and chipset drivers",
        ],
        severity="critical",
    ),
    "0x000000BE": BSODEntry(
        code="0x000000BE",
        name="ATTEMPTED_WRITE_TO_READONLY_MEMORY",
        description="A driver attempted to write to read-only memory.",
        common_causes=[
            "Buggy device driver",
            "Windows Update conflicts (e.g., KB5079473 March 2026)",
            "Firmware issues",
            "RAM hardware failure",
        ],
        recommended_fixes=[
            "Uninstall recent Windows Updates",
            "Update all device drivers",
            "Run 'sfc /scannow' and DISM repair",
            "Test RAM with MemTest86",
            "Boot into Safe Mode and test stability",
        ],
        severity="high",
    ),
    "0x000000C2": BSODEntry(
        code="0x000000C2",
        name="BAD_POOL_CALLER",
        description="A kernel-mode process made a bad pool request.",
        common_causes=[
            "Faulty device driver",
            "RAM issues",
            "Antimalware software conflicts",
        ],
        recommended_fixes=[
            "Update all drivers",
            "Remove recently installed software",
            "Run memory diagnostics",
            "Check for driver verifier issues",
        ],
        severity="high",
    ),
    "0x000000D1": BSODEntry(
        code="0x000000D1",
        name="DRIVER_IRQL_NOT_LESS_OR_EQUAL",
        description="A driver accessed paged memory at an elevated IRQL.",
        common_causes=[
            "Network driver issues (most common)",
            "WiFi/Bluetooth driver conflicts",
            "VPN software driver problems",
            "Virtualization driver issues",
        ],
        recommended_fixes=[
            "Update network/WiFi drivers",
            "Uninstall VPN software temporarily",
            "Disable Bluetooth and test",
            "Check the driver name on the BSOD screen",
            "Use Driver Verifier to identify the faulting driver",
        ],
        severity="high",
    ),
    "0x000000EF": BSODEntry(
        code="0x000000EF",
        name="CRITICAL_PROCESS_DIED",
        description="A critical system process terminated unexpectedly.",
        common_causes=[
            "Corrupt system files",
            "Failed Windows Update",
            "Disk errors",
            "Malware infection",
            "Hardware failure",
        ],
        recommended_fixes=[
            "Run 'sfc /scannow' from recovery environment",
            "Run 'DISM /Online /Cleanup-Image /RestoreHealth'",
            "Check disk health with 'chkdsk /f /r'",
            "Run full antimalware scan",
            "Consider Windows repair install (keeps files)",
        ],
        severity="critical",
    ),
    "0x00000133": BSODEntry(
        code="0x00000133",
        name="DPC_WATCHDOG_VIOLATION",
        description="The DPC watchdog detected a prolonged run time at an elevated IRQL.",
        common_causes=[
            "SSD firmware issues (especially with AHCI mode)",
            "Storage controller driver problems",
            "SATA/NVMe driver conflicts",
            "Incompatible hardware",
        ],
        recommended_fixes=[
            "Update SSD firmware",
            "Update storage controller (AHCI/NVMe) drivers",
            "Check BIOS for SATA mode (try switching AHCI/RAID)",
            "Update chipset drivers",
            "Disconnect external storage devices and test",
        ],
        severity="high",
    ),
    "0x00000139": BSODEntry(
        code="0x00000139",
        name="KERNEL_SECURITY_CHECK_FAILURE",
        description="The kernel detected corruption of a critical data structure.",
        common_causes=[
            "Driver buffer overflow",
            "Memory corruption",
            "Outdated drivers",
            "Incompatible software",
        ],
        recommended_fixes=[
            "Update all drivers (especially GPU and network)",
            "Run memory diagnostics",
            "Run 'sfc /scannow'",
            "Uninstall recently added software",
            "Check for Windows Updates",
        ],
        severity="high",
    ),
    "0x00000154": BSODEntry(
        code="0x00000154",
        name="UNEXPECTED_STORE_EXCEPTION",
        description="A store component caught an unexpected exception.",
        common_causes=[
            "Failing hard drive or SSD",
            "Corrupt system files",
            "Antivirus driver conflicts",
            "Outdated storage drivers",
        ],
        recommended_fixes=[
            "Check disk health (SMART data)",
            "Run 'chkdsk /f /r'",
            "Update storage drivers",
            "Disable fast startup in power settings",
            "Temporarily disable antivirus",
        ],
        severity="high",
    ),
    "0xC000021A": BSODEntry(
        code="0xC000021A",
        name="STATUS_SYSTEM_PROCESS_TERMINATED",
        description="The Windows subsystem process (csrss.exe or winlogon.exe) "
        "terminated unexpectedly.",
        common_causes=[
            "Corrupt system files",
            "Failed Windows Update",
            "Mismatched system DLLs",
            "Third-party software interference during logon",
        ],
        recommended_fixes=[
            "Boot into Recovery Environment",
            "Run 'sfc /scannow' from command prompt",
            "Use System Restore to revert to a working state",
            "Run 'DISM /Image:C:\\ /Cleanup-Image /RestoreHealth'",
            "Perform a repair install of Windows",
        ],
        severity="critical",
    ),
}


def lookup_bsod(code: str) -> BSODEntry | None:
    """Look up a BSOD stop code. Accepts various formats."""
    # Normalize: strip spaces, uppercase, ensure 0x prefix
    code = code.strip().upper()
    if not code.startswith("0X"):
        code = "0x" + code
    code = code.replace("0X", "0x")

    # Try direct match
    if code in BSOD_DATABASE:
        return BSOD_DATABASE[code]

    # Try zero-padded match (e.g., "0xA" → "0x0000000A")
    try:
        numeric = int(code, 16)
        padded = f"0x{numeric:08X}"
        return BSOD_DATABASE.get(padded)
    except ValueError:
        return None


def lookup_bsod_by_name(name: str) -> BSODEntry | None:
    """Look up a BSOD by its symbolic name."""
    name_upper = name.upper().strip()
    for entry in BSOD_DATABASE.values():
        if entry.name == name_upper:
            return entry
    return None
