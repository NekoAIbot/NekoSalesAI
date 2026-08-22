"""Delivering follow-ups through the mail transport.

``FollowUpService`` was written against a ``Sender`` protocol with a deliberately
honest placeholder: ``UnconfiguredSender`` raises rather than pretending, because
a sender that silently discarded messages would let the desk mark follow-ups as
sent that no customer ever received. This is the real implementation that
placeholder was waiting for.

Thin on purpose. Everything that decides *whether* a follow-up is still
warranted, and *what* it says, already lives in ``FollowUpService.send`` and the
rules — this only carries the result to the transport.
"""

from __future__ import annotations

from app import mail
from app.followups.service import Delivery, FollowUpSendError


class MailSender:
    """Sends a follow-up as email.

    Raises ``FollowUpSendError`` on failure rather than returning quietly. The
    caller uses the exception to decide whether the follow-up stays scheduled, so
    swallowing it here would mark an undelivered message as sent — the exact
    failure ``UnconfiguredSender`` exists to avoid.
    """

    def send(self, delivery: Delivery) -> None:
        outcome = mail.send(
            mail.follow_up(
                to=delivery.to_email,
                subject=delivery.subject,
                body=delivery.body,
            )
        )

        if not outcome.sent:
            raise FollowUpSendError(
                f"Could not send via {outcome.backend}: {outcome.error}"
            )
