"""Password hashing — the single implementation for the whole app.

Uses bcrypt directly rather than passlib. passlib 1.7.4 (last released 2020)
reads ``bcrypt.__about__.__version__``, which bcrypt 4.x removed, so every
hash call emitted an AttributeError traceback and fell back to a degraded
backend. bcrypt's own API is small enough that the wrapper bought nothing.

bcrypt truncates silently at 72 bytes, so longer passwords are rejected
explicitly instead of having their tail ignored.
"""

import bcrypt

MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds bcrypt's 72-byte input limit."""


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")

    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password exceeds {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded."
        )

    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True when the password matches. Never raises on bad input."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:MAX_PASSWORD_BYTES],
            hashed.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Malformed or empty stored hash — treat as a failed match, not a 500.
        return False
