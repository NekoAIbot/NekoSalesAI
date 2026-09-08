import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config.settings import settings
from app.database.base import Base

# Import every model so Alembic can discover them
import app.models

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Only configure logging when this migration owns the process.
#
# fileConfig() does not merge: it removes every handler on the root logger and
# installs the ones in alembic.ini. That is what you want from `alembic upgrade`
# on a terminal, and wrong every other time env.py is imported. Running a
# migration in-process — from a test, or from a startup task that has already
# called configure_logging() — silently unhooked whatever was listening. Two
# tests asserting on seeded log output saw an empty buffer because a migration
# test earlier in the run had removed pytest's capture handler, and the same
# call inside the poller would have taken the poller's stdout handler with it,
# leaving var/nera-poller.log to go quiet with nothing to explain why.
#
# An already-configured root logger is somebody else's decision, so leave it.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
