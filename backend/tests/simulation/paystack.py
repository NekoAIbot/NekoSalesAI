"""Paystack, offline, but not lenient.

The shared ``FakeTransport`` in ``tests.test_checkout`` verifies at a fixed
amount, which is fine for one hand-built order and wrong here: a thousand
dynamically-priced builds all have different totals, and a verifier that always
agrees would hide the one failure mode that costs real money — an order confirmed
at an amount nobody was charged.

So this records what it was asked to initialize and echoes *that* back on verify.
If the checkout sends ₦25,000 and confirms against ₦148,000, this notices.

It also keeps the suite off the network. The first smoke run reached Paystack for
real over TLS and timed out, which took the whole reply down with it — a useful
thing to have learned, and not something to do a thousand times.
"""

from dataclasses import dataclass, field


@dataclass
class SimulatedPaystack:
    """An in-process Paystack that remembers amounts per reference."""

    # Every reference is unpaid until told otherwise, because that is the state a
    # real checkout starts in and the "buyer never paid" branches have to be
    # reachable.
    pay_everything: bool = False

    initialized: dict[str, int] = field(default_factory=dict)
    paid: set = field(default_factory=set)
    requests: list = field(default_factory=list)
    currency: str = "NGN"
    fail_initialize: bool = False
    fail_verify: bool = False

    def mark_paid(self, reference: str) -> None:
        self.paid.add(reference)

    def request(self, method, url, *, headers, json_body=None):
        self.requests.append(
            {"method": method, "url": url, "body": json_body}
        )

        if "/transaction/initialize" in url:
            return self._initialize(json_body or {})

        if "/transaction/verify/" in url:
            return self._verify(url.rsplit("/", 1)[-1])

        return 404, {"status": False, "message": f"unstubbed {url}"}

    def _initialize(self, body: dict):
        if self.fail_initialize:
            return 400, {"status": False, "message": "Invalid amount"}

        reference = body.get("reference", "ref_unknown")
        self.initialized[reference] = int(body.get("amount") or 0)

        return 200, {
            "status": True,
            "data": {
                "authorization_url": f"https://checkout.paystack.com/{reference}",
                "access_code": f"acc_{reference}",
                "reference": reference,
            },
        }

    def _verify(self, reference: str):
        if self.fail_verify:
            return 502, {"status": False, "message": "Paystack is unwell"}

        settled = self.pay_everything or reference in self.paid

        return 200, {
            "status": True,
            "data": {
                "reference": reference,
                "status": "success" if settled else "abandoned",
                # The amount this reference was actually initialized at, so a
                # mismatch between what was quoted and what was confirmed shows
                # up as a mismatch instead of agreeing by construction.
                "amount": self.initialized.get(reference, 0),
                "currency": self.currency,
                "customer": {"email": "buyer@example.com"},
                "paid_at": "2026-08-25T05:47:00.000Z",
            },
        }


def install(monkeypatch, paystack: SimulatedPaystack) -> SimulatedPaystack:
    """Make every ``PaystackClient`` in the process use this one.

    Patched at ``HttpxTransport`` rather than at each call site because several
    paths — ``ClosingService`` reaching for its own ``CheckoutService``, the
    reconciler, the checkout route — construct a client with no injection point.
    Patching the default transport catches all of them, including the one added
    next month that forgets to accept an injected client.
    """
    monkeypatch.setattr(
        "app.payments.paystack.HttpxTransport",
        lambda *args, **kwargs: paystack,
    )

    return paystack
