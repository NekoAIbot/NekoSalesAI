"""Does the migrated database match the models?

Every other test file builds its schema with ``Base.metadata.create_all``, which
reads the models directly. Production does not: it runs the Alembic chain. So
the two can disagree indefinitely and the suite will stay green — the tests are
looking at the models, and the models were never wrong.

That is exactly how the ``follow_ups`` timestamp bug survived. ``BaseModel``
declares ``created_at`` with ``server_default=func.now()`` and no code ever
sends a value, but migration ``c4e81f27a9b3`` created the column ``NOT NULL``
with no default. Under ``create_all`` the default was always there. Under
migrations it never was, so the first workspace to reach the follow-up step got

    sqlite3.IntegrityError: NOT NULL constraint failed: follow_ups.created_at

which poisoned the session, raised out of provisioning, returned 500 from the
checkout status endpoint, and left a buyer who had paid ₦148,000 watching
"setting up your workspace now" forever.

These tests run the real migration chain into a throwaway file and then ask the
result whether it can do what the application assumes. They are deliberately
generic: the point is not to guard one column, it is to make the next drift of
this kind fail here instead of in front of a paying customer.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.database.base import Base

# Importing the model package registers every table on Base.metadata. Without
# it the comparison below is vacuous: an empty metadata matches anything.
import app.models  # noqa: F401


BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def migrated(tmp_path_factory):
    """A database built the way production builds one: ``alembic upgrade head``."""
    path = tmp_path_factory.mktemp("migrated") / "migrated.db"
    url = f"sqlite:///{path}"

    original = settings.DATABASE_URL
    settings.DATABASE_URL = url  # env.py reads this to point the migration
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")
    finally:
        settings.DATABASE_URL = original

    engine = create_engine(url)
    yield engine
    engine.dispose()


# ---------- the live failure, stated directly ----------


def test_a_follow_up_can_be_written_without_naming_its_timestamps(migrated):
    """The bug, reproduced at the level it actually broke.

    Nothing in the application sends ``created_at``; it is the database's job.
    A column that is ``NOT NULL`` with no default makes that an error instead of
    a convention, and the error surfaces three layers away from the cause.
    """
    from datetime import datetime

    from app.models.follow_up import STATUS_SCHEDULED, FollowUp

    session = sessionmaker(bind=migrated)()
    try:
        session.add(
            FollowUp(
                organization_id=1,
                workspace_profile_id=1,
                rule_code="day_0_workspace_live",
                day_offset=0,
                due_at=datetime(2026, 8, 25, 5, 47, 50),
                status=STATUS_SCHEDULED,
                subject="Your workspace is live",
                body="Everything you paid for is switched on.",
            )
        )
        session.commit()

        written = session.query(FollowUp).one()

        assert written.created_at is not None
        assert written.updated_at is not None
    finally:
        session.close()


# ---------- the general guard ----------


def _model_columns(table_name: str) -> dict:
    table = Base.metadata.tables[table_name]
    return {column.name: column for column in table.columns}


def test_every_model_table_exists_in_the_migrated_database(migrated):
    migrated_tables = set(inspect(migrated).get_table_names())
    model_tables = set(Base.metadata.tables)

    assert model_tables - migrated_tables == set()


def test_no_model_column_is_missing_from_the_migrated_database(migrated):
    """A model column with no migration behind it fails only in production."""
    inspector = inspect(migrated)
    missing = {}

    for table_name in sorted(Base.metadata.tables):
        migrated_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        gap = set(_model_columns(table_name)) - migrated_columns

        if gap:
            missing[table_name] = sorted(gap)

    assert missing == {}


def test_a_column_the_application_never_sends_has_a_default_to_fall_back_on(
    migrated,
):
    """The drift class this suite was blind to, closed generically.

    A column that is ``NOT NULL`` and whose model gives it a ``server_default``
    is one the application deliberately does not populate. If the migrated
    table has no default, every insert into it fails — and no model-built test
    can see that, because ``create_all`` copies the default across.
    """
    inspector = inspect(migrated)
    undefaulted = {}

    for table_name in sorted(Base.metadata.tables):
        actual = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }

        for name, column in _model_columns(table_name).items():
            expects_database_to_fill_it = (
                column.server_default is not None and not column.nullable
            )
            if not expects_database_to_fill_it:
                continue

            live = actual.get(name)
            if live is not None and live.get("default") is None:
                undefaulted.setdefault(table_name, []).append(name)

    assert undefaulted == {}


# ---------- running a migration must not reach outside itself ----------


def test_running_a_migration_leaves_existing_log_handlers_alone(tmp_path):
    """A migration configures the database, not the process it was called from.

    ``env.py`` used to call ``fileConfig`` unconditionally, and ``fileConfig``
    removes every handler on the root logger before installing alembic.ini's.
    Run from a terminal that is exactly right. Run in-process it is theft: this
    suite lost pytest's log capture to it — two seed tests failed on an empty
    ``caplog.text`` and pointed at seeding, which was innocent — and the poller,
    which calls ``configure_logging()`` at startup and then has migrations run
    against the same process, would have gone silent the same way with nothing
    in the log to say so.
    """
    import logging

    listener = logging.NullHandler()
    listener.set_name("a-handler-alembic-did-not-install")
    root = logging.getLogger()
    root.addHandler(listener)

    original = settings.DATABASE_URL
    settings.DATABASE_URL = f"sqlite:///{tmp_path / 'handlers.db'}"
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")

        assert listener in logging.getLogger().handlers
    finally:
        settings.DATABASE_URL = original
        root.removeHandler(listener)
