from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.database.base import Base

# check_same_thread is a SQLite-only connect arg. Passing it unconditionally
# makes the app fail to start on Postgres, so it is applied per-dialect.
connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

__all__ = ["Base", "engine", "SessionLocal"]
