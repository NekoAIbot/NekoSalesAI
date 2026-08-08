from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.database.database import SessionLocal


def get_db() -> Iterator[Session]:
    """Canonical request-scoped database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
