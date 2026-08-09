"""Why the agent said what it said.

Every agent reply carries a Reasoning record: the signals it read in the
visitor's message, the rule that fired, and the exact catalog entries it drew
the answer from. Two things fall out of that.

First, a reply that cites no catalog entry is a reply making an unsourced
claim, and the agent's own tests assert that does not happen. Second, when a
buyer later says "your bot told me X", there is a record of what it said and
on what basis.

Note what is deliberately absent: a confidence number. A percentage that is
not measured against outcomes is a fabricated statistic dressed up as a
measurement, and the honest alternative is to publish the signals and let a
human judge them.
"""

import json
from dataclasses import dataclass, field


@dataclass
class Reasoning:
    """The audit trail for one agent turn."""

    # Short machine-readable name of the rule that produced the reply, e.g.
    # "pricing_question" or "off_script_discount_request".
    rule: str

    # Human-readable observations from the visitor's message that led here,
    # e.g. "asked about price", "named the Growth plan".
    signals: list[str] = field(default_factory=list)

    # Catalog entries the answer was built from, as stable references:
    # "plan:growth_monthly", "capability:app.sales.agent", "faq:2".
    # Empty means the reply asserted nothing about the product.
    grounded_in: list[str] = field(default_factory=list)

    # True when the turn was routed to a human instead of answered outright.
    escalated: bool = False

    def add_signal(self, signal: str) -> None:
        if signal not in self.signals:
            self.signals.append(signal)

    def cite(self, reference: str) -> None:
        if reference not in self.grounded_in:
            self.grounded_in.append(reference)

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "signals": list(self.signals),
            "grounded_in": list(self.grounded_in),
            "escalated": self.escalated,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str | None) -> "Reasoning | None":
        """Parse a stored trail. Returns None rather than raising on junk.

        Reasoning is an explanation of a reply, not the reply itself. A row
        written by an older version of this code should degrade to "no
        explanation available" and never take down the thread it explains.
        """
        if not raw:
            return None

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict) or "rule" not in data:
            return None

        signals = data.get("signals") or []
        grounded_in = data.get("grounded_in") or []

        return cls(
            rule=str(data["rule"]),
            signals=[str(s) for s in signals] if isinstance(signals, list) else [],
            grounded_in=(
                [str(g) for g in grounded_in]
                if isinstance(grounded_in, list)
                else []
            ),
            escalated=bool(data.get("escalated", False)),
        )


def plan_reference(code: str) -> str:
    return f"plan:{code}"


def capability_reference(verified_by: str) -> str:
    """Cite a capability backed by code in this repo.

    The reference is the module path, so a reader of the trail can go and look
    at the implementation.
    """
    return f"capability:{verified_by}"


def declared_capability_reference(index: int) -> str:
    """Cite a capability the customer asserted during requirements intake.

    Deliberately a different prefix from ``capability:``. A trail that showed
    both kinds identically would let an unverified claim borrow the
    credibility of a verified one, which is the exact confusion the source
    field on ``Capability`` exists to prevent. Indexed rather than named,
    because there is no module to point at.
    """
    return f"declared:{index}"


def faq_reference(index: int) -> str:
    return f"faq:{index}"


def knowledge_reference(index: int) -> str:
    """Cite a business fact the customer supplied — hours, policies, process."""
    return f"knowledge:{index}"
