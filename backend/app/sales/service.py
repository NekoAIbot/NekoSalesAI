"""Conversation orchestration: the visitor-facing entry point.

Holds the transaction boundary and the side effects the pure agent in
``app.sales.agent`` deliberately has none of — persisting turns, capturing the
visitor as a CRM lead, and raising approval requests.
"""

# Annotations are deferred because the service exposes a ``list`` method,
# which shadows the builtin inside the class body and would otherwise break
# every ``list[...]`` return annotation declared after it.
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.models.conversation import (
    ROLE_AGENT,
    ROLE_VISITOR,
    STAGE_GREETING,
    Conversation,
    Message,
)
from app.models.lead import Lead
from app.products.resolver import resolve_config
from app.sales.agent import compose_reply
from app.sales.approvals import ApprovalService
from app.sales.reasoning import Reasoning

logger = get_logger(__name__)

# Long enough that guessing another visitor's thread is not feasible.
TOKEN_BYTES = 24

# A single message the agent will accept. Past this the visitor is pasting,
# not talking, and long bodies are the cheapest denial-of-service there is.
MAX_MESSAGE_LENGTH = 4_000


class ConversationError(ValueError):
    """Raised when a message cannot be accepted."""


class ConversationService:

    def __init__(self, db: Session):
        self.db = db
        self.approvals = ApprovalService(db)

    def start(self, organization_id: int) -> Conversation:
        """Open a thread and greet the visitor.

        The greeting is a stored agent message rather than static page copy,
        so the transcript a human reviews later is the whole conversation.
        """
        conversation = Conversation(
            organization_id=organization_id,
            public_token=secrets.token_urlsafe(TOKEN_BYTES),
            stage=STAGE_GREETING,
        )

        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        opening = compose_reply(
            "",
            STAGE_GREETING,
            config=resolve_config(self.db, organization_id),
        )

        self.db.add(
            Message(
                conversation_id=conversation.id,
                role=ROLE_AGENT,
                body=opening.body,
                reasoning_json=opening.reasoning.to_json(),
            )
        )

        if opening.next_stage:
            conversation.stage = opening.next_stage

        self.db.commit()
        self.db.refresh(conversation)

        return conversation

    def get_by_token(self, token: str) -> Conversation | None:
        if not token:
            return None

        return (
            self.db.query(Conversation)
            .filter(Conversation.public_token == token)
            .first()
        )

    def get(
        self,
        organization_id: int,
        conversation_id: int,
    ) -> Conversation | None:
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
            .first()
        )

    def list(self, organization_id: int) -> list[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(Conversation.organization_id == organization_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )

    def messages(self, conversation_id: int) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id)
            .all()
        )

    def handle_visitor_message(
        self,
        conversation: Conversation,
        body: str,
    ) -> Message:
        """Store the visitor's turn, produce the agent's, return the reply."""
        body = (body or "").strip()

        if not body:
            raise ConversationError("Message cannot be empty.")

        if len(body) > MAX_MESSAGE_LENGTH:
            raise ConversationError(
                f"Message is too long (limit {MAX_MESSAGE_LENGTH:,} "
                "characters)."
            )

        self.db.add(
            Message(
                conversation_id=conversation.id,
                role=ROLE_VISITOR,
                body=body,
            )
        )
        self.db.commit()

        # Once a human has taken the thread, the agent stays quiet. Replying
        # over a person mid-negotiation is how an AI contradicts the deal its
        # own colleague just agreed.
        if conversation.is_handed_off:
            self.db.refresh(conversation)
            return Message(
                conversation_id=conversation.id,
                role=ROLE_AGENT,
                body="",
                reasoning_json=Reasoning(
                    rule="suppressed_handed_off",
                    signals=["a human owns this conversation"],
                ).to_json(),
            )

        config = resolve_config(self.db, conversation.organization_id)
        reply = compose_reply(body, conversation.stage, config=config)

        if reply.captured_email and not conversation.visitor_email:
            conversation.visitor_email = reply.captured_email

        if reply.interested_plan_code:
            # Guard against the agent naming a plan the config has since
            # dropped: store nothing rather than a dangling code. Checked
            # against this conversation's config, not the storefront's — a
            # customer's plan codes are not visible in ours.
            if config.find_plan(reply.interested_plan_code):
                conversation.interested_plan_code = reply.interested_plan_code

        if reply.next_stage:
            conversation.stage = reply.next_stage

        agent_message = Message(
            conversation_id=conversation.id,
            role=ROLE_AGENT,
            body=reply.body,
            reasoning_json=reply.reasoning.to_json(),
        )

        self.db.add(agent_message)
        self.db.commit()

        if reply.needs_approval:
            # Raised after the reply is committed: the visitor has already
            # been told a human will check, so the row backing that promise
            # must exist even if this is the last thing that happens.
            self.approvals.create(
                conversation=conversation,
                subject=reply.approval_subject or "Needs a human",
                requested=reply.approval_request or body,
            )

        self._sync_lead(conversation)

        self.db.refresh(agent_message)

        return agent_message

    def update_visitor_details(
        self,
        conversation: Conversation,
        name: str | None = None,
        email: str | None = None,
        company: str | None = None,
    ) -> Conversation:
        if name:
            conversation.visitor_name = name.strip()

        if email:
            conversation.visitor_email = email.strip()

        if company:
            conversation.visitor_company = company.strip()

        self.db.commit()
        self.db.refresh(conversation)

        self._sync_lead(conversation)

        return conversation

    def hand_off(self, conversation: Conversation, reason: str) -> Conversation:
        conversation.handed_off_at = datetime.now(timezone.utc)
        conversation.handoff_reason = reason

        self.db.commit()
        self.db.refresh(conversation)

        return conversation

    def _sync_lead(self, conversation: Conversation) -> None:
        """Mirror the visitor into the CRM once we know who they are.

        Reuses the existing Lead table rather than adding a parallel notion of
        a person: a website visitor who gives their email *is* a lead, and the
        team should see them in the same list as every other one.
        """
        if not conversation.visitor_email:
            return

        if conversation.lead_id:
            lead = (
                self.db.query(Lead)
                .filter(Lead.id == conversation.lead_id)
                .first()
            )

            if lead:
                lead.status = _lead_status_for(conversation.stage)
                self.db.commit()

            return

        existing = (
            self.db.query(Lead)
            .filter(
                Lead.organization_id == conversation.organization_id,
                Lead.email == conversation.visitor_email,
            )
            .first()
        )

        if existing:
            conversation.lead_id = existing.id
            existing.status = _lead_status_for(conversation.stage)
            self.db.commit()
            return

        first_name, last_name = _split_name(conversation.visitor_name)

        lead = Lead(
            organization_id=conversation.organization_id,
            first_name=first_name,
            last_name=last_name,
            email=conversation.visitor_email,
            company=conversation.visitor_company,
            source="AI Chat",
            status=_lead_status_for(conversation.stage),
            notes="Created from a website chat with the AI sales rep.",
        )

        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)

        conversation.lead_id = lead.id
        self.db.commit()

        logger.info(
            "Captured lead %s from conversation %s",
            lead.id,
            conversation.id,
        )


def _split_name(full_name: str | None) -> tuple[str, str]:
    """Lead requires both name columns; visitors rarely give both."""
    if not full_name or not full_name.strip():
        return "Website", "Visitor"

    parts = full_name.strip().split()

    if len(parts) == 1:
        return parts[0], "—"

    return parts[0], " ".join(parts[1:])


def _lead_status_for(stage: str) -> str:
    """Map conversation stage onto the CRM statuses the board already uses."""
    from app.models.conversation import (
        STAGE_AWAITING_APPROVAL,
        STAGE_CLOSED_WON,
        STAGE_NEGOTIATING,
        STAGE_QUALIFIED,
        STAGE_READY_TO_BUY,
    )

    mapping = {
        STAGE_QUALIFIED: "Qualified",
        STAGE_NEGOTIATING: "Negotiating",
        STAGE_AWAITING_APPROVAL: "Negotiating",
        STAGE_READY_TO_BUY: "Ready to Buy",
        STAGE_CLOSED_WON: "Won",
    }

    return mapping.get(stage, "New")
