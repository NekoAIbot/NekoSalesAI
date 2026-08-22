"""Telegram and WhatsApp: sending to them, and receiving from them.

``clients`` sends. ``inbound`` reads what arrives and proves the platform sent
it. ``service`` joins a chat id to a conversation and runs the sales agent over
it. ``poller`` receives on Telegram without needing a public URL; the webhook
routes in ``app.api.v1.routes.messaging`` are the alternative for a deployment
that has one.
"""

from app.messaging.clients import (
    MessagingError,
    MessagingNotConfigured,
    TelegramClient,
    Transport,
    WhatsAppClient,
)
from app.messaging.service import InboundMessagingService, storefront_organization_id

__all__ = [
    "InboundMessagingService",
    "MessagingError",
    "MessagingNotConfigured",
    "TelegramClient",
    "Transport",
    "WhatsAppClient",
    "storefront_organization_id",
]
