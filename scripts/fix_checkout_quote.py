with open("/root/NekoSalesAI/backend/app/payments/checkout.py", "r") as f:
    content = f.read()

# After the order is created and before checkout.initialize, create a Quote row
# when builder_requirement was used, so provisioning can find it.
old = """        # Persist the builder configuration hash for reusable-checkout lookup.
        if builder_requirement is not None:
            order.builder_config_hash = _config_hash(builder_requirement)
            self._store_builder_configuration(builder_requirement, order)

        checkout = self.client.initialize("""

new = """        # Persist the builder configuration hash for reusable-checkout lookup.
        if builder_requirement is not None:
            order.builder_config_hash = _config_hash(builder_requirement)
            self._store_builder_configuration(builder_requirement, order)
            # Also create a Quote row so provisioning can look up the requirement.
            try:
                requirement = _builder_to_requirement(builder_requirement)
                computed = price(requirement)
                quote = Quote(
                    reference=reference,  # same reference as the order
                    organization_id=organization_id,
                    conversation_id=conversation.id if conversation else None,
                    requirement_json=json.dumps(_requirement_to_dict(requirement)),
                    product_type=requirement.product_type,
                    total_minor=computed.total_minor,
                    currency=computed.currency,
                )
                self.db.add(quote)
            except Exception:
                logger.warning(
                    "Order %s: could not persist quote for builder configuration",
                    reference,
                )

        checkout = self.client.initialize("""

if old in content:
    content = content.replace(old, new)
    with open("/root/NekoSalesAI/backend/app/payments/checkout.py", "w") as f:
        f.write(content)
    print("Patched checkout.py")
else:
    print("Pattern not found")
