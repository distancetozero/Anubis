"""Database engine and session management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from anubis.core.config import DatabaseConfig
from anubis.db.models import Base


async def init_db(config: DatabaseConfig | None = None) -> async_sessionmaker[AsyncSession]:
    """Initialize the database and return a session factory."""
    if config is None:
        config = DatabaseConfig()

    engine = create_async_engine(config.url, echo=config.echo)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return async_sessionmaker(engine, expire_on_commit=False)
