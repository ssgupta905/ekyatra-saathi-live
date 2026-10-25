"""Alembic environment. The URL arrives through the config, never from here."""

from __future__ import annotations

from alembic import context
from saathi.db.tables import Base
from sqlalchemy import create_engine, pool

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot alter a column in place; batch mode rebuilds the
            # table instead. A no-op on Postgres.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
