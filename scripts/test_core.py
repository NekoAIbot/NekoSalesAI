"""Direct module tests for NekoSalesAI core logic."""
import sys
sys.path.insert(0, '/root/NekoSalesAI/backend')

from app.pricing.complexity import price, Requirement
from app.sales.advisor import recommend

results = []
def check(name, actual, expected):
    ok = actual == expected
    results.append((name, ok, actual, expected))
    status = "PASS" if ok else "FAIL"
    print(f"{status}: {name} - got {actual}, expected {expected}")

# Canonical pricing tests
r = Requirement(product_type="sales_agent", channels=["web"], monthly_conversations=500, integrations=[], languages=["en"])
check("Sales AI 500 conv", price(r).total_minor, 20150000)

r = Requirement(product_type="support_agent", channels=["web"], monthly_conversations=1000, integrations=["crm","calendar"], languages=["en"])
check("Support AI 1000 conv 2 integ", price(r).total_minor, 15800000)

r = Requirement(product_type="workforce_agent", channels=["web","telegram","whatsapp","email"], monthly_conversations=2450, integrations=["crm","calendar","payment","inventory","accounting"], languages=["en"])
check("Workforce 2450 conv 5 integ (en only)", price(r).total_minor, 38525000)

r = Requirement(product_type="sales_agent", channels=["web"], monthly_conversations=10000, integrations=[], languages=["en"])
check("Sales AI 10000 conv", price(r).total_minor, 24900000)

r = Requirement(product_type="workforce_agent", channels=["web","telegram","whatsapp","email"], monthly_conversations=2450, integrations=["crm","calendar","payment","inventory","accounting"], languages=["en","yo"])
check("Workforce 2450 conv 5 integ + yo", price(r).total_minor, 38875000)

r = Requirement(product_type="sales_agent", channels=["web"], monthly_conversations=450, integrations=[], languages=["en"])
check("Sales AI 450 conv", price(r).total_minor, 20125000)

r = Requirement(product_type="sales_agent", channels=["web"], monthly_conversations=3750, integrations=[], languages=["en"])
check("Sales AI 3750 conv", price(r).total_minor, 21775000)

passed = sum(1 for _, ok, _, _ in results if ok)
failed = len(results) - passed
print("\n" + str(passed) + "/" + str(len(results)) + " passed, " + str(failed) + " failed")

# Advisor tests
print("\nAdvisor tests:")
tests = [
    ("I run a clothing business", "sales_agent"),
    ("I need customer support for my online store", "support_agent"),
    ("I need both sales and support for my business", "workforce_agent"),
    ("We sell products on WhatsApp and need help with sales", "sales_agent"),
]
for msg, expected_product in tests:
    recs = recommend(msg)
    if recs:
        top = recs[0]
        name = top.get("name", top.get("product_type", "?"))
        ok = expected_product in str(top)
        status = "PASS" if ok else "FAIL"
        print("  " + status + ": " + msg[:50] + " -> " + name)
    else:
        print("  FAIL: " + msg[:50] + " -> no recommendations")

if failed > 0:
    sys.exit(1)
