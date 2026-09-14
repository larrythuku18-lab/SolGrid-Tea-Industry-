import os
import sys

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

# Import models so they register on db.metadata before Alembic reads it.
import solgrid_tea.models  # noqa: E402,F401
from solgrid_tea.extensions import db  # noqa: E402

config = context.config

# Deliberately MIGRATIONS_DATABASE_URL (the owner role), never DATABASE_URL
# (the restricted runtime role) — DDL requires owner privileges the app
# role doesn't have.
db_url = os.environ.get("MIGRATIONS_DATABASE_URL")
if not db_url:
    raise RuntimeError("MIGRATIONS_DATABASE_URL is not set")
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = db.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
