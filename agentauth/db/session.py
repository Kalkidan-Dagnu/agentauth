"""
Async database session and engine setup.

Uses SQLAlchemy's asyncio extension with asyncpg for PostgreSQL in
production and aiosqlite for tests.

Usage:
    # In FastAPI lifespan:
    await init_db(database_url)

    # In route handlers (via Depends):
    async def my_route(db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentauth.db.models import Base

logger = structlog.get_logger(__name__)

# Module-level singletons, initialised by init_db()
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    """
    Create the async engine and (optionally) create all tables.

    Call this once at application startup before accepting requests.

    Args:
        database_url: SQLAlchemy async connection URL, e.g.:
            - "postgresql+asyncpg://user:pass@localhost/agentauth"
            - "sqlite+aiosqlite:///./agentauth.db"   (dev / tests)
    """
    global _engine, _session_factory

    # connect_args only needed for SQLite (disable same-thread check)
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_async_engine(
        database_url,
        echo=False,          # set True to log all SQL (noisy but useful for debugging)
        pool_pre_ping=True,  # verify connections before use
        connect_args=connect_args,
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,  # keep ORM objects usable after commit
    )

    # Create all tables that don't exist yet.
    # In production you would use Alembic migrations instead, but this
    # is a safe fallback for dev/test environments.
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialised", url=_redact_url(database_url))


async def close_db() -> None:
    """Dispose the engine. Call this on application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Each request gets its own session that is automatically committed
    on success and rolled back on exception.

    Usage:
        @app.post("/agents")
        async def create_agent(db: AsyncSession = Depends(get_db)):
            ...
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database not initialised. Call init_db() before using get_db()."
        )

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory (useful for creating sessions outside DI)."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _session_factory


def _redact_url(url: str) -> str:
    """Remove password from a database URL for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url
