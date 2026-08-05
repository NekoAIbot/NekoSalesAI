class SalesPriority:

    def calculate(self, customer):

        score = customer.opportunity_score

        if score >= 90:
            return "CRITICAL"

        if score >= 70:
            return "HIGH"

        if score >= 40:
            return "MEDIUM"

        return "LOW"


sales_priority = SalesPriority()
