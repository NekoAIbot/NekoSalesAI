with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "r") as f:
    content = f.read()

old1 = """def _role_for_order(order: Order) -> str:
    \"\"\"Which role to provision for a paid order.\"\"\"
    if order.plan_code:
        reference = reference_from_plan_code(order.plan_code)
        if reference and order.quote:
            try:
                requirement = requirement_from_json(order.quote.requirement_json)
                if requirement.products:
                    return PRODUCT_TYPE_TO_ROLE.get(
                        requirement.products[0], CATALOG_ROLE
                    )
            except Exception:
                pass
    return CATALOG_ROLE"""

new1 = """def _role_for_order(order: Order, db: Session) -> str:
    \"\"\"Which role to provision for a paid order.\"\"\"
    if order.plan_code:
        reference = reference_from_plan_code(order.plan_code)
        if reference:
            try:
                quote = QuoteService(db).get(reference)
                if quote:
                    requirement = requirement_from_json(quote.requirement_json)
                    if requirement.products:
                        return PRODUCT_TYPE_TO_ROLE.get(
                            requirement.products[0], CATALOG_ROLE
                        )
            except Exception:
                pass
    return CATALOG_ROLE"""

old2 = """    def _provision_for_role(
        self, order: Order, role: str
    ) -> tuple[ProvisionedAgent, ...]:
        \"\"\"Create workspace profiles for an order based on its quote.\"\"\"
        if not order.quote:
            return ()

        try:
            requirement = requirement_from_json(order.quote.requirement_json)
        except Exception:
            logger.error(
                "Order %s has an unreadable requirement", order.paystack_reference
            )
            return ()"""

new2 = """    def _provision_for_role(
        self, order: Order, role: str
    ) -> tuple[ProvisionedAgent, ...]:
        \"\"\"Create workspace profiles for an order based on its quote.\"\"\"
        requirement = None
        if order.plan_code:
            reference = reference_from_plan_code(order.plan_code)
            if reference:
                try:
                    quote = QuoteService(self.db).get(reference)
                    if quote:
                        requirement = requirement_from_json(quote.requirement_json)
                except Exception:
                    logger.error(
                        "Order %s has an unreadable requirement", order.paystack_reference
                    )

        if requirement is None:
            return ()"""

old3 = """        role = _role_for_order(order)
        agents = self._provision_for_role(order, role)"""

new3 = """        role = _role_for_order(order, self.db)
        agents = self._provision_for_role(order, role)"""

if old1 in content and old2 in content and old3 in content:
    content = content.replace(old1, new1)
    content = content.replace(old2, new2)
    content = content.replace(old3, new3)
    with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "w") as f:
        f.write(content)
    print("Patched provisioning.py")
else:
    if old1 not in content:
        print("old1 not found")
    if old2 not in content:
        print("old2 not found")
    if old3 not in content:
        print("old3 not found")
