"""Application logging.

Replaces the ad-hoc print() calls that previously served as the logging
system. Configured once at startup from app.main.
"""

import logging
import sys

from app.config.settings import settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"


def configure_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # SQLAlchemy echoes every statement at INFO; keep it at WARNING so app
    # logs stay readable during development.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # httpx and httpcore log the full request line at DEBUG/INFO, and a Telegram
    # Bot API URL contains the bot token — https://api.telegram.org/bot<TOKEN>/…
    # With DEBUG=true that puts a live credential into stdout, into any file the
    # output is redirected to, and into terminal scrollback. The token is a bearer
    # credential for the bot's whole account, so it is not something to leak in
    # exchange for transport logging nobody reads.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
