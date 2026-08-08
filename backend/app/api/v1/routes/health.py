from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.session import get_db

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("/")
def health(db: Session = Depends(get_db)):
    """Liveness plus real database connectivity.

    The previous implementation returned a hardcoded "database": "pending"
    string regardless of actual state, so it reported healthy while every
    query was failing against a missing schema.
    """
    try:
        db.execute(text("SELECT 1"))
        database = "connected"
        status = "healthy"
    except Exception:
        database = "unavailable"
        status = "degraded"

    return {
        "status": status,
        "database": database,
        "api": "running",
        "version": settings.APP_VERSION,
    }
