"""Conversation orchestration: the visitor-facing entry point.

Holds the transaction boundary and the side effects the pure agent in
``app.sales.agent`` deliberately has none of — persisting turns, capturing the
visitor as a CRM lead, and raising approval requests.
"""

# Annotations are deferred because the service exposes a ``list`` method,
# which shadows the builtin inside the class body and would otherwise break
# every ``list[...]`` return annotation declared after it.
from __future__ import annotations

import json
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
from app.models.order import Order
from app.models.quote import Quote
from app.models.workspace_profile import WorkspaceProfile
from app.pricing.complexity import CHANNEL_WEB
from app.pricing.quotes import (
    QuoteService,
    plan_code_for,
    reference_from_plan_code,
    requirement_from_json,
)
from app.products.resolver import resolve_config
from app.sales.agent import compose_reply
from app.sales.approvals import ApprovalService
from app.sales.reasoning import Reasoning
from app.sales.rephrase import Rephraser
from app.sales.scoping import Scope
from app.sales.support import SetupFacts

logger = get_logger(__name__)

# Long enough that guessing another visitor's thread is not feasible.
TOKEN_BYTES = 24

# A single message the agent will accept. Past this the visitor is pasting,
# not talking, and long bodies are the cheapest denial-of-service there is.
MAX_MESSAGE_LENGTH = 4_000


class ConversationError(ValueError):
    """Raised when a message cannot be accepted."""


class ConversationService:

    def __init__(self, db: Session, rephraser: Rephraser | None = None):
        self.db = db
        self.approvals = ApprovalService(db)
        # Wording only, and off unless a key is configured. Injectable so tests
        # can exercise both the improved and the rejected path without a network.
        self.rephraser = rephraser or Rephraser()

    def start(
        self,
        organization_id: int,
        workspace_profile_id: int | None = None,
    ) -> Conversation:
        """Open a thread and greet the visitor.

        The greeting is a stored agent message rather than static page copy,
        so the transcript a human reviews later is the whole conversation.

        ``workspace_profile_id`` is which of the organization's agents the visitor
        has opened, and is recorded on the thread rather than looked up per turn:
        a workspace with two agents cannot answer that question from the
        organization, and the greeting is the first place getting it wrong shows —
        a support widget that opens with "I'm Ada, the sales rep".
        """
        conversation = Conversation(
            organization_id=organization_id,
            workspace_profile_id=workspace_profile_id,
            public_token=secrets.token_urlsafe(TOKEN_BYTES),
            stage=STAGE_GREETING,
        )

        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        opening = compose_reply(
            "",
            STAGE_GREETING,
            config=resolve_config(self.db, organization_id, workspace_profile_id),
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
        external_id: str | None = None,
    ) -> Message:
        """Store the visitor's turn, produce the agent's, return the reply.

        ``external_id`` is the platform's id for the delivery that carried this
        message — a Telegram update, a WhatsApp message id — and is null for the
        widget, which has no such thing. It is recorded on the visitor's turn so
        a re-delivery can be recognised as one; see
        ``app.messaging.service.InboundMessagingService``.
        """
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
                external_id=external_id,
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

        config = resolve_config(
            self.db,
            conversation.organization_id,
            conversation.workspace_profile_id,
        )
        reply = compose_reply(
            body,
            conversation.stage,
            config=config,
            interested_plan_code=conversation.interested_plan_code,
            scope=Scope.from_json(conversation.scope_json),
            rules_already_used=self._rules_already_used(conversation.id),
            order_paid=self._order_paid(conversation),
            setup=self._setup_facts(conversation),
        )

        if reply.scope is not None:
            # Written back on every turn that touched it, so the next turn asks
            # the next question rather than the first one again. Stored as the
            # engine's own JSON — this layer does not interpret it.
            conversation.scope_json = reply.scope.to_json()

        if reply.quoted is not None:
            # The agent has just told the buyer a computed figure. Issue the
            # redeemable quote behind it now, so what the checkout re-derives is
            # the requirement that produced the number they were given — not a
            # requirement reassembled later from a transcript.
            #
            # Stamped with the conversation and the org it was quoted in. Without
            # those, a stored quote is a price with no provenance: nothing can
            # answer "where did this figure come from" or "what else was this
            # buyer told", which is the audit trail the whole computed-pricing
            # design rests on.
            #
            # It lands in interested_plan_code as ``quote_<reference>`` because
            # that is the form CheckoutService and ProvisioningService already
            # understand, so a computed price needs no second path to payment.
            quote_row = QuoteService(self.db).issue(
                reply.scope.to_requirement(),
                organization_id=conversation.organization_id,
                conversation_id=conversation.id,
            )
            conversation.interested_plan_code = plan_code_for(quote_row.reference)

        if reply.captured_email and not conversation.visitor_email:
            conversation.visitor_email = reply.captured_email

        # Only ever fills a blank. The agent reads these out of prose, so a
        # value the visitor typed into the widget's own form — or gave on an
        # earlier, clearer turn — outranks anything parsed later.
        if reply.captured_name and not conversation.visitor_name:
            conversation.visitor_name = reply.captured_name

        if reply.captured_company and not conversation.visitor_company:
            conversation.visitor_company = reply.captured_company

        if reply.interested_plan_code:
            # Guard against the agent naming a plan the config has since
            # dropped: store nothing rather than a dangling code. Checked
            # against this conversation's config, not the storefront's — a
            # customer's plan codes are not visible in ours.
            if config.find_plan(reply.interested_plan_code):
                conversation.interested_plan_code = reply.interested_plan_code

        if reply.next_stage:
            conversation.stage = reply.next_stage

        # Wording, last, and only wording.
        #
        # Deliberately after every decision above has been made and recorded.
        # The stage, the scope, the quote and the plan code are all derived from
        # the reply the rules composed, so nothing a model returns can change
        # what this conversation *is* — only how the next sentence reads. And it
        # is here rather than in a channel, so the widget, Telegram and WhatsApp
        # get the same wording instead of three drifting voices.
        #
        # What is stored is what the buyer saw. A transcript that shows the
        # composed text while the buyer read something else would make every
        # later dispute unanswerable.
        body_for_visitor = self.rephraser.rephrase(reply.body)

        agent_message = Message(
            conversation_id=conversation.id,
            role=ROLE_AGENT,
            body=body_for_visitor,
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

    def _order_paid(self, conversation: Conversation) -> bool | None:
        """Whether this conversation's order has been paid, or None if there is none.

        Read here rather than in the engine because the engine is pure, and looked
        up on every turn rather than only when it looks relevant because the
        engine is the thing that decides relevance — this layer does not get to
        guess which messages are about a payment.

        The newest order wins. A buyer who abandoned one checkout and completed
        another is asking about the one they just paid.
        """
        order = (
            self.db.query(Order)
            .filter(Order.conversation_id == conversation.id)
            .order_by(Order.id.desc())
            .first()
        )

        return None if order is None else order.is_paid

    def _setup_facts(self, conversation: Conversation) -> SetupFacts | None:
        """What is true of this buyer's workspace, if this buyer has one.

        Returns None for everybody else, which is nearly everybody, and the
        engine treats None as "the support path does not apply". Looked up on
        every turn for the same reason ``_order_paid`` is: the engine decides
        which messages are about a broken install, and this layer does not get to
        guess.

        **Only the thread the purchase was made in.** The link is
        ``Order.conversation_id`` → ``WorkspaceProfile.order_id``, which is
        narrow on purpose. A customer's own widget serves *their* end-customers,
        and one of those saying "it's not working" is talking about a dress or a
        delivery, not about our software. Resolving the workspace from
        ``conversation.organization_id`` instead would have handed every one of
        those people install instructions for a chat widget they have never heard
        of.

        Unpaid orders are excluded. Before payment there is no workspace for any
        of this to be true of, and the buyer is still a buyer.
        """
        order = (
            self.db.query(Order)
            .filter(Order.conversation_id == conversation.id)
            .order_by(Order.id.desc())
            .first()
        )

        if order is None or not order.is_paid:
            return None

        profiles = (
            self.db.query(WorkspaceProfile)
            .filter(WorkspaceProfile.order_id == order.id)
            .order_by(WorkspaceProfile.id)
            .all()
        )

        if not profiles:
            # Paid, and nothing provisioned against it. Still a customer — they
            # are owed something — and ``workspace_ready`` False is what makes
            # the engine say the build has not finished rather than send them
            # looking for a snippet that was never issued.
            return SetupFacts(is_customer=True)

        return SetupFacts(
            is_customer=True,
            # Named only when there is one agent to name. With both a sales rep
            # and a support agent in the workspace, "Ada answers out of your
            # material" is true of one of two things the customer owns, and the
            # generic phrasing is the accurate one.
            agent_name=profiles[0].agent_name if len(profiles) == 1 else "",
            # Every profile, not any: a customer who bought two agents and has
            # one still building is mid-provision, and telling them the build is
            # finished would send them hunting for a fault that is ours.
            workspace_ready=all(profile.is_ready for profile in profiles),
            has_widget_token=any(profile.widget_token for profile in profiles),
            widget_last_seen=self._latest_widget_load(profiles),
            bought_channels=self._channels_bought(order),
            # Honest rather than aspirational. Provisioning issues a widget token
            # and nothing else — there is no per-customer Telegram bot or
            # WhatsApp number yet — so web is the only channel that is actually
            # live, and the gap against ``bought_channels`` is what makes the
            # engine own the shortfall instead of walking the customer through a
            # setup that does not exist.
            live_channels=(
                (CHANNEL_WEB,)
                if any(profile.widget_token for profile in profiles)
                else ()
            ),
            conversations_handled=self._conversations_handled(profiles),
        )

    @staticmethod
    def _latest_widget_load(profiles: list[WorkspaceProfile]) -> datetime | None:
        """The most recent time any of this customer's snippets ran.

        The newest wins because the question it answers is "has the code ever
        reached us", and one agent loading is enough to prove the install works.
        """
        seen = [
            profile.widget_last_seen_at
            for profile in profiles
            if profile.widget_last_seen_at is not None
        ]

        return max(seen) if seen else None

    def _channels_bought(self, order: Order) -> tuple[str, ...]:
        """The channels this order actually paid for.

        Read from the stored quote's requirement — the same JSON the checkout
        re-priced and provisioning read the products from — so what the customer
        is told they bought is what they were charged for.

        A catalog order predates computed pricing and has no requirement behind
        it, so it gets web alone, which is what those plans were. An unreadable
        quote gets the same treatment rather than an exception: this is a
        diagnostic detail on a support reply, and failing a customer's turn over
        it would replace a slightly vaguer answer with no answer.
        """
        reference = reference_from_plan_code(order.plan_code)

        if reference is None:
            return (CHANNEL_WEB,)

        quote = (
            self.db.query(Quote).filter(Quote.reference == reference).first()
        )

        if quote is None:
            return (CHANNEL_WEB,)

        try:
            return requirement_from_json(quote.requirement_json).channels
        except (ValueError, KeyError, TypeError):
            logger.warning(
                "Quote %s has a requirement we cannot read; assuming web only "
                "for support diagnostics.",
                reference,
            )
            return (CHANNEL_WEB,)

    def _conversations_handled(self, profiles: list[WorkspaceProfile]) -> int:
        """How many conversations this customer's own agents have answered.

        Proof the agent works, which is what turns "it is not replying" from "it
        was never installed" into "this page or this browser". Counted across the
        customer's organization rather than per profile, because the claim being
        made is about their agents in general.

        Threads with no agent turn do not count. A conversation row that was
        opened and abandoned is not evidence that anything replied, and evidence
        is the only reason this number is being read.
        """
        organization_ids = {profile.organization_id for profile in profiles}

        if not organization_ids:
            return 0

        return (
            self.db.query(Message.conversation_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .filter(
                Conversation.organization_id.in_(organization_ids),
                Message.role == ROLE_AGENT,
            )
            .distinct()
            .count()
        )

    def _rules_already_used(self, conversation_id: int) -> frozenset[str]:
        """Which rules have already spoken in this thread.

        Read back out of the reasoning trail the agent writes on every turn
        anyway, rather than kept as a second piece of state that could disagree
        with it. The agent uses it to avoid repeating a reply word for word; it
        is wording only, and nothing about a price, a stage or a scope depends
        on it.

        Malformed rows are skipped rather than raised on. A reasoning blob that
        cannot be read is a cosmetic loss — the reply is simply worded as if it
        were the first — and is not worth failing a visitor's turn over.
        """
        rows = (
            self.db.query(Message.reasoning_json)
            .filter(
                Message.conversation_id == conversation_id,
                Message.role == ROLE_AGENT,
                Message.reasoning_json.isnot(None),
            )
            .all()
        )

        rules = set()

        for (raw,) in rows:
            try:
                rule = json.loads(raw).get("rule")
            except (TypeError, ValueError):
                continue

            if rule:
                rules.add(rule)

        return frozenset(rules)

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
