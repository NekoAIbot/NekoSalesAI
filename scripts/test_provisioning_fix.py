import json
from app.database.database import SessionLocal
from app.models.order import Order, ORDER_PAID
from app.models.quote import Quote
from app.payments.provisioning import ProvisioningService, _role_for_order
from app.pricing.quotes import plan_code_for, build_reference
from app.pricing.complexity import Requirement, price

db = SessionLocal()
requirement = Requirement(
    product_type="sales_agent",
    products=("sales_agent",),
    channels=("web",),
    integrations=("crm",),
    languages=("en",),
    monthly_conversations=500,
)
computed = price(requirement)
quote = Quote(
    reference=build_reference(),
    requirement_json=json.dumps({
        "product_type": requirement.product_type,
        "products": list(requirement.products),
        "channels": list(requirement.channels),
        "integrations": list(requirement.integrations),
        "languages": list(requirement.languages),
        "monthly_conversations": requirement.monthly_conversations,
        "discount_percent": requirement.discount_percent,
    }),
    product_type=requirement.product_type,
    total_minor=computed.total_minor,
    currency=computed.currency,
)
db.add(quote)
db.commit()

order = Order(
    organization_id=1,
    paystack_reference="test_ref_001",
    plan_code=plan_code_for(quote.reference),
    plan_name="Sales AI",
    billing_period="month",
    amount_minor=computed.total_minor,
    currency="NGN",
    buyer_email="test@example.com",
    status=ORDER_PAID,
)
db.add(order)
db.commit()

role = _role_for_order(order, db)
print(f"Role: {role}")

result = ProvisioningService(db).provision(order)
print(f"Created: {result.created}")
print(f"Profiles: {len(result.profiles)}")
for p in result.profiles:
    print(f"  - {p.profile.role}: {p.profile.agent_name}")

db.close()
print("SUCCESS")
