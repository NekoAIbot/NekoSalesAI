"""Email: composing messages and delivering them.

``transport`` delivers. ``messages`` composes. Nothing that triggers an email
needs to know which backend is configured.
"""

from app.mail.messages import credentials, follow_up, receipt
from app.mail.transport import (
    BACKEND_CONSOLE,
    BACKEND_MEMORY,
    BACKEND_SMTP,
    ConsoleMailTransport,
    MailTransport,
    MemoryMailTransport,
    Message,
    SendResult,
    SmtpMailTransport,
    build_transport,
    get_transport,
    send,
    set_transport,
)

__all__ = [
    "BACKEND_CONSOLE",
    "BACKEND_MEMORY",
    "BACKEND_SMTP",
    "ConsoleMailTransport",
    "MailTransport",
    "MemoryMailTransport",
    "Message",
    "SendResult",
    "SmtpMailTransport",
    "build_transport",
    "credentials",
    "follow_up",
    "get_transport",
    "receipt",
    "send",
    "set_transport",
]
