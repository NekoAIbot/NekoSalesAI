with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "r") as f:
    content = f.read()

old = "from app.pricing.quotes import reference_from_plan_code, requirement_from_json"
new = "from app.pricing.quotes import QuoteService, reference_from_plan_code, requirement_from_json"

if old in content:
    content = content.replace(old, new)
    with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "w") as f:
        f.write(content)
    print("Fixed QuoteService import")
else:
    print("Import line not found")
