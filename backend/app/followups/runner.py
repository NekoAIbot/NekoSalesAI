"""The runner that makes the follow-up calendar ring.

``FollowUpService.due`` has always answered "what is owed right now" correctly,
and until this module nothing ever asked. Six follow-ups were scheduled the
moment a workspace went live — day 0, 1, 3, 7, 14, 30 — and then sat in the table
waiting for a human to notice them in the desk. The loop was a calendar with no
alarm.

Run it from cron, or by hand:

    python -m app.followups.runner            # send what is due
    python -m app.followups.runner --dry-run  # list it without sending

Every decision about *whether* to send and *what* to say stays in
``FollowUpService.send`` and the rules: this walks the due list and calls it. That
matters because ``send`` re-renders against today's facts and cancels anything
overtaken by events, so a runner that composed its own messages would bypass the
only code that knows a follow-up has become wrong.

One follow-up failing does not stop the run. A single bad address in a batch of
fifty should cost one message, not forty-nine.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import configure_logging, get_logger
from app.database.session import SessionLocal
from app.followups.dispatcher import FollowUpDispatcher
from app.followups.service import FollowUpSendError, FollowUpService
from app.models.follow_up import STATUS_SCHEDULED, STATUS_SENT, FollowUp
from app.models.workspace_profile import WorkspaceProfile

logger = get_logger(__name__)


@dataclass
class RunReport:
    """What one pass did. Returned so a caller can assert on it."""

    due: int = 0
    sent: int = 0
    cancelled: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def summary(self) -> str:
        return (
            f"{self.due} due, {self.sent} sent, "
            f"{self.cancelled} cancelled, {self.failed} failed"
        )


def due_across_organizations(
    db: Session,
    now: datetime | None = None,
) -> list[FollowUp]:
    """Everything owed, for every tenant, oldest first.

    ``FollowUpService.due`` is scoped to one organization because every caller
    until now was answering a request on behalf of one. The runner is the first
    caller that legitimately spans tenants, so the cross-tenant query lives here
    rather than loosening the scoped method others depend on.
    """
    moment = now or datetime.now(timezone.utc)

    return list(
        db.execute(
            select(FollowUp)
            .where(
                FollowUp.status == STATUS_SCHEDULED,
                FollowUp.due_at <= moment,
            )
            .order_by(FollowUp.due_at.asc())
        ).scalars().all()
    )


def _service_for(db: Session, follow_up: FollowUp) -> FollowUpService | None:
    """A service whose sender matches this workspace's chosen channels.

    Returns None when the workspace has gone, so the caller can cancel rather
    than send into nothing.
    """
    profile = db.get(WorkspaceProfile, follow_up.workspace_profile_id)

    if profile is None:
        return None

    return FollowUpService(db, sender=FollowUpDispatcher(profile))


def run_due(
    db: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    service: FollowUpService | None = None,
) -> RunReport:
    """Send every follow-up that is owed."""
    follow_ups = due_across_organizations(db, now=now)
    report = RunReport(due=len(follow_ups))

    if not follow_ups:
        logger.info("No follow-ups due.")
        return report

    for follow_up in follow_ups:
        if dry_run:
            logger.info(
                "[dry-run] would send %s (%s) due %s",
                follow_up.id,
                follow_up.rule_code,
                follow_up.due_at,
            )
            continue

        # Built per follow-up rather than once for the run, because channel
        # preferences live on the workspace and each one may have chosen a
        # different set. An explicit service overrides this entirely, which is
        # what tests use to pin a single sender.
        worker = service or _service_for(db, follow_up)

        if worker is None:
            report.cancelled += 1
            logger.warning(
                "Follow-up %s has no workspace; cancelling.", follow_up.id
            )
            FollowUpService(db).cancel(follow_up, "The workspace no longer exists.")
            continue

        try:
            result = worker.send(follow_up)
        except FollowUpSendError as exc:
            # Left scheduled on purpose. A transient mail failure should be
            # retried by the next run, and marking it sent would lose the
            # message silently — which is the failure the sender interface was
            # designed to prevent.
            report.failed += 1
            report.errors.append(f"{follow_up.id} ({follow_up.rule_code}): {exc}")
            logger.error("Follow-up %s failed: %s", follow_up.id, exc)
            continue
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            db.rollback()
            report.failed += 1
            report.errors.append(f"{follow_up.id}: {type(exc).__name__}: {exc}")
            logger.exception("Follow-up %s raised", follow_up.id)
            continue

        # send() cancels rather than delivering when a rule no longer applies,
        # the workspace is gone, or there is no address. That is a correct
        # outcome, not a failure, and it is counted separately so a run that
        # cancelled everything is visible rather than looking like a quiet
        # success.
        if result.status == STATUS_SCHEDULED:
            report.failed += 1
            report.errors.append(f"{follow_up.id}: still scheduled after send")
        elif result.status == STATUS_SENT:
            report.sent += 1
        else:
            report.cancelled += 1

    logger.info("Follow-up run finished: %s", report.summary())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Send due follow-ups.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be sent without sending it.",
    )
    args = parser.parse_args()

    configure_logging()

    db = SessionLocal()
    try:
        report = run_due(db, dry_run=args.dry_run)
    finally:
        db.close()

    print(report.summary())

    for error in report.errors:
        print(f"  failed: {error}")

    # Non-zero on failure so cron surfaces a bad run instead of hiding it.
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
