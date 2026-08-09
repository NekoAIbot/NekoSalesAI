"""Model registry.

Importing this module registers every model on Base.metadata. Alembic's env.py
imports it so autogenerate can see the full schema — a model that is not listed
here is invisible to migrations.
"""

from app.models.organization import Organization
from app.models.user import User
from app.models.customer import Customer
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.conversation import Conversation, Message
from app.models.approval_request import ApprovalRequest
from app.models.order import Order
from app.models.workspace_profile import WorkspaceProfile
from app.models.follow_up import FollowUp

__all__ = [
    "Organization",
    "User",
    "Customer",
    "Contact",
    "Lead",
    "Conversation",
    "Message",
    "ApprovalRequest",
    "Order",
    "WorkspaceProfile",
    "FollowUp",
]
