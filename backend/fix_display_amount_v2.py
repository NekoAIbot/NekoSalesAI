# Fix checkout.py list_orders to compute display_amount inline

with open("app/api/v1/routes/checkout.py", "r") as f:
    content = f.read()

# Check if the fix is still in place
if '"display_amount": o.display_amount' in content:
    content = content.replace(
        '"display_amount": o.display_amount,',
        '"display_amount": f"₦{o.amount_minor / 100:,.0f}" if o.amount_minor else None,'
    )
    with open("app/api/v1/routes/checkout.py", "w") as f:
        f.write(content)
    print("Fixed display_amount in list_orders")
else:
    print("display_amount already fixed or pattern not found")
