with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "r") as f:
    content = f.read()

old = """        if not order.plan_code:
            return CATALOG_ROLE"""

new = """        if not order.plan_code:
            return CATALOG_ROLE
        # DEBUG: log what we are looking for
        print(f"DEBUG plan_code: {order.plan_code!r}")"""

old2 = """        if reference:
            try:
                quote = QuoteService(db).get(reference)
                if quote:
                    requirement = requirement_from_json(quote.requirement_json)"""

new2 = """        if reference:
            try:
                quote = QuoteService(db).get(reference)
                print(f"DEBUG quote: {quote}")
                if quote:
                    print(f"DEBUG requirement_json: {quote.requirement_json!r}")
                    requirement = requirement_from_json(quote.requirement_json)"""

old3 = """        if not order.plan_code:
            return ()"""

new3 = """        print(f"DEBUG _provision_for_role plan_code: {order.plan_code!r}")
        if not order.plan_code:
            return ()"""

old4 = """        if reference:
                try:
                    quote = QuoteService(self.db).get(reference)
                    if quote:
                        requirement = requirement_from_json(quote.requirement_json)"""

new4 = """        if reference:
                try:
                    quote = QuoteService(self.db).get(reference)
                    print(f"DEBUG _provision_for_role quote: {quote}")
                    if quote:
                        print(f"DEBUG _provision_for_role requirement_json: {quote.requirement_json!r}")
                        requirement = requirement_from_json(quote.requirement_json)"""

content = content.replace(old, new)
content = content.replace(old2, new2)
content = content.replace(old3, new3)
content = content.replace(old4, new4)

with open("/root/NekoSalesAI/backend/app/payments/provisioning.py", "w") as f:
    f.write(content)
print("Added debug output")
