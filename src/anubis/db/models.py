"""SQLAlchemy models for telemetry storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TelemetrySnapshot(Base):
    """Periodic system health snapshots."""

    __tablename__ = "telemetry_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    cpu_percent: Mapped[float] = mapped_column(Float)
    memory_percent: Mapped[float] = mapped_column(Float)
    disk_usage_percent: Mapped[float] = mapped_column(Float)
    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text)  # Full snapshot as JSON


class AgentInteraction(Base):
    """Log of agent queries and responses."""

    __tablename__ = "agent_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user_query: Mapped[str] = mapped_column(Text)
    agents_invoked: Mapped[str] = mapped_column(String(500))  # Comma-separated agent names
    response: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float)


class AlertEvent(Base):
    """System alerts triggered by monitoring."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    severity: Mapped[str] = mapped_column(String(20))  # info, warning, critical
    category: Mapped[str] = mapped_column(String(50))  # cpu, memory, disk, driver, service
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)
