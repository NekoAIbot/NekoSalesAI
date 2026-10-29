"""Scheduling and sending post-sale follow-ups.

Three jobs, kept apart on purpose.

``schedule_for`` runs once, when a workspace goes live, and writes the whole
calendar at once. Writing it up front rather than deciding each morning means
the queue is inspectable: a customer who paid today has six dated rows against
their name, and anyone can look at what they are going to receive before they
receive it.

``due`` answers "what is owed right now" and nothing else.

``send`` re-evaluates the rule before it delivers. That second check is the
important one. A calendar written on day zero cannot know the customer will
install the widget on day two, so the day-three "nothing has reached you yet"
note has to be able to withdraw itself. Cancelled, with a reason, rather than
deleted.

Delivery goes through an injectable sender for the same reason payments go
through an injectable transport: the whole loop has to be testable with no
account, no credentials and no network. With no sender configured the app does
not pretend to have emailed anyone — the follow-up stays open on the sales
desk for a human to send, and says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.catalog import COMPANY
from app.config.logging import get_logger
from app.config.settings import settings
from app.followups.rules import RULES, RULES_BY_CODE, FollowUpContext, Rule
from app.models.conversation import Conversation
from app.models.follow_up import (
    STATUS_CANCELLED,
    STATUS_SCHEDULED,
    STATUS_SENDING,
    STATUS_SENT,
    FollowUp,
)
from app.models.order import Order
from app.models.workspace_profile import WorkspaceProfile

logger = get_logger(__name__)

# Maximum time a follow-up can remain in STATUS_SENDING before being deemed
# abandoned by a crashed or unresponsive worker and reclaimed for retry.
CLAIM_TIMEOUT = timedelta(minutes=5)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def reclaim_stale_claims(
    db: Session,
    now: datetime | None = None,
    timeout: timedelta = CLAIM_TIMEOUT,
) -> int:
    """Reclaim follow-ups stuck in 'sending' state due to a worker crash.

    If a process crashes between acquiring an in-flight lease and completing
    delivery or marking the record as sent, the row remains in STATUS_SENDING.
    Once ``timeout`` has elapsed, the lease is considered expired and the row
    is restored to STATUS_SCHEDULED so subsequent runner passes will retry it.

    Returns the number of reclaimed rows.
    """
    moment = _ensure_utc(now) or datetime.now(timezone.utc)
    cutoff = moment - timeout

    result = db.execute(
        update(FollowUp)
        .where(
            FollowUp.status == STATUS_SENDING,
            or_(
                FollowUp.updated_at <= cutoff,
                FollowUp.updated_at.is_(None),
            ),
        )
        .values(
            status=STATUS_SCHEDULED,
            updated_at=moment,
        )
    )
    if result.rowcount > 0:
        db.commit()
        logger.warning(
            "Reclaimed %d stale follow-up(s) stuck in sending lease",
            result.rowcount,
        )
    return result.rowcount


class FollowUpSendError(Exception):
    """Delivery failed. The follow-up stays open."""


class FollowUpClaimConflict(FollowUpSendError):
    """The follow-up was claimed or is currently in-flight by another worker."""


@dataclass(frozen=True)
class Delivery:
    """One outbound message, as handed to a sender."""

    to_email: str
    subject: str
    body: str


class Sender(Protocol):
    """Whatever actually delivers the message.

    A Protocol rather than a base class so a test can pass a plain object with
    one method. The real implementation is an email provider; there is no
    account for one yet, which is exactly why this is an interface.
    """

    def send(self, delivery: Delivery) -> None: ...


class UnconfiguredSender:
    """The honest no-op.

    Raises rather than silently succeeding. A sender that quietly discarded
    messages would let the desk mark follow-ups as sent that no customer ever
    received, which is a worse failure than an obvious one.
    """

    def send(self, delivery: Delivery) -> None:
        raise FollowUpSendError(
            "No email sender is configured, so this cannot be delivered "
            "automatically. Copy the message and send it yourself, then mark "
            "it sent."
        )


class FollowUpService:
    def __init__(self, db: Session, sender: Sender | None = None):
        self.db = db
        self.sender = sender or UnconfiguredSender()

    # ---------- scheduling ----------

    def schedule_for(self, profile: WorkspaceProfile, order: Order | None = None) -> list[FollowUp]:
        """Write the calendar for a newly-live workspace.

        Safe to call more than once. Provisioning is idempotent and calls this
        on every confirmation attempt, so this skips any rule already on the
        books for the workspace rather than raising on the unique constraint.
        """
        if not profile.is_ready or profile.ready_at is None:
            return []

        existing = {
            code
            for (code,) in self.db.execute(
                select(FollowUp.rule_code).where(
                    FollowUp.workspace_profile_id == profile.id
                )
            ).all()
        }

        context = self.build_context(profile, order)
        created: list[FollowUp] = []

        for rule in RULES:
            if rule.code in existing:
                continue

            # Conditions are re-checked at send time too. Scheduling
            # optimistically here means a rule whose condition is false today
            # but true on its due date still gets its chance.
            subject, body, reasoning = rule.render(context)

            follow_up = FollowUp(
                organization_id=self._seller_organization_id(order),
                workspace_profile_id=profile.id,
                order_id=order.id if order is not None else profile.order_id,
                rule_code=rule.code,
                day_offset=rule.day_offset,
                due_at=profile.ready_at + timedelta(days=rule.day_offset),
                subject=subject,
                body=body,
                reasoning_json=reasoning.to_json(),
            )

            self.db.add(follow_up)
            created.append(follow_up)

        if created:
            self.db.commit()
            for follow_up in created:
                self.db.refresh(follow_up)

            logger.info(
                "Scheduled %d follow-ups for workspace %s",
                len(created),
                profile.id,
            )

        return created

    # ---------- reading ----------

    def due(
        self,
        organization_id: int,
        now: datetime | None = None,
    ) -> list[FollowUp]:
        """Follow-ups owed as of ``now``, oldest first."""
        moment = now or datetime.now(timezone.utc)
        reclaim_stale_claims(self.db, now=moment)

        return list(
            self.db.execute(
                select(FollowUp)
                .where(
                    FollowUp.organization_id == organization_id,
                    FollowUp.status == STATUS_SCHEDULED,
                    FollowUp.due_at <= moment,
                )
                .order_by(FollowUp.due_at.asc())
            ).scalars().all()
        )

    def list(
        self,
        organization_id: int,
        status: str | None = None,
    ) -> list[FollowUp]:
        query = select(FollowUp).where(FollowUp.organization_id == organization_id)

        if status:
            query = query.where(FollowUp.status == status)

        return list(
            self.db.execute(query.order_by(FollowUp.due_at.asc())).scalars().all()
        )

    def get(self, organization_id: int, follow_up_id: int) -> FollowUp | None:
        """Scoped by organization in the query — the tenant boundary."""
        return self.db.execute(
            select(FollowUp).where(
                FollowUp.id == follow_up_id,
                FollowUp.organization_id == organization_id,
            )
        ).scalars().first()

    # ---------- sending ----------

    def send(self, follow_up: FollowUp) -> FollowUp:
        """Deliver one follow-up, after checking it is still warranted.

        Uses an atomic lease (STATUS_SENDING) to prevent concurrent duplicate sends.
        If delivery succeeds, it transitions to STATUS_SENT.
        If delivery fails with an exception, it immediately rolls back to STATUS_SCHEDULED.
        If the process crashes during transmission, the lease will expire after
        CLAIM_TIMEOUT and be reclaimed on the next runner pass, preventing silent drops.
        """
        now_dt = datetime.now(timezone.utc)
        stale_cutoff = now_dt - CLAIM_TIMEOUT

        if follow_up.status not in (STATUS_SCHEDULED, STATUS_SENDING):
            raise FollowUpSendError(
                f"This follow-up is already {follow_up.status}."
            )

        if follow_up.status == STATUS_SENDING:
            updated_at = _ensure_utc(follow_up.updated_at)
            if updated_at and updated_at > stale_cutoff:
                raise FollowUpClaimConflict(
                    f"This follow-up is currently in-flight (status: {follow_up.status})."
                )

        rule = RULES_BY_CODE.get(follow_up.rule_code)

        if rule is None:
            # The rule was removed from the code but its rows survive. Do not
            # send a message whose basis no longer exists.
            return self.cancel(follow_up, "The rule behind this no longer exists.")

        profile = self.db.get(WorkspaceProfile, follow_up.workspace_profile_id)

        if profile is None:
            return self.cancel(follow_up, "The workspace no longer exists.")

        order = (
            self.db.get(Order, follow_up.order_id)
            if follow_up.order_id is not None
            else None
        )
        context = self.build_context(profile, order)

        if not rule.applies(context):
            return self.cancel(
                follow_up,
                "Overtaken by events — the condition no longer holds.",
            )

        # Re-render against today's facts. A month-old draft would quote a
        # conversation count from the day the workspace was created.
        subject, body, reasoning = rule.render(context)
        follow_up.subject = subject
        follow_up.body = body
        follow_up.reasoning_json = reasoning.to_json()

        recipient = self._recipient(profile, order)

        if not recipient:
            return self.cancel(follow_up, "No email address on file.")

        # 1. ATOMIC LEASE ACQUISITION:
        # Transition from scheduled (or expired in-flight claim) to sending.
        # If another worker already claimed or sent this row concurrently,
        # the conditional UPDATE affects 0 rows, preventing duplicate sends.
        claim_stmt = (
            update(FollowUp)
            .where(
                FollowUp.id == follow_up.id,
                or_(
                    FollowUp.status == STATUS_SCHEDULED,
                    and_(
                        FollowUp.status == STATUS_SENDING,
                        or_(
                            FollowUp.updated_at <= stale_cutoff,
                            FollowUp.updated_at.is_(None),
                        ),
                    ),
                ),
            )
            .values(
                status=STATUS_SENDING,
                updated_at=now_dt,
                subject=subject,
                body=body,
                reasoning_json=reasoning.to_json(),
            )
        )
        claimed = self.db.execute(claim_stmt)
        self.db.commit()

        if claimed.rowcount == 0:
            raise FollowUpClaimConflict(
                f"This follow-up is already being processed or has status {follow_up.status}."
            )

        # 2. DELIVER VIA SENDER:
        try:
            self.sender.send(Delivery(to_email=recipient, subject=subject, body=body))
        except Exception:
            # Delivery failed: revert back to scheduled so the next run can retry,
            # ensuring transient mail failures do not lose scheduled messages.
            # Fencing check: only revert if this worker still owns the lease. If another
            # worker already reclaimed or completed it, do not overwrite their state.
            self.db.execute(
                update(FollowUp)
                .where(
                    FollowUp.id == follow_up.id,
                    FollowUp.status == STATUS_SENDING,
                    FollowUp.updated_at == now_dt,
                )
                .values(status=STATUS_SCHEDULED, updated_at=datetime.now(timezone.utc))
            )
            self.db.commit()
            raise

        # 3. SUCCESS TRANSITION:
        # Fencing check: transition to sent only if this worker still owns the lease.
        success_dt = datetime.now(timezone.utc)
        claim_res = self.db.execute(
            update(FollowUp)
            .where(
                FollowUp.id == follow_up.id,
                FollowUp.status == STATUS_SENDING,
                FollowUp.updated_at == now_dt,
            )
            .values(
                status=STATUS_SENT,
                sent_at=success_dt,
                updated_at=success_dt,
            )
        )
        self.db.commit()

        if claim_res.rowcount == 0:
            # The lease expired during outbound transmission.
            # Inspect the current row state to check whether safe salvage is possible
            # without overwriting newer state from a competing claim.
            current_row = self.db.get(FollowUp, follow_up.id)
            if current_row is None:
                raise FollowUpSendError(
                    f"Follow-up {follow_up.id} disappeared while sending was in progress."
                )

            if current_row.status == STATUS_SCHEDULED:
                # SAFE AUTOMATIC SALVAGE:
                # The lease expired and reclaim_stale_claims restored the row to STATUS_SCHEDULED,
                # but no competing worker has claimed it into STATUS_SENDING yet.
                # Since this worker already delivered the message to the recipient,
                # atomically transitioning from STATUS_SCHEDULED to STATUS_SENT prevents
                # subsequent runner passes from sending an avoidable duplicate message.
                salvaged = self.db.execute(
                    update(FollowUp)
                    .where(
                        FollowUp.id == follow_up.id,
                        FollowUp.status == STATUS_SCHEDULED,
                    )
                    .values(
                        status=STATUS_SENT,
                        sent_at=success_dt,
                        updated_at=success_dt,
                    )
                )
                self.db.commit()
                if salvaged.rowcount > 0:
                    logger.warning(
                        "Follow-up %s lease expired during slow send (acquired %s) "
                        "but was successfully salvaged to sent from scheduled state.",
                        follow_up.id,
                        now_dt,
                    )
                    self.db.refresh(follow_up)
                    return follow_up

            # Safe automatic salvage is not possible:
            # - If status is STATUS_SENT: another worker already claimed and sent it (duplicate delivered externally).
            # - If status is STATUS_SENDING: another worker holds the active lease and is sending.
            # - If status is STATUS_CANCELLED: cancelled by user or workflow.
            # We must NOT overwrite the newer worker's state. Document the ambiguity.
            logger.warning(
                "Follow-up %s lease expired during slow send (acquired %s) and could not "
                "be salvaged; competing status is %r (updated_at=%s). Leaving current state intact.",
                follow_up.id,
                now_dt,
                current_row.status,
                current_row.updated_at,
            )
            self.db.refresh(follow_up)
            if current_row.status == STATUS_SENDING:
                raise FollowUpClaimConflict(
                    f"Follow-up {follow_up.id} was reclaimed and claimed by another worker "
                    f"while slow send was in flight."
                )
            if current_row.status != STATUS_SENT:
                raise FollowUpSendError(
                    f"Follow-up {follow_up.id} lease expired and row transitioned to {current_row.status}."
                )
            return follow_up

        self.db.refresh(follow_up)

        logger.info(
            "Sent follow-up %s (%s) to %s",
            follow_up.id,
            follow_up.rule_code,
            recipient,
        )

        return follow_up

    def mark_sent_manually(self, follow_up: FollowUp) -> FollowUp:
        """Record that a human sent this themselves.

        Needed because the default sender refuses to deliver. Without this the
        desk would have no way to clear a follow-up it had actually actioned,
        and the queue would only ever grow.
        """
        if not follow_up.is_open:
            raise FollowUpSendError(
                f"This follow-up is already {follow_up.status}."
            )

        follow_up.status = STATUS_SENT
        follow_up.sent_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(follow_up)
        return follow_up

    def cancel(self, follow_up: FollowUp, reason: str) -> FollowUp:
        follow_up.status = STATUS_CANCELLED
        follow_up.cancelled_reason = reason[:255]
        self.db.commit()
        self.db.refresh(follow_up)
        return follow_up

    # ---------- context ----------

    def build_context(
        self,
        profile: WorkspaceProfile,
        order: Order | None = None,
    ) -> FollowUpContext:
        """Assemble the facts the rules read. Every field is a real value."""
        if order is None and profile.order_id is not None:
            order = self.db.get(Order, profile.order_id)

        conversation_count = (
            self.db.execute(
                select(func.count(Conversation.id)).where(
                    Conversation.organization_id == profile.organization_id
                )
            ).scalar()
            or 0
        )

        return FollowUpContext(
            company_name=profile.company_name,
            buyer_name=order.buyer_name if order is not None else None,
            plan_code=profile.plan_code,
            plan_name=(
                order.plan_name if order is not None else profile.plan_code
            ),
            amount_minor=order.amount_minor if order is not None else 0,
            currency=order.currency if order is not None else "NGN",
            api_key_prefix=profile.api_key_prefix,
            conversation_count=conversation_count,
            support_email=COMPANY["support_email"],
            dashboard_url=f"{settings.PUBLIC_BASE_URL.rstrip('/')}/desk",
            agent_name=profile.agent_name,
            widget_token=profile.widget_token,
            # Direct evidence, not an inference: the widget asks for its config
            # every time it loads, and it can only load from a page carrying the
            # snippet. Without this the install emails have to guess, and they
            # guessed the same way for every customer including the ones whose
            # install was already working.
            widget_last_seen=profile.widget_last_seen_at,
        )

    # ---------- helpers ----------

    def _seller_organization_id(self, order: Order | None) -> int:
        """Whose desk this lands on.

        The order's organization is the storefront that made the sale, which
        is not the workspace organization created for the buyer. Getting this
        backwards would file every follow-up in the customer's own tenant,
        where the seller could not see it.
        """
        if order is not None:
            return order.organization_id

        raise ValueError(
            "Cannot schedule follow-ups without an order to attribute them to."
        )

    @staticmethod
    def _recipient(profile: WorkspaceProfile, order: Order | None) -> str | None:
        if order is not None and order.buyer_email:
            return order.buyer_email

        organization = profile.organization
        return organization.email if organization is not None else None


def rule_for(code: str) -> Rule | None:
    return RULES_BY_CODE.get(code)
