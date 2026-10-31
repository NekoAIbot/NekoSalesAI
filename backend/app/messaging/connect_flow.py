"""The /connect handshake on the owner bot, for owners with no web session.

State lives in telegram_connect_codes: the chat asks to connect, the bot asks
for the account email, a code goes out by mail, and the reply verifies. A
matching reply issues a temporary web password (forced to be replaced on the
first sign-in) and tells the owner where to use it. Codes and emails are
matched by hash; nothing sensitive is logged.
"""

import re

from sqlalchemy import delete, select

from app.auth.security import hash_password
from app.config.settings import settings
from app.mail.transport import Message, send_in_background
from app.models.telegram_connect_code import (
    CONNECT_CODE_TTL_MINUTES,
    CONNECT_MAX_ATTEMPTS,
    TelegramConnectCode,
)
from app.repositories.user_repository import UserRepository

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PENDING_CONNECT = "__pending_connect__"

_WELCOME = (
    "let's connect your Nera account. reply with the email you signed up "
    "with on the website and i'll send you a verification code."
)
_CODE_SENT = (
    "if that email has a Nera account, a code is on its way. reply with the "
    f"6-digit code ({CONNECT_CODE_TTL_MINUTES} minutes)."
)
_CODE_WRONG = (
    "that code didn't match. check the email and try again "
    f"({CONNECT_MAX_ATTEMPTS} attempts)."
)
_CONNECT_DONE = (
    "connected. here is your temporary web password — sign in at "
    "{base_url}/login with your email and this password:\n\n"
    "  {temp}\n\n"
    "the website will make you set a new password immediately. this message "
    "is the only place it appears."
)
_UNKNOWN_EMAIL = (
    "i couldn't find a Nera account with that email. check the spelling and "
    "send it again, or sign up at {base_url}/signup first."
)


def handle_connect_step(db, external_id: str, text: str, service, message) -> str | None:
    """Advance the /connect handshake for this chat.

    Returns the reply text when the message was part of the handshake, or
    None when the chat has no pending connect and this text is not an email
    (the caller falls through to normal handling).
    """
    text = text.strip()

    if text.lower() == "/connect" or text.lower() == "connect":
        _clear(db, external_id)
        return _WELCOME

    pending = db.execute(
        select(TelegramConnectCode).where(TelegramConnectCode.chat_id == external_id)
    ).scalars().first()

    if pending is None:
        # An email typed cold, with no pending handshake, starts one only if
        # it looks like an email — plain chatter falls through.
        if EMAIL_RE.match(text):
            return _start_with_email(db, external_id, text)
        return None

    if pending.expired():
        _clear(db, external_id)
        return "that code expired. send /connect again and i'll start over."

    if pending.attempts + 1 >= CONNECT_MAX_ATTEMPTS and not pending.matches(text):
        _clear(db, external_id)
        return "too many wrong codes. send /connect to start over."

    if not pending.matches(text):
        pending.attempts += 1
        db.commit()
        return _CODE_WRONG

    # Verified. Issue the temp password.
    service_repo = UserRepository(db)
    temp = None
    from app.auth.service import AuthService

    auth = AuthService(service_repo, db)
    temp = auth.issue_temp_password(pending.email)

    if temp is None:
        _clear(db, external_id)
        return (
            "that code checked out but the account is gone. sign up at "
            f"{settings.PUBLIC_BASE_URL}/signup and run /connect again."
        )

    reply = _CONNECT_DONE.format(base_url=settings.PUBLIC_BASE_URL, temp=temp)
    _clear(db, external_id)
    return reply


def _start_with_email(db, external_id: str, email: str) -> str:
    from app.auth.service import _generate_numeric_code

    code = _generate_numeric_code()
    known = UserRepository(db).get_by_email(email) is not None
    if known:
        _clear(db, external_id)
        db.add(TelegramConnectCode.fresh(external_id, email, code))
        db.commit()
        _mail_code(email, code)
    # Neutral either way: the reply never reveals whether the email has an
    # account, and an unknown email simply has no pending row to verify.
    return _CODE_SENT.format(email=email)


def _mail_code(email: str, code: str) -> None:
    body = (
        f"Your NekoSalesAI connect code is:\n\n  {code}\n\n"
        f"It expires in {CONNECT_CODE_TTL_MINUTES} minutes. "
        "Never share this code — reply to Zuri on Telegram with it to link "
        "your account.\n\n"
        f"— {settings.MAIL_FROM_NAME}\n{settings.MAIL_FROM}\n"
    )
    send_in_background(Message(to=email, subject=f"Your connect code: {code}", body=body))


def _clear(db, external_id: str) -> None:
    db.execute(delete(TelegramConnectCode).where(TelegramConnectCode.chat_id == external_id))
