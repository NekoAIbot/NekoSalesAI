from app.core.brain import brain

brain.publish(
    stage="thinking",
    worker="customer_onboarding",
    customer_id=1,
    message="Analyzing customer profile...",
    confidence=0.91,
)

brain.publish(
    stage="decision",
    worker="customer_onboarding",
    customer_id=1,
    message="Customer qualifies for onboarding.",
    confidence=0.97,
)

print("Brain events saved successfully.")

