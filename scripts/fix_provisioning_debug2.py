with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "r") as f:
    content = f.read()

# Add traceback to see the actual error
old = """                except Exception:
                    logger.error(
                        \"Order %s has an unreadable requirement\", order.paystack_reference
                    )"""

new = """                except Exception as e:
                    import traceback
                    logger.error(
                        \"Order %s has an unreadable requirement: %s\", order.paystack_reference, e
                    )
                    traceback.print_exc()"""

content = content.replace(old, new)

# Also log when _provision_for_role is called
old2 = """    def _provision_for_role(
        self, order: Order, role: str
    ) -> tuple[ProvisionedAgent, ...]:
        \"\"\"Create workspace profiles for an order based on its quote.\"\"\"
        requirement = None
        if order.plan_code:"""

new2 = """    def _provision_for_role(
        self, order: Order, role: str
    ) -> tuple[ProvisionedAgent, ...]:
        \"\"\"Create workspace profiles for an order based on its quote.\"\"\"
        import sys
        sys.stderr.write(f\"PROVISION_CALLED plan_code={order.plan_code!r} role={role!r}\\n\")
        sys.stderr.flush()
        requirement = None
        if order.plan_code:"""

content = content.replace(old2, new2)

with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "w") as f:
    f.write(content)
print("Added traceback debug")
