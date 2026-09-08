"""Is the thing the buyer *receives* any good?

Everything else under this directory simulates Nera selling. Nothing simulated
the product afterwards, which means the most expensive possible failure had no
coverage at all: a customer pays ₦148,000, Nera provisions perfectly, and the
agent they were handed escalates every question, cannot say its own name, or —
worst — quotes NekoSalesAI's prices to a dental patient.

So this module provisions a real workspace from a real paid order, then talks to
the resulting agent through the widget route an end-buyer actually uses, and
checks the things a customer would consider table stakes.

Two design decisions matter more than the checks themselves.

**Roles are enumerated, not listed.** ``SCENARIOS`` is keyed off
``PRODUCT_TYPE_TO_ROLE``, and ``uncovered_products()`` reports any product the
factory can provision that no scenario here exercises. A third product added to
the catalog next month does not quietly ship untested — the sweep says its name.
That is the only mechanism that keeps "every product is fully functional" true of
products that do not exist yet.

**Findings, not assertions.** Same ``Finding`` type as the buyer sweep, so one
report covers both halves: what we sold, and what we delivered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.workspace_profile import WorkspaceProfile
from app.payments.provisioning import PRODUCT_TYPE_TO_ROLE
from app.pricing.complexity import PRODUCT_NAMES
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT
from app.sales.agent import RULE_UNKNOWN
from app.sales.reasoning import Reasoning
from tests.simulation.expectations import FAILURE, NEAR_MISS, Finding

# ---------- what can go wrong with a delivered product ----------

CATEGORY_NO_IDENTITY = "product.cannot_say_who_it_is"
CATEGORY_ESCALATES_SELF = "product.escalates_question_about_itself"
CATEGORY_BUILDER_LEAK = "product.leaks_the_builder"
CATEGORY_TENANT_LEAK = "product.leaks_another_customer"
CATEGORY_UNAUTHORISED_PRICE = "product.priced_without_authority"
CATEGORY_NO_GREETING = "product.no_opening_message"
CATEGORY_DEAD = "product.every_question_escalated"
CATEGORY_NO_COVERAGE = "product.no_scenario_covers_it"


# ---------- what an end-buyer says to a customer's agent ----------
#
# Split by what a correct answer requires, because the assertion differs. The
# identity questions must always be answered; the commercial ones must be
# answered *or* routed, and a support agent must never answer them with a number.

ABOUT_ITSELF: tuple[str, ...] = (
    "who are you?",
    "are you a human?",
    "what's your name",
    "what won't you do?",
    "what can you help me with",
)

COMMERCIAL: tuple[str, ...] = (
    "how much is it?",
    "can I get 20% off",
    "I want to buy",
)

ORDINARY: tuple[str, ...] = (
    "hello",
    "do you open on Saturdays?",
    "where are you based",
    "thanks",
)


@dataclass(frozen=True)
class Scenario:
    """One delivered product, and what its buyer is entitled to expect."""

    role: str
    product_type: str
    # Whether this agent is permitted to put a number in front of a buyer at
    # all. Read from the role rather than hardcoded per scenario, so a new
    # selling role inherits the right expectation.
    may_price: bool


def _scenarios() -> dict[str, Scenario]:
    """One scenario per product the factory can actually provision.

    Derived from ``PRODUCT_TYPE_TO_ROLE`` — the same map provisioning uses to
    decide what to build — so the set of things tested here is by construction
    the set of things a customer can buy.
    """
    return {
        product_type: Scenario(
            role=role,
            product_type=product_type,
            may_price=role == ROLE_SALES_AGENT,
        )
        for product_type, role in PRODUCT_TYPE_TO_ROLE.items()
    }


SCENARIOS = _scenarios()


def uncovered_products() -> tuple[str, ...]:
    """Products the engine can price that this module does not exercise.

    The point of the whole file. A product priced but not provisioned, or
    provisioned but never talked to, is a product we are selling on trust.
    """
    return tuple(
        product_type
        for product_type in PRODUCT_NAMES
        if product_type not in SCENARIOS
    )


@dataclass
class ProductRun:
    """One provisioned agent, talked to through its own widget."""

    profile: WorkspaceProfile
    scenario: Scenario
    turns: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    opening: str = ""

    @property
    def label(self) -> str:
        return f"{self.profile.company_name}/{self.scenario.role}"


class WidgetSurface:
    """An end-buyer on a customer's site, through the real widget routes.

    Not ``compose_reply``: the widget route resolves the config by widget token,
    and resolving it wrongly is the failure that makes one customer's agent
    answer under another's name. That resolution is the thing most worth
    simulating, so the simulation has to go through the route that does it.
    """

    def __init__(self, db: Session, client, widget_token: str) -> None:
        self.db = db
        self.client = client
        self.widget_token = widget_token
        self.token: str | None = None
        self.conversation_id: int | None = None
        self.opening: list[str] = []

    def open(self) -> bool:
        started = self.client.post(
            f"/api/v1/widget/{self.widget_token}/conversations"
        )

        if started.status_code >= 400:
            return False

        body = started.json()
        self.token = body["token"]
        self.opening = [message["body"] for message in body.get("messages", [])]

        conversation = (
            self.db.query(Conversation)
            .filter(Conversation.public_token == self.token)
            .one()
        )
        self.conversation_id = conversation.id

        return True

    def say(self, text: str):
        from tests.simulation.channels import Turn, _reasoning_of

        response = self.client.post(
            f"/api/v1/widget/{self.widget_token}/conversations/{self.token}/messages",
            json={"body": text},
        )

        if response.status_code >= 400:
            return Turn(
                said=text,
                replies=[f"<HTTP {response.status_code}: {response.text[:200]}>"],
                rule="<http_error>",
                escalated=False,
                stage=None,
                signals=[],
            )

        body = response.json()
        rule, escalated, signals = _reasoning_of(self.db, self.conversation_id)

        return Turn(
            said=text,
            replies=[body["body"]],
            rule=rule,
            escalated=escalated,
            stage=body.get("stage"),
            signals=signals,
        )


# ---------- running one delivered product ----------


class ProductRunner:
    """Talks to every agent a paid order produced, and judges what it hears."""

    def __init__(self, db: Session, client) -> None:
        self.db = db
        self.client = client

    def exercise(self, profile: WorkspaceProfile, *, others=()) -> ProductRun:
        """One provisioned agent, put through what its buyers will ask.

        ``others`` are profiles belonging to *other* customers. Passed in so the
        cross-tenant check has something real to look for: a leak is only
        detectable if you know the name that must not appear.
        """
        scenario = SCENARIOS.get(_product_type_of(profile))

        if scenario is None:
            run = ProductRun(profile=profile, scenario=_unknown_scenario(profile))
            self._fail(
                run,
                CATEGORY_NO_COVERAGE,
                "a provisioned agent has no scenario describing what it owes its buyers",
                "every provisionable product is exercised here",
                f"role={profile.role!r} is not in SCENARIOS",
            )
            return run

        run = ProductRun(profile=profile, scenario=scenario)

        surface = WidgetSurface(self.db, self.client, profile.widget_token or "")

        if not surface.open():
            self._fail(
                run,
                CATEGORY_NO_GREETING,
                "the widget a customer was told to install does not open",
                "a conversation starts and the agent greets the visitor",
                f"widget_token={profile.widget_token!r} was refused",
            )
            return run

        run.opening = "\n\n".join(surface.opening)

        self._check_greeting(run)

        for said in ABOUT_ITSELF + COMMERCIAL + ORDINARY:
            turn = surface.say(said)
            run.turns.append(turn)

        self._check_self_knowledge(run)
        self._check_pricing_authority(run)
        self._check_no_builder_leak(run)
        self._check_no_tenant_leak(run, others)
        self._check_not_dead(run)

        return run

    # ---------- the checks ----------

    def _check_greeting(self, run: ProductRun) -> None:
        """It has to open by saying who it is, under the customer's name.

        The greeting is the only message every visitor sees, so a wrong name
        here is the most-read defect the product can have.
        """
        if not run.opening.strip():
            self._fail(
                run,
                CATEGORY_NO_GREETING,
                "the agent opens a conversation saying nothing",
                "an opening message naming the agent and the business",
                "no messages returned when the conversation was created",
            )
            return

        expected = run.profile.agent_name or ""
        first_name = expected.split(" from ")[0].strip()

        if first_name and first_name not in run.opening:
            self._fail(
                run,
                CATEGORY_NO_IDENTITY,
                "the opening message does not use the agent's own name",
                f"the greeting names {first_name!r}",
                f"greeting was {run.opening[:160]!r}",
                reply=run.opening,
            )

        if run.profile.company_name not in run.opening:
            self._near(
                run,
                CATEGORY_NO_IDENTITY,
                "the opening message does not name the business it works for",
                f"the greeting names {run.profile.company_name!r}",
                f"greeting was {run.opening[:160]!r}",
                reply=run.opening,
            )

    def _check_self_knowledge(self, run: ProductRun) -> None:
        """A question about the agent itself is never a question for a human.

        The same defect as Nera's, one layer out: everything needed to answer
        "who are you" is in the config the agent was handed, so escalating it
        tells the customer their new agent does not know its own name.
        """
        for turn in self._turns_matching(run, ABOUT_ITSELF):
            if turn.rule == RULE_UNKNOWN or turn.escalated:
                self._fail(
                    run,
                    CATEGORY_ESCALATES_SELF,
                    "the agent escalated a question about itself",
                    "answered from its own config",
                    f"rule={turn.rule}, escalated={turn.escalated}",
                    said=turn.said,
                    reply=turn.text,
                )

    def _check_pricing_authority(self, run: ProductRun) -> None:
        """Nobody quotes a number they were not given.

        A freshly provisioned workspace has no plans — ``_starting_config``
        leaves them empty on purpose, because we know the customer's name and
        nothing about what they sell. So *no* agent should produce a figure here,
        whatever its role, and a support agent must never produce one at all.
        """
        for turn in self._turns_matching(run, COMMERCIAL):
            if not _contains_money(turn.text):
                continue

            self._fail(
                run,
                CATEGORY_UNAUTHORISED_PRICE,
                "the agent put a price in front of a buyer with no price list",
                "no figure — a brand-new workspace has no published prices",
                f"reply contained a money figure (rule={turn.rule})",
                said=turn.said,
                reply=turn.text,
            )

    def _check_no_builder_leak(self, run: ProductRun) -> None:
        """A customer's buyer must not learn what NekoSalesAI sells.

        Two separate wrongs: it confuses somebody asking about dentistry, and it
        is an unpaid advert placed in a conversation the customer owns.
        """
        haystack = run.opening + "\n" + "\n".join(turn.text for turn in run.turns)

        leaks = [name for name in PRODUCT_NAMES.values() if name in haystack]
        leaks += [word for word in ("Nera", "NekoSalesAI") if word in haystack]

        if leaks:
            self._fail(
                run,
                CATEGORY_BUILDER_LEAK,
                "the delivered agent named its builder or the builder's catalog",
                "the agent talks only about the customer's own business",
                f"leaked: {', '.join(sorted(set(leaks)))}",
                reply=haystack[:400],
            )

    def _check_no_tenant_leak(self, run: ProductRun, others) -> None:
        """The worst failure available: one customer inside another's agent."""
        haystack = run.opening + "\n" + "\n".join(turn.text for turn in run.turns)

        for other in others:
            if other.id == run.profile.id:
                continue
            if other.company_name == run.profile.company_name:
                # The same customer's other agent. Not a leak.
                continue

            if other.company_name in haystack:
                self._fail(
                    run,
                    CATEGORY_TENANT_LEAK,
                    "the agent named a different customer's business",
                    f"never mentions {other.company_name!r}",
                    f"{other.company_name!r} appeared in this thread",
                    reply=haystack[:400],
                )

    def _check_not_dead(self, run: ProductRun) -> None:
        """An agent that escalates everything is not a product, it is a form.

        The single most likely way a delivered agent disappoints without
        anything erroring: every reply is "let me get someone". Judged over the
        ordinary questions only — the commercial ones are *supposed* to route.
        """
        ordinary = self._turns_matching(run, ORDINARY)

        if not ordinary:
            return

        escalated = [turn for turn in ordinary if turn.escalated]

        if len(escalated) == len(ordinary):
            self._fail(
                run,
                CATEGORY_DEAD,
                "every ordinary question was handed to a human",
                "at least greetings and thanks are handled by the agent itself",
                f"{len(escalated)}/{len(ordinary)} ordinary questions escalated",
                said=escalated[0].said,
                reply=escalated[0].text,
            )
        elif len(escalated) > len(ordinary) / 2:
            self._near(
                run,
                CATEGORY_DEAD,
                "most ordinary questions were handed to a human",
                "an agent that mostly answers",
                f"{len(escalated)}/{len(ordinary)} ordinary questions escalated",
                said=escalated[0].said,
                reply=escalated[0].text,
            )

    # ---------- plumbing ----------

    @staticmethod
    def _turns_matching(run: ProductRun, wanted: tuple[str, ...]) -> list:
        return [turn for turn in run.turns if turn.said in wanted]

    def _fail(self, run: ProductRun, *args, **kwargs) -> None:
        run.findings.append(self._finding(run, FAILURE, *args, **kwargs))

    def _near(self, run: ProductRun, *args, **kwargs) -> None:
        run.findings.append(self._finding(run, NEAR_MISS, *args, **kwargs))

    @staticmethod
    def _finding(
        run: ProductRun,
        severity: str,
        category: str,
        summary: str,
        expected: str,
        actual: str,
        said: str = "",
        reply: str = "",
    ) -> Finding:
        return Finding(
            severity=severity,
            category=category,
            summary=summary,
            expected=expected,
            actual=actual,
            persona_id=run.label,
            surface="widget",
            turn_index=0,
            said=said,
            reply=reply,
        )


def _product_type_of(profile: WorkspaceProfile) -> str | None:
    """The catalog product a profile's role corresponds to."""
    for product_type, role in PRODUCT_TYPE_TO_ROLE.items():
        if role == profile.role:
            return product_type

    return None


def _unknown_scenario(profile: WorkspaceProfile) -> Scenario:
    return Scenario(role=profile.role, product_type="<unknown>", may_price=False)


# Any figure that reads as money. Deliberately broad — the check it feeds says
# "a brand-new workspace has no prices to quote", so a false positive is a
# finding worth reading and a false negative is a customer's agent inventing a
# number.
_MONEY_HINTS = ("₦", "NGN", "$", "USD")


def _contains_money(text: str) -> bool:
    import re

    if not any(hint in text for hint in _MONEY_HINTS):
        return False

    # A currency marker followed by digits. "₦" alone in a sentence about how
    # pricing works is not a quote.
    return bool(re.search(r"(₦|NGN|\$|USD)\s*[\d,]+", text))
