with open("/root/NekoSalesAI/backend/app/payments/checkout.py", "r") as f:
    content = f.read()

# Fix import
old_import = "from app.pricing.quotes import QuoteError, QuoteService, build_reference as build_quote_reference"
new_import = "from app.pricing.quotes import QuoteError, QuoteService, build_reference as build_quote_reference, _requirement_to_dict"

# Fix: use a separate quote reference, not the order reference
old_quote = """                    reference=reference,  # same reference as the order"""
new_quote = """                    reference=build_quote_reference(),"""

if old_import in content and old_quote in content:
    content = content.replace(old_import, new_import)
    content = content.replace(old_quote, new_quote)
    with open("/root/NekoSalesAI/backend/app/payments/checkout.py", "w") as f:
        f.write(content)
    print("Patched checkout.py")
else:
    if old_import not in content:
        print("old_import not found")
    if old_quote not in content:
        print("old_quote not found")
