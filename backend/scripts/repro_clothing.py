"""Reproduce the reported clothing-business Telegram conversation at service level.

Runs the exact buyer messages from the production transcript against current code
with an in-memory DB, printing every reply and the scope after each turn.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
import app.models  # noqa: F401  (registers mappers)
from app.models.organization import Organization
from app.models.conversation import Conversation
from app.config.settings import settings
from app.messaging.service import InboundMessagingService
from app.messaging.inbound import InboundMessage, KIND_TEXT

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=engine)
db = sessionmaker(bind=engine)()

org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
db.add(org)
db.commit()
db.refresh(org)

svc = InboundMessagingService(db)

BUYER_TURNS = [
    "Hi 👋 Im running a clothing business and I'm not sure why it's not moving "
    "forward properly. I think I have a poor customer support system and sales. "
    "How can you help me with it?",
    "Explain what the workforce is and what it does. Also the support agent and sales.",
    "web, telegram, whatsapp and email",
    "About 32087",
    "18",
    "English, Yoruba, Hausa, Igbo, Nigerian Pidgin",
]


def scope_now() -> dict:
    conv = db.query(Conversation).order_by(Conversation.id.desc()).first()
    if conv is None:
        return {}
    return json.loads(conv.scope_json or "{}")


for index, text in enumerate(BUYER_TURNS, start=1):
    started = time.monotonic()
    msg = InboundMessage(
        channel="telegram",
        external_id="99001",
        delivery_id=f"tg:{index}",
        kind=KIND_TEXT,
        text=text,
    )
    handled = svc.handle(org.id, msg)
    elapsed = time.monotonic() - started
    print("=" * 78)
    print(f"TURN {index}  ({elapsed:.2f}s)  BUYER: {text}")
    print("-" * 78)
    for reply in handled.replies:
        print(f"NERA: {reply}")
    if handled.channel_messages:
        for cm in handled.channel_messages:
            if cm is None:
                continue
            kb = getattr(cm, "telegram_inline_keyboard", None)
            if kb:
                labels = [b.get("text") for row in kb for b in row]
                print(f"   [keyboard] {labels}")
    print("-" * 78)
    print(f"SCOPE: {json.dumps(scope_now(), sort_keys=True)}")
    print()
