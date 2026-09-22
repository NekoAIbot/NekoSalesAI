"""Buying, paying, and being told — the part where real money is involved.

The conversation simulation asks whether Nera talks sensibly. This asks the
harder question: when a buyer actually pays, does everything they paid for exist,
and do they find out on the channel they were sitting in?

That distinction is not academic. A real buyer paid ₦148,000 on Telegram and was
told nothing, and every test in the suite passed while it happened, because they
all asserted on database rows. Rows were fine. The buyer was not. So the checks
here end at the buyer's end of the wire: a message they can see, on the channel
they used, with the amount that actually left their account.

Four failure modes get their own checks because each one has either happened or
come close:

* **Charged a different number than you were quoted.** ``SimulatedPaystack``
  echoes back the amount it was initialized at, so a quote of ₦25,000 confirmed
  against ₦148,000 surfaces as a mismatch rather than agreeing by construction.
* **Half a purchase.** Two products bought, one provisioned. The delivery message
  names agents from the profile rows, so a missing profile reads as a shorter
  message rather than an error.
* **Told on the wrong channel, or not at all.** Derived from ``ChannelIdentity``,
  compared against the surface the buyer actually used.
* **Told forty times.** The status page polls and the reconciler runs on a timer,
  so "delivered twice" is the ordinary case, not the exotic one.

Everything runs offline against ``SimulatedPaystack``. Nothing here can move
money, and nothing here can reach the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.workspace_profile import WorkspaceProfile
from app.payments.checkout import CheckoutService
from app.payments.delivery import RULE_DELIVERED, DeliveryService, Push
from app.payments.paystack import PaystackClient
from app.sales.agent import RULE_PAYMENT_REPORTED, RULE_UNKNOWN
from tests.simulation.channels import build_surface
from tests.simulation.expectations import FAILURE, NEAR_MISS, Finding, Transcript
from tests.simulation.run import MAX_TURNS, run_one

# What a buyer types when they have paid and want to know it landed. Every one of
# these was said by a real buyer on Telegram, and "done" was answered as an
# unknown question and escalated to a human who had nothing to add.
PAID_PHRASINGS = (
    "I paid",
    "done",
    "confirmed",
    "i have paid now",
    "payment sent",
    "I've made the payment",
)

# The categories this module reports under, kept as constants so the report can
# group by them without matching on prose.
CATEGORY_LINK = "payment.no_link"
CATEGORY_AMOUNT = "payment.amount_mismatch"
CATEGORY_PROVISIONED = "provisioning.incomplete"
CATEGORY_DELIVERED = "delivery.buyer_not_told"
CATEGORY_CHANNEL = "delivery.wrong_channel"
CATEGORY_DUPLICATE = "delivery.told_twice"
CATEGORY_CREDENTIAL = "delivery.credential_in_chat"
CATEGORY_STATUS = "payment.status_check_escalated"
CATEGORY_CROSSED = "concurrency.buyers_crossed"


@dataclass
class Purchase:
    """One buyer's whole journey, from first message to being told."""

    persona: object
    surface: str
    transcript: Transcript | None = None
    order: Order | None = None
    profiles: list[WorkspaceProfile] = field(default_factory=list)
    pushes: list[Push] = field(default_factory=list)
    delivered_text: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def reached_payment(self) -> bool:
        return self.order is not None and bool(self.order.checkout_url)

    @property
    def completed(self) -> bool:
        """Paid, provisioned, and the buyer was told. The only success."""
        return (
            self.order is not None
            and self.order.is_paid
            and bool(self.profiles)
            and bool(self.delivered_text)
            and not any(f.severity == FAILURE for f in self.findings)
        )


def order_for(db: Session, conversation_id: int | None) -> Order | None:
    """The order raised in a conversation, whichever surface raised it.

    The single source of truth for all three surfaces: the chat platforms get a
    link pushed into the thread by ``ClosingService`` and the widget POSTs its buy
    panel to the checkout route, but both end up as a row pointing back here.
    """
    if conversation_id is None:
        return None

    return db.execute(
        select(Order)
        .where(Order.conversation_id == conversation_id)
        .order_by(Order.id.desc())
    ).scalars().first()


def quoted_total(transcript: Transcript) -> int | None:
    """The figure Nera put in front of the buyer, in minor units.

    Read out of the quote turn's text rather than from the database on purpose.
    What the buyer agreed to is what they *saw*; comparing the database against
    itself would pass even if the message showed a different number.
    """
    turn = transcript.quote_turn()

    if turn is None:
        return None

    # "AI Sales Representative — ₦25,000 per month" — the total is the first
    # naira figure on the headline line, which is the one a buyer reads as the
    # price. Line items come after it and are smaller by construction.
    for line in turn.text.splitlines():
        if "₦" not in line or line.strip().startswith("–"):
            continue

        digits = ""
        for character in line.split("₦", 1)[1]:
            if character.isdigit():
                digits += character
            elif character == ",":
                continue
            else:
                break

        if digits:
            return int(digits) * 100

    return None


class PurchaseRun:
    """Drives one buyer from first message to delivered, and judges the result."""

    def __init__(self, db: Session, client, paystack) -> None:
        self.db = db
        self.client = client
        self.paystack = paystack

    # ---------- the whole journey ----------

    def buy(self, persona, surface_name: str, *, pay: bool = True) -> Purchase:
        purchase = Purchase(persona=persona, surface=surface_name)

        surface = build_surface(
            surface_name,
            self.db,
            self.client,
            external_id=f"sim-{persona.persona_id}-{surface_name}",
        )

        purchase.transcript = run_one(
            persona, surface_name, self.db, self.client, max_turns=MAX_TURNS,
            surface=surface,
        )

        order = order_for(self.db, surface.conversation_id)

        # The widget has no link in chat: its buy panel is the payment path, and
        # it only appears once the conversation is genuinely ready. Trying it
        # unconditionally would manufacture orders for buyers who never agreed to
        # anything, so this only runs when the conversation got that far.
        if order is None and purchase.transcript.reached_quote():
            surface.checkout(persona)
            order = order_for(self.db, surface.conversation_id)

        purchase.order = order

        if order is None:
            if purchase.transcript.reached_quote():
                self._fail(
                    purchase,
                    CATEGORY_LINK,
                    "a buyer who agreed to a price could not reach a payment page",
                    "an order with a checkout URL",
                    "no order was raised in this conversation",
                )
            return purchase

        self._check_amount(purchase)

        if not pay:
            return purchase

        self._pay_and_deliver(purchase, surface)
        self._check_status_phrasing(purchase, surface)

        return purchase

    # ---------- the money ----------

    def _check_amount(self, purchase: Purchase) -> None:
        """Was Paystack asked for the number the buyer saw?

        This is the one check that cannot be satisfied by the system agreeing with
        itself: the figure comes out of the rendered message and the amount comes
        out of what the checkout put on the wire.
        """
        order = purchase.order
        shown = quoted_total(purchase.transcript)
        initialized = self.paystack.initialized.get(order.paystack_reference)

        if initialized is None:
            self._fail(
                purchase,
                CATEGORY_LINK,
                "an order exists that was never sent to Paystack",
                f"a transaction initialized for {order.paystack_reference}",
                "no initialize call was made for this reference",
            )
            return

        if initialized != order.amount_minor:
            self._fail(
                purchase,
                CATEGORY_AMOUNT,
                "the order and the payment request disagree on the amount",
                f"Paystack initialized at {order.amount_minor}",
                f"Paystack initialized at {initialized}",
            )

        if shown is not None and shown != order.amount_minor:
            self._fail(
                purchase,
                CATEGORY_AMOUNT,
                "the buyer was charged an amount other than the one quoted",
                f"charged {shown} — the total in the quote message",
                f"charged {order.amount_minor}",
            )

    def _pay_and_deliver(self, purchase: Purchase, surface) -> None:
        """Pay at Paystack, then let the reconciler notice, exactly as live.

        Deliberately not calling ``confirm_by_reference`` directly. There is no
        public HTTPS URL on this deployment so Paystack cannot call in, which
        makes the reconciler the only thing that ever notices a payment — and
        therefore the thing worth testing. A buyer taps the link, pays in another
        tab, and says nothing.
        """
        order = purchase.order
        self.paystack.mark_paid(order.paystack_reference)

        checkout = CheckoutService(
            self.db,
            client=PaystackClient(secret_key="sk_test_simulated", transport=self.paystack),
        )
        service = DeliveryService(self.db, checkout=checkout)

        report = service.reconcile()

        self.db.refresh(order)

        if not order.is_paid:
            self._fail(
                purchase,
                CATEGORY_DELIVERED,
                "a paid order was not recognised as paid",
                "the reconciler confirms the payment and provisions the workspace",
                f"the order is still {order.status}; errors: {report.errors}",
            )
            return

        purchase.profiles = service.profiles_for(order)
        purchase.pushes = [
            push
            for push in report.pushes
            if push.external_id == getattr(surface, "external_id", None)
            or surface.name == "web"
        ]

        self._check_provisioning(purchase)
        self._check_delivery(purchase, surface, report)
        self._check_told_once(purchase, service)

    # ---------- did they get what they bought ----------

    def _check_provisioning(self, purchase: Purchase) -> None:
        """One workspace profile per product bought. Not one per order."""
        expected = self._products_bought(purchase.order)
        built = {profile.role for profile in purchase.profiles}

        if not purchase.profiles:
            self._fail(
                purchase,
                CATEGORY_PROVISIONED,
                "money was taken and nothing was built",
                "a workspace profile for every product bought",
                "no workspace profile exists for this order",
            )
            return

        missing = expected - built

        if missing:
            self._fail(
                purchase,
                CATEGORY_PROVISIONED,
                "a multi-product purchase only provisioned part of itself",
                f"profiles for {sorted(expected)}",
                f"profiles for {sorted(built)}",
            )

    def _products_bought(self, order: Order) -> set:
        """The roles this order paid for, read back from the priced requirement.

        Products are translated into the roles provisioning builds — Workforce
        is one product that builds two agents — because that is what the
        profiles on the workspace are named by.
        """
        from app.models.quote import Quote
        from app.payments.provisioning import PRODUCT_TYPE_TO_ROLE
        from app.pricing.quotes import reference_from_plan_code, requirement_from_json

        reference = reference_from_plan_code(order.plan_code)

        if reference is None:
            return set()

        quote = self.db.execute(
            select(Quote).where(Quote.reference == reference)
        ).scalar_one_or_none()

        if quote is None:
            return set()

        requirement = requirement_from_json(quote.requirement_json)

        # The same translation the provisioner performs, so the check asks
        # "did they get the roles their products build" rather than comparing
        # product codes against role codes.
        products = tuple(getattr(requirement, "products", ()) or ())
        if not products:
            product = getattr(requirement, "product_type", None)
            products = (product,) if product else ()

        roles: set = set()
        for product in products:
            if product == "workforce_agent":
                roles.update(("sales_agent", "support_agent"))
            else:
                roles.add(PRODUCT_TYPE_TO_ROLE.get(product, "sales_agent"))

        return roles

    # ---------- did they find out ----------

    def _check_delivery(self, purchase: Purchase, surface, report) -> None:
        messages = self._delivery_messages(purchase.order.conversation_id)
        purchase.delivered_text = "\n\n".join(message.body for message in messages)

        if not messages:
            self._fail(
                purchase,
                CATEGORY_DELIVERED,
                "the buyer paid and was never told",
                "a delivery message in the thread they bought from",
                f"no delivery message; reconciler said {report.summary()}",
            )
            return

        if not purchase.delivered_text.startswith("Payment confirmed"):
            self._near(
                purchase,
                CATEGORY_DELIVERED,
                "the delivery does not open by confirming the payment",
                "the first line confirms the amount",
                purchase.delivered_text.splitlines()[0][:120],
            )

        self._check_channel(purchase, surface, report)
        self._check_no_credentials(purchase)

    def _check_channel(self, purchase: Purchase, surface, report) -> None:
        """Told where they were standing.

        A web buyer reads the thread, so the transcript row *is* the delivery and
        no push is owed. A chat buyer is not holding a connection open, so a push
        is the only thing that reaches them.
        """
        if surface.name == "web":
            if report.pushes:
                self._near(
                    purchase,
                    CATEGORY_CHANNEL,
                    "a web purchase produced a chat push",
                    "no push: the transcript row is the delivery",
                    f"pushed to {sorted({p.channel for p in report.pushes})}",
                )
            return

        channels = {push.channel for push in purchase.pushes}

        if not purchase.pushes:
            self._fail(
                purchase,
                CATEGORY_CHANNEL,
                "a chat buyer got no message on the channel they bought from",
                f"a push on {surface.name}",
                "the delivery was written to the transcript and never sent",
            )
            return

        if channels != {surface.name}:
            self._fail(
                purchase,
                CATEGORY_CHANNEL,
                "the buyer was told on a different channel than they bought from",
                f"a push on {surface.name} only",
                f"pushed to {sorted(channels)}",
            )

        for push in purchase.pushes:
            if push.external_id != surface.external_id:
                self._fail(
                    purchase,
                    CATEGORY_CROSSED,
                    "one buyer's confirmation was addressed to another buyer",
                    f"every push addressed to {surface.external_id}",
                    f"a push addressed to {push.external_id}",
                )

    def _check_no_credentials(self, purchase: Purchase) -> None:
        """A chat log is forwarded and screenshotted; a posted key cannot be unposted."""
        text = purchase.delivered_text

        for profile in purchase.profiles:
            prefix = profile.api_key_prefix or ""

            # The prefix is a deliberate hint and is safe. A full key is not, and
            # the only way to tell them apart here is length.
            if prefix and len(prefix) > 12 and prefix in text:
                self._fail(
                    purchase,
                    CATEGORY_CREDENTIAL,
                    "a credential was put into the chat thread",
                    "the message says where the credentials are, not what they are",
                    f"the thread contains {prefix[:8]}…",
                )

    def _check_told_once(self, purchase: Purchase, service: DeliveryService) -> None:
        """The status page polls and the reconciler runs on a timer."""
        before = purchase.delivered_text.count("Payment confirmed")

        service.reconcile(verify_pending=False)
        service.reconcile(verify_pending=False)

        after = "\n\n".join(
            message.body
            for message in self._delivery_messages(purchase.order.conversation_id)
        ).count("Payment confirmed")

        if after != before:
            self._fail(
                purchase,
                CATEGORY_DUPLICATE,
                "a further reconcile pass told the buyer again",
                f"{before} confirmation after three passes",
                f"{after} confirmations",
            )

    # ---------- "I paid" ----------

    def _check_status_phrasing(self, purchase: Purchase, surface) -> None:
        """Reporting a payment is a status check, not an unknown question.

        A buyer who says "done" is asking whether their money arrived. Escalating
        that fetches a human who can only repeat what the system already knows,
        and it teaches the buyer that this channel does not work.
        """
        said = PAID_PHRASINGS[hash(purchase.persona.persona_id) % len(PAID_PHRASINGS)]
        turn = surface.say(said)

        if turn.rule == RULE_UNKNOWN or (
            turn.escalated and turn.rule != RULE_PAYMENT_REPORTED
        ):
            self._fail(
                purchase,
                CATEGORY_STATUS,
                "a buyer reporting their payment was escalated to a human",
                f"{RULE_PAYMENT_REPORTED}: a status check answered from what is known",
                f"{turn.rule}, escalated={turn.escalated}",
                said=said,
                reply=turn.text,
            )

    # ---------- plumbing ----------

    def _delivery_messages(self, conversation_id: int | None) -> list:
        from app.models.conversation import Message

        if conversation_id is None:
            return []

        return [
            message
            for message in self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id)
            .all()
            if RULE_DELIVERED in (message.reasoning_json or "")
        ]

    def _fail(self, purchase, category, summary, expected, actual, **extra) -> None:
        purchase.findings.append(
            self._finding(FAILURE, purchase, category, summary, expected, actual, **extra)
        )

    def _near(self, purchase, category, summary, expected, actual, **extra) -> None:
        purchase.findings.append(
            self._finding(NEAR_MISS, purchase, category, summary, expected, actual, **extra)
        )

    @staticmethod
    def _finding(
        severity, purchase, category, summary, expected, actual, said="", reply=""
    ) -> Finding:
        return Finding(
            severity=severity,
            category=category,
            persona_id=purchase.persona.persona_id,
            surface=purchase.surface,
            summary=summary,
            expected=expected,
            actual=actual,
            said=said,
            reply=reply[:600],
        )


def buy_concurrently(
    db: Session,
    client,
    paystack,
    personas: list,
    surface_name: str,
) -> list[Purchase]:
    """Several buyers mid-purchase at once, then one reconcile pass for all.

    This is the real shape of the race, and it is not hypothetical: the poller
    reconciles on a timer, so every buyer who paid since the last cycle is
    provisioned and delivered inside one pass. The failure being watched for is
    one buyer's confirmation going to another buyer's chat, or two buyers landing
    in one workspace.
    """
    run = PurchaseRun(db, client, paystack)
    purchases: list[Purchase] = []
    surfaces = {}

    # Everyone reaches a payment page first, nobody pays yet.
    for persona in personas:
        purchase = run.buy(persona, surface_name, pay=False)
        purchases.append(purchase)

        if purchase.order is not None:
            paystack.mark_paid(purchase.order.paystack_reference)
            surfaces[purchase.persona.persona_id] = purchase

    checkout = CheckoutService(
        db, client=PaystackClient(secret_key="sk_test_simulated", transport=paystack)
    )
    report = DeliveryService(db, checkout=checkout).reconcile()

    service = DeliveryService(db)

    for purchase in purchases:
        if purchase.order is None:
            continue

        db.refresh(purchase.order)
        purchase.profiles = service.profiles_for(purchase.order)
        purchase.pushes = [
            push
            for push in report.pushes
            if push.external_id == f"sim-{purchase.persona.persona_id}-{surface_name}"
        ]
        purchase.delivered_text = "\n\n".join(
            message.body
            for message in run._delivery_messages(purchase.order.conversation_id)
        )

        run._check_provisioning(purchase)

        # Every buyer must own their workspace alone. Two buyers sharing one is
        # the concurrency failure that matters, because it hands one customer
        # another customer's agent.
        for profile in purchase.profiles:
            if profile.order_id != purchase.order.id:
                run._fail(
                    purchase,
                    CATEGORY_CROSSED,
                    "a workspace was attached to the wrong buyer's order",
                    f"every profile belongs to order {purchase.order.id}",
                    f"a profile belongs to order {profile.order_id}",
                )

        if purchase.persona.email and purchase.delivered_text:
            if purchase.persona.email not in purchase.delivered_text:
                run._fail(
                    purchase,
                    CATEGORY_CROSSED,
                    "a buyer's confirmation names somebody else's email",
                    f"the sign-in line names {purchase.persona.email}",
                    "it names a different address",
                )

    return purchases
