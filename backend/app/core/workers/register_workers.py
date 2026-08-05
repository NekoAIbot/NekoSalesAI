from app.core.runtime import runtime

from app.core.workers.lead_conversion import LeadConversionWorker
from app.core.workers.customer_onboarding import CustomerOnboardingWorker
from app.core.workers.conversation_agent import ConversationAgentWorker
from app.core.workers.customer_review import CustomerReviewWorker
from app.core.workers.customer_success import CustomerSuccessWorker
from app.core.workers.customer_intelligence import CustomerIntelligenceWorker


def register_workers():

    runtime.register(
        "lead_conversion",
        LeadConversionWorker(),
    )

    runtime.register(
        "customer_onboarding",
        CustomerOnboardingWorker(),
    )

    runtime.register(
        "conversation_agent",
        ConversationAgentWorker(),
    )

    runtime.register(
        "customer_intelligence",
        CustomerIntelligenceWorker(),
    )

    runtime.register(
        "customer_review",
        CustomerReviewWorker(),
    )

    runtime.register(
        "customer_success",
        CustomerSuccessWorker(),
    )

    print("AI Workers Registered")
