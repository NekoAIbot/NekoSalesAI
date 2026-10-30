"""Entitlements: what an organization bought decides what Zuri unlocks.

Zuri is included free with every purchase. What she is allowed to report,
coordinate and advise on depends on the paid orders on record for the
organization. A locked capability is named honestly with what unlocks it;
Zuri never pretends to have access she does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import ORDER_PAID, Order
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT


@dataclass
class Entitlements:
    organization_id: int
    has_any_purchase: bool = False
    has_sales: bool = False
    has_support: bool = False
    has_workforce: bool = False
    active_plans: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.has_workforce or (self.has_sales and self.has_support):
            return "Workforce (sales + support active)"
        if self.has_sales:
            return "AI Sales Agent active"
        if self.has_support:
            return "AI Support Agent active"
        if self.has_any_purchase:
            return "Basic plan active"
        return "No active purchases on record"


def for_organization(db: Session, organization_id: int) -> Entitlements:
    orders = list(
        db.execute(
            select(Order)
            .where(
                Order.organization_id == organization_id,
                Order.status == ORDER_PAID,
            )
        ).scalars().all()
    )

    plans = {o.plan_code for o in orders if o.plan_code}

    has_workforce = "workforce_agent" in plans or "workforce" in plans
    has_sales = has_workforce or "sales_agent" in plans or "sales" in plans
    has_support = has_workforce or "support_agent" in plans or "support" in plans

    return Entitlements(
        organization_id=organization_id,
        has_any_purchase=bool(orders),
        has_sales=has_sales,
        has_support=has_support,
        has_workforce=has_workforce,
        active_plans=sorted(plans),
    )
