"""Mira: owner-facing Telegram business manager.

Metric answers are computed from organization-scoped database rows. Groq is used
only to classify intent and polish an answer, never to supply metric values.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.conversation import Conversation
from app.models.mira_memory import MiraMemory
from app.models.order import ORDER_PAID, Order
from app.models.organization import Organization

HELP_TEXT = (
    "i'm mira, your nera business manager. ask me how today or this week went, "
    "ask for an overview, or tell me a business fact to remember. "
    "i can report paid orders, revenue and conversations from your workspace. "
    "sales actions like customer follow-ups are noted, not sent or scheduled yet."
)

_OWNER_TASK = re.compile(r"\b(follow\s*up|message|email|contact|call|reach\s+out|remind\s+customers?)\b", re.I)
_MEMORY_PREFIX = re.compile(r"^(?:remember|note|keep in mind)\s+(?:that\s+)?(.+)$", re.I | re.S)


def _period(text: str, now: datetime) -> tuple[datetime, datetime, str] | None:
    if re.search(r"\b(this week|weekly|week)\b", text, re.I):
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7), "this week"
    if re.search(r"\b(today|daily|overview|how did we do)\b", text, re.I):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), "today"
    return None


def _report(db: Session, organization_id: int, text: str, now: datetime | None = None) -> str | None:
    org = db.get(Organization, organization_id)
    if not org:
        return "i couldn't verify the workspace data for that period, so i won't guess."
    try:
        tz = ZoneInfo(org.timezone or "UTC")
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    period = _period(text, now)
    if not period:
        return None
    start, end, label = period
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    order_count = db.scalar(select(func.count(Order.id)).where(
        Order.organization_id == organization_id, Order.status == ORDER_PAID,
        Order.paid_at >= start_utc, Order.paid_at < end_utc,
    ))
    revenue_rows = db.execute(select(Order.currency, func.sum(Order.amount_minor)).where(
        Order.organization_id == organization_id, Order.status == ORDER_PAID,
        Order.paid_at >= start_utc, Order.paid_at < end_utc,
    ).group_by(Order.currency)).all()
    conversation_count = db.scalar(select(func.count(Conversation.id)).where(
        Conversation.organization_id == organization_id,
        Conversation.created_at >= start_utc, Conversation.created_at < end_utc,
    ))
    revenue = ", ".join(f"{currency} {int(amount) / 100:,.2f}" for currency, amount in revenue_rows) or None
    if order_count is None or conversation_count is None:
        return "i couldn't verify the workspace data for that period, so i won't guess."
    revenue_text = revenue or "no paid orders recorded"
    return f"{label}: {order_count} paid order(s), revenue {revenue_text}, {conversation_count} conversation(s)."


def _remember(db: Session, organization_id: int, fact: str) -> str:
    fact = fact.strip().rstrip(".")
    if not fact or len(fact) > 500:
        return "send me one short business fact and i'll keep it in mind."
    key = re.sub(r"[^a-z0-9]+", "_", fact.lower()).strip("_")[:150]
    row = db.execute(select(MiraMemory).where(
        MiraMemory.organization_id == organization_id, MiraMemory.key == key,
    )).scalar_one_or_none()
    if row:
        row.value, row.source = fact, "owner"
    else:
        db.add(MiraMemory(organization_id=organization_id, key=key, value=fact, source="owner"))
    db.commit()
    return f"got it, i'll remember: {fact}"


def _understand(text: str, memories: list[str]) -> str | None:
    """Optional Groq conversational response, constrained by data-first rules."""
    if not settings.GROQ_API_KEY or settings.TESTING:
        return None
    prompt = (
        "You are Mira, a warm, concise business manager in Telegram. "
        "Answer only from the supplied verified workspace facts and memory. "
        "Do not invent metrics or claim to execute work. Sales tasks can only be noted. "
        f"Verified memory: {json.dumps(memories, ensure_ascii=False)}\nOwner: {text}"
    )
    try:
        response = httpx.post(
            f"{settings.GROQ_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json={"model": settings.GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 180},
            timeout=settings.LLM_UNDERSTANDING_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return content.strip()[:1000] if isinstance(content, str) and content.strip() else None
    except Exception:  # model is optional, deterministic response remains safe
        return None


def respond(db: Session, organization_id: int, text: str, command: str = "", now: datetime | None = None) -> str:
    if command in {"mira", "help"}:
        return HELP_TEXT
    memory_match = _MEMORY_PREFIX.match(text.strip())
    if memory_match:
        return _remember(db, organization_id, memory_match.group(1))
    if _OWNER_TASK.search(text):
        task = text.strip()[:300]
        _remember(db, organization_id, f"todo: {task}")
        return f"noted as a TODO: {task}. i haven't contacted anyone or scheduled it."
    report = _report(db, organization_id, text, now)
    if report:
        return report
    memories = db.execute(select(MiraMemory.value).where(
        MiraMemory.organization_id == organization_id,
    ).order_by(MiraMemory.updated_at.desc()).limit(12)).scalars().all()
    llm = _understand(text, list(memories))
    if llm:
        return llm
    if memories:
        return "i've got this in your business memory: " + "; ".join(memories[:5])
    return "i can give you today's or this week's verified orders, revenue and conversation counts, or remember a business fact. what should i focus on?"
