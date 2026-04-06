"""Background system monitoring watchdog.

Periodically collects system telemetry, checks thresholds,
and triggers alerts when anomalies are detected.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import structlog

from anubis.core.config import MonitoringConfig

logger = structlog.get_logger("anubis.watchdog")


@dataclass
class Alert:
    """A system alert triggered by the watchdog."""

    timestamp: str
    severity: str  # info, warning, critical
    category: str  # cpu, memory, disk, temperature, service, driver
    title: str
    message: str
    value: float | None = None
    threshold: float | None = None


AlertCallback = Callable[[Alert], Any]


class Watchdog:
    """Background monitoring watchdog that checks system health periodically."""

    def __init__(self, config: MonitoringConfig | None = None) -> None:
        self.config = config or MonitoringConfig()
        self._running = False
        self._alerts: list[Alert] = []
        self._callbacks: list[AlertCallback] = []
        self._task: asyncio.Task | None = None
        # Track previous values for trend detection
        self._history: list[dict[str, float]] = []
        self._max_history = 288  # ~24 hours at 5-minute intervals

    def on_alert(self, callback: AlertCallback) -> None:
        """Register a callback to be called when an alert fires."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the watchdog background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("watchdog_started", interval_sec=self.config.poll_interval_seconds)

    async def stop(self) -> None:
        """Stop the watchdog."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("watchdog_stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_system_health()
            except Exception as e:
                logger.error("watchdog_error", error=str(e))

            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _check_system_health(self) -> None:
        """Run all health checks and fire alerts if needed."""
        from anubis.tools.system_health import (
            get_cpu_info,
            get_disk_info,
            get_memory_info,
            get_temperatures,
        )

        now = datetime.now().isoformat()

        # CPU check
        cpu = get_cpu_info()
        if cpu.usage_percent >= self.config.cpu_alert_threshold:
            await self._fire_alert(Alert(
                timestamp=now,
                severity="warning" if cpu.usage_percent < 95 else "critical",
                category="cpu",
                title="High CPU Usage",
                message=f"CPU usage is at {cpu.usage_percent}% (threshold: {self.config.cpu_alert_threshold}%)",
                value=cpu.usage_percent,
                threshold=self.config.cpu_alert_threshold,
            ))

        # Memory check
        mem = get_memory_info()
        if mem.usage_percent >= self.config.memory_alert_threshold:
            await self._fire_alert(Alert(
                timestamp=now,
                severity="warning" if mem.usage_percent < 95 else "critical",
                category="memory",
                title="High Memory Usage",
                message=f"Memory usage is at {mem.usage_percent}% "
                f"({mem.used_gb}/{mem.total_gb} GB, threshold: {self.config.memory_alert_threshold}%)",
                value=mem.usage_percent,
                threshold=self.config.memory_alert_threshold,
            ))

        # Disk check
        disks = get_disk_info()
        for disk in disks:
            if disk.usage_percent >= self.config.disk_usage_alert_threshold:
                await self._fire_alert(Alert(
                    timestamp=now,
                    severity="warning" if disk.usage_percent < 95 else "critical",
                    category="disk",
                    title=f"Low Disk Space: {disk.mountpoint}",
                    message=f"Disk {disk.mountpoint} is at {disk.usage_percent}% "
                    f"({disk.free_gb} GB free, threshold: {self.config.disk_usage_alert_threshold}%)",
                    value=disk.usage_percent,
                    threshold=self.config.disk_usage_alert_threshold,
                ))

        # Temperature check
        temps = get_temperatures()
        for temp in temps:
            if temp.current_celsius >= self.config.temp_alert_threshold_celsius:
                await self._fire_alert(Alert(
                    timestamp=now,
                    severity="warning" if temp.current_celsius < 95 else "critical",
                    category="temperature",
                    title=f"High Temperature: {temp.label}",
                    message=f"{temp.label} is at {temp.current_celsius}C "
                    f"(threshold: {self.config.temp_alert_threshold_celsius}C)",
                    value=temp.current_celsius,
                    threshold=self.config.temp_alert_threshold_celsius,
                ))

        # Store history for trend analysis
        self._history.append({
            "timestamp": now,
            "cpu_percent": cpu.usage_percent,
            "memory_percent": mem.usage_percent,
            "disk_max_percent": max((d.usage_percent for d in disks), default=0),
        })
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    async def _fire_alert(self, alert: Alert) -> None:
        """Fire an alert and notify all callbacks."""
        self._alerts.append(alert)
        logger.warning(
            "alert_fired",
            severity=alert.severity,
            category=alert.category,
            title=alert.title,
        )
        for callback in self._callbacks:
            try:
                result = callback(alert)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("alert_callback_error", error=str(e))

    def get_recent_alerts(self, limit: int = 20) -> list[dict]:
        """Get recent alerts."""
        return [
            {
                "timestamp": a.timestamp,
                "severity": a.severity,
                "category": a.category,
                "title": a.title,
                "message": a.message,
            }
            for a in self._alerts[-limit:]
        ]

    def get_trends(self) -> dict[str, Any]:
        """Analyze telemetry trends from history.

        Returns trend data including averages, peaks, and predictions.
        """
        if len(self._history) < 2:
            return {"status": "insufficient_data", "data_points": len(self._history)}

        cpu_values = [h["cpu_percent"] for h in self._history]
        mem_values = [h["memory_percent"] for h in self._history]
        disk_values = [h["disk_max_percent"] for h in self._history]

        def _analyze(values: list[float], name: str) -> dict:
            avg = sum(values) / len(values)
            peak = max(values)
            recent_avg = sum(values[-12:]) / min(len(values), 12)  # Last hour
            older_avg = sum(values[:12]) / min(len(values), 12)  # First hour
            trend = "stable"
            if recent_avg > older_avg * 1.15:
                trend = "increasing"
            elif recent_avg < older_avg * 0.85:
                trend = "decreasing"

            # Simple linear prediction for disk
            prediction = None
            if name == "disk" and trend == "increasing" and recent_avg < 100:
                daily_increase = (recent_avg - older_avg) * (288 / len(values))
                if daily_increase > 0:
                    days_until_full = (100 - recent_avg) / daily_increase
                    prediction = f"At current rate, disk will be full in ~{days_until_full:.0f} days"

            return {
                "average": round(avg, 1),
                "peak": round(peak, 1),
                "recent_avg_1h": round(recent_avg, 1),
                "trend": trend,
                "prediction": prediction,
            }

        return {
            "data_points": len(self._history),
            "time_span_hours": len(self._history) * self.config.poll_interval_seconds / 3600,
            "cpu": _analyze(cpu_values, "cpu"),
            "memory": _analyze(mem_values, "memory"),
            "disk": _analyze(disk_values, "disk"),
        }
