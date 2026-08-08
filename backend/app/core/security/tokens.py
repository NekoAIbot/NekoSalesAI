"""JWT access tokens — the single implementation for the whole app.

Consolidates two prior copies (app/auth/security.py and app/config/security.py)
which disagreed on their signature: one took a subject string, the other an
arbitrary dict, and one hardcoded HS256 while the other read it from settings.
"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.config.settings import settings


def create_access_token(subject: str) -> str:
    """Issue a signed token for a user id."""
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(subject),
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> str | None:
    """Return the subject from a valid token, or None if it is invalid/expired."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None

    return payload.get("sub")
