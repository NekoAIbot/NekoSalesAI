"""Model registry.

Importing this module registers every model on Base.metadata. Alembic's env.py
imports it so autogenerate can see the full schema — a model that is not listed
here is invisible to migrations, which is how activity_events,
worker_executions and dead_letter_jobs ended up with no tables.
"""

from app.models.organization import Organization
from app.models.user import User
from app.models.customer import Customer
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.conversation import Conversation, Message
from app.models.approval_request import ApprovalRequest
from app.models.timeline_event import TimelineEvent
from app.models.customer_timeline import CustomerTimeline
from app.models.activity_event import ActivityEvent
from app.models.ai_memory import AIMemory
from app.models.ai_event import AIEvent
from app.models.ai_task import AITask
from app.models.ai_decision_log import AIDecisionLog
from app.models.ai_execution_queue import AIExecutionQueue
from app.models.ai_thought_log import AIThoughtLog
from app.models.mission_event import MissionEvent
from app.models.priority_score import PriorityScore
from app.models.worker_execution import WorkerExecution
from app.models.dead_letter_job import DeadLetterJob

__all__ = [
    "Organization",
    "User",
    "Customer",
    "Contact",
    "Lead",
    "Conversation",
    "Message",
    "ApprovalRequest",
    "TimelineEvent",
    "CustomerTimeline",
    "ActivityEvent",
    "AIMemory",
    "AIEvent",
    "AITask",
    "AIDecisionLog",
    "AIExecutionQueue",
    "AIThoughtLog",
    "MissionEvent",
    "PriorityScore",
    "WorkerExecution",
    "DeadLetterJob",
]
