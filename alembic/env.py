"""
Alembic environment configuration.

Configured for async SQLAlchemy (asyncpg / aiosqlite) and reads the
DATABASE_URL from the environment so the same migration can be run
against any environment without editing files.

Run migrations:
    # upgrade to latest
    alembic upgrade head

    # generate a new migration (autogenerate from model changes)
    alembic revision --autogenerate -m "describe your change"

    # downgrade one step
    alembic downgrade -1
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load .env so DATABASE_URL is available when running migrations locally
load_dotenv()

# --- Alembic Config object (access to alembic.ini values) ---
config = context.config

# Override sqlalchemy.url from environment variable
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Set up loggers from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Import our ORM models so Alembic can diff against them ---
from agentauth.db.models import Base  # noqa: E402

target_metadata = Base.metadata


# ── Offline migrations (generate SQL without a live connection) ────────────────


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Emits SQL to stdout/file without opening a database connection.
    Useful for reviewing or applying migrations in restricted environments.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (run against a live database connection) ─────────────────


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # no connection pooling during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
