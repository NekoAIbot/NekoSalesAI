"""The post-sale follow-up loop.

Rule-based and dated. See ``app.followups.rules`` for the calendar itself.
"""

from app.followups.rules import RULES, RULES_BY_CODE, FollowUpContext, Rule
from app.followups.service import (
    Delivery,
    FollowUpSendError,
    FollowUpService,
    Sender,
    UnconfiguredSender,
)

__all__ = [
    "RULES",
    "RULES_BY_CODE",
    "Delivery",
    "FollowUpContext",
    "FollowUpSendError",
    "FollowUpService",
    "Rule",
    "Sender",
    "UnconfiguredSender",
]
