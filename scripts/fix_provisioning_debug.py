with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "r") as f:
    content = f.read()

# Replace print with sys.stderr.write for pytest visibility
content = content.replace("print(f\"DEBUG quote: {quote}\")", "import sys; sys.stderr.write(f\"DEBUG quote: {quote}\\n\")")
content = content.replace("print(f\"DEBUG requirement_json: {quote.requirement_json!r}\")", "import sys; sys.stderr.write(f\"DEBUG requirement_json: {quote.requirement_json!r}\\n\")")
content = content.replace("print(f\"DEBUG _provision_for_role quote: {quote}\")", "import sys; sys.stderr.write(f\"DEBUG _provision_for_role quote: {quote}\\n\")")
content = content.replace("print(f\"DEBUG _provision_for_role requirement_json: {quote.requirement_json!r}\")", "import sys; sys.stderr.write(f\"DEBUG _provision_for_role requirement_json: {quote.requirement_json!r}\\n\")")
content = content.replace("print(f\"DEBUG plan_code: {order.plan_code!r}\")", "import sys; sys.stderr.write(f\"DEBUG plan_code: {order.plan_code!r}\\n\")")
content = content.replace("print(f\"DEBUG _provision_for_role plan_code: {order.plan_code!r}\")", "import sys; sys.stderr.write(f\"DEBUG _provision_for_role plan_code: {order.plan_code!r}\\n\")")

with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "w") as f:
    f.write(content)
print("Switched to stderr debug")
