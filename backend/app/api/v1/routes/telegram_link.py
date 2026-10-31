import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.channel_identity import CHANNEL_TELEGRAM, ChannelIdentity
from app.sales.service import ConversationService
from app.models.conversation import Conversation
from app.models.base_model import BaseModel
from app.models.user import User
from app.models.order import Order, ORDER_PAID

from app.config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])
LINK_TTL = timedelta(minutes=10)


class TelegramLinkToken(BaseModel):
    """Short-lived, single-use proof that a Telegram chat belongs to a user."""

    __tablename__ = "telegram_link_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@router.post("/link-token")
def create_link_token(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="This account has no organization.")
    has_purchase = db.execute(
        select(Order.id).where(
            Order.organization_id == current_user.organization_id,
            Order.status == ORDER_PAID,
        ).limit(1)
    ).scalar() is not None
    logger.info(
        "telegram link-token attempt: user=%s org=%s paid_orders=%s",
        current_user.id, current_user.organization_id, "yes" if has_purchase else "no",
    )
    if not has_purchase:
        raise HTTPException(
            status_code=403,
            detail="Connect Telegram unlocks with your first Nera purchase. Once your plan is active, link your account here.",
        )
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(TelegramLinkToken(
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        expires_at=now + LINK_TTL,
    ))
    db.commit()
    return {"url": f"https://t.me/zurinerabot?start=link_{token}", "expires_in_seconds": int(LINK_TTL.total_seconds())}


def exchange_link_token(db: Session, token: str, chat_id: str, display_name: str | None = None) -> bool:
    """Consume a dashboard token and attach the Telegram identity to its organization."""
    digest = hashlib.sha256(token.encode()).hexdigest()
    record = db.execute(
        select(TelegramLinkToken).where(TelegramLinkToken.token_hash == digest).with_for_update()
    ).scalars().first()
    now = datetime.now(timezone.utc)
    if not record or record.consumed_at is not None:
        return False
    expiry = record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= now:
        return False
    existing = db.execute(select(ChannelIdentity).where(
        ChannelIdentity.channel == CHANNEL_TELEGRAM,
        ChannelIdentity.external_id == chat_id,
    )).scalars().first()
    if existing:
        existing.organization_id = record.organization_id
        existing.owner_user_id = record.user_id
        existing.display_name = display_name or existing.display_name
        conversation = db.get(Conversation, existing.conversation_id)
        if conversation:
            conversation.organization_id = record.organization_id
    else:
        conversation = ConversationService(db).start(record.organization_id)
        conversation.visitor_name = display_name
        db.add(ChannelIdentity(
            organization_id=record.organization_id,
            channel=CHANNEL_TELEGRAM,
            external_id=chat_id,
            conversation_id=conversation.id,
            display_name=display_name,
            owner_user_id=record.user_id,
        ))
    record.consumed_at = now
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True
