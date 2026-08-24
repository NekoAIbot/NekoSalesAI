"""The three reported bugs, re-tested against the running deployment.

Not a unit test. The suite already covers all three at the ``compose_reply``
level, and it passed while the live bot was serving a withdrawn price — which is
exactly the gap this script exists to close. It talks HTTP to whatever is actually
listening on the port, so it exercises the deployed process, its imports, its
database and its config, and it is the only check here that would have caught the
original failure.

    .venv/bin/python scripts/verify_bugfixes.py
    .venv/bin/python scripts/verify_bugfixes.py --base http://127.0.0.1:8000
    .venv/bin/python scripts/verify_bugfixes.py --web-only

Both surfaces, because "they share a backend so fixing one fixes both" is a
hypothesis and this is the thing that tests it. The web half goes over HTTP. The
Telegram half goes through ``InboundMessagingService.handle``, which is the
function the poller calls: it decides what to say and sends nothing, so this
cannot message a real buyer. Its threads are keyed ``verify:<token>`` and deleted
afterwards, following the convention ``stress_nera.py`` already established.

Every conversation is started fresh, because all three bugs are about what Nera
does with no prior context — a reused thread would carry a scope and hide the
behaviour being checked.

Exit code is 0 only if every flow passes on every surface. Anything else means do
not deploy.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_BASE = "http://127.0.0.1:8000"
API = "/api/v1/sales"
TIMEOUT = 30.0

# BUG 2's exact shape: the withdrawn flat tier, in every form it could surface.
WITHDRAWN = ("180,000", "180000", "Founding User", "founding_annual")

# What a real close asks for. Used to detect a premature one.
PAYMENT_TELLS = (
    "name, email and company",
    "raise the payment",
    "payment link",
    "checkout",
)

MONEY = re.compile(r"₦\s?[\d,]+")


class Failure(Exception):
    """A flow behaved the way the bug report described."""


class Client:
    """One buyer, one fresh thread."""

    def __init__(self, base: str):
        self._http = httpx.Client(base_url=base, timeout=TIMEOUT)
        self.token: str | None = None
        self.turns: list[tuple[str, str]] = []
        self.last: dict = {}

    def start(self) -> None:
        response = self._http.post(f"{API}/conversations")
        response.raise_for_status()
        self.token = response.json()["token"]

    def say(self, text: str) -> str:
        response = self._http.post(
            f"{API}/conversations/{self.token}/messages", json={"body": text}
        )
        response.raise_for_status()

        self.last = response.json()
        body = self.last["body"]
        self.turns.append((text, body))

        return body

    @property
    def rule(self) -> str:
        """Which rule produced the last reply.

        Checked in preference to the prose wherever a check has a structural
        equivalent. Copy is meant to be rewritten — a control that matched the
        refusal wording failed here the moment the wording said "rather than
        guess" instead of "rather not guess", reporting a bug in a reply that was
        entirely correct. A rule name is the engine's own account of what it did.
        """
        return ((self.last.get("reasoning") or {}).get("rule")) or ""

    @property
    def escalated(self) -> bool:
        return bool((self.last.get("reasoning") or {}).get("escalated"))

    @property
    def interested_plan_code(self) -> str | None:
        """What the thread thinks the buyer settled on, read back from the API."""
        thread = self._http.get(f"{API}/conversations/{self.token}")
        thread.raise_for_status()

        return thread.json().get("interested_plan_code")

    def transcript(self) -> str:
        return "\n\n".join(
            f"  buyer> {said}\n  nera > {heard}" for said, heard in self.turns
        )

    def close(self) -> None:
        self._http.close()


class TelegramBuyer:
    """The same six checks, arriving the way a Telegram buyer arrives.

    Deliberately the same interface as ``Client`` so the checks below are written
    once and run twice. What differs is everything underneath: a channel identity,
    a greeting on first contact, the command handling, and ``ClosingService``
    wired in — which the web route does not use. A bug living in that wiring would
    be invisible to the HTTP half.

    ``handle`` returns the replies rather than sending them, so nothing here
    reaches Telegram. The bot token is never touched.
    """

    def __init__(self, run_token: str, name: str):
        from app.database.session import SessionLocal
        from app.messaging.service import (
            InboundMessagingService,
            storefront_organization_id,
        )

        self._db = SessionLocal()
        self._service = InboundMessagingService(self._db)
        self._organization_id = storefront_organization_id(self._db)

        if self._organization_id is None:
            raise Failure(
                "No storefront organization in this database — seed it first."
            )

        self.external_id = f"verify:{run_token}:{name}"
        self._counter = 0
        self.turns: list[tuple[str, str]] = []
        self.last_reply = ""

    def start(self) -> None:
        # First contact is the message itself; the greeting comes back with it.
        # Nothing to do here, but the web client needs the call, so both surfaces
        # keep one shape.
        return None

    def say(self, text: str) -> str:
        from app.messaging.inbound import KIND_TEXT, InboundMessage
        from app.models.channel_identity import CHANNEL_TELEGRAM

        self._counter += 1

        handled = self._service.handle(
            self._organization_id,
            InboundMessage(
                channel=CHANNEL_TELEGRAM,
                external_id=self.external_id,
                delivery_id=f"{self.external_id}:{self._counter}",
                kind=KIND_TEXT,
                text=text,
                sender_name="Verification",
            ),
        )

        # A turn can be several messages — a greeting then an answer. The buyer
        # reads them as one thing, so they are checked as one thing.
        self.last_reply = "\n\n".join(handled.replies)
        self._conversation = handled.conversation
        self.turns.append((text, self.last_reply))

        return self.last_reply

    @property
    def _reasoning(self) -> dict:
        """The trail on the last agent message in the thread.

        Read from the database because ``handle`` returns prose, not reasoning.
        This is the same row the web API serialises, so both surfaces are judged
        against the same structure.
        """
        import json

        from app.models.conversation import ROLE_AGENT, Message

        if self._conversation is None:
            return {}

        row = (
            self._db.query(Message)
            .filter(
                Message.conversation_id == self._conversation.id,
                Message.role == ROLE_AGENT,
            )
            .order_by(Message.id.desc())
            .first()
        )

        if row is None or not row.reasoning_json:
            return {}

        try:
            return json.loads(row.reasoning_json)
        except (ValueError, TypeError):
            return {}

    @property
    def rule(self) -> str:
        return self._reasoning.get("rule") or ""

    @property
    def escalated(self) -> bool:
        return bool(self._reasoning.get("escalated"))

    @property
    def interested_plan_code(self) -> str | None:
        if self._conversation is None:
            return None

        self._db.refresh(self._conversation)

        return self._conversation.interested_plan_code

    def transcript(self) -> str:
        return "\n\n".join(
            f"  buyer> {said}\n  nera > {heard}" for said, heard in self.turns
        )

    def close(self) -> None:
        """Remove the thread this check created.

        A verification run that leaves rows behind would slowly fill the same
        tables the sales desk reads, and a synthetic buyer in that list is worse
        than no data: someone follows it up.
        """
        from app.models.channel_identity import ChannelIdentity
        from app.models.conversation import Message

        try:
            identity = (
                self._db.query(ChannelIdentity)
                .filter(ChannelIdentity.external_id == self.external_id)
                .first()
            )

            if identity is not None:
                conversation = identity.conversation
                self._db.delete(identity)

                if conversation is not None:
                    self._db.query(Message).filter(
                        Message.conversation_id == conversation.id
                    ).delete(synchronize_session=False)
                    self._db.delete(conversation)

            self._db.commit()
        except Exception:  # noqa: BLE001 - cleanup must not mask a real result
            self._db.rollback()
        finally:
            self._db.close()


def _quotes_money(text: str) -> bool:
    return bool(MONEY.search(text))


def _itemised(text: str) -> bool:
    """A real quote shows its lines. A flat tier price cannot."""
    return "–" in text or "—" in text or text.count("₦") > 1


def bug_1_discovery_before_price(new_buyer) -> None:
    """Buy-intent with no prior context must reach discovery, not a price."""
    buyer = new_buyer()

    try:
        buyer.start()
        reply = buyer.say("I want to buy an AI sales rep")

        if _quotes_money(reply):
            raise Failure(
                "Nera quoted a price on the first turn, before asking anything:\n"
                f"{buyer.transcript()}"
            )

        for tell in PAYMENT_TELLS:
            if tell in reply.lower():
                raise Failure(
                    f"Nera asked for payment details ({tell!r}) before discovery:\n"
                    f"{buyer.transcript()}"
                )

        if "?" not in reply:
            raise Failure(
                "Nera neither quoted nor asked a question — discovery did not "
                f"start:\n{buyer.transcript()}"
            )
    finally:
        buyer.close()


def bug_1b_discovery_survives_a_hurry(new_buyer) -> None:
    """Pressure must not buy a shortcut past the questions.

    The report said the same phrase behaved differently on different runs, so the
    interesting case is not one message — it is whether insisting can skip the
    gate. A buyer who says "just give me the price" has still told Nera nothing
    it can price from.
    """
    buyer = new_buyer()

    try:
        buyer.start()
        buyer.say("I want to buy an AI sales rep")
        reply = buyer.say("just give me the price, skip the questions")

        if _quotes_money(reply) and not _itemised(reply):
            raise Failure(
                "Nera produced a flat price under pressure, with no scope:\n"
                f"{buyer.transcript()}"
            )
    finally:
        buyer.close()


def bug_2_no_withdrawn_tier(new_buyer) -> None:
    """The removed flat tier must be unreachable, and prices must itemise."""
    buyer = new_buyer()

    probes = (
        "I want to buy an AI sales rep",
        "how much does it cost",
        "what are your prices",
        "do you have a founding user plan",
        "is there an annual plan",
    )

    try:
        buyer.start()

        for probe in probes:
            reply = buyer.say(probe)

            for token in WITHDRAWN:
                if token.lower() in reply.lower():
                    raise Failure(
                        f"The withdrawn tier surfaced ({token!r}) in reply to "
                        f"{probe!r}:\n{buyer.transcript()}"
                    )

            if _quotes_money(reply) and not _itemised(reply):
                raise Failure(
                    f"A flat, non-itemised price was quoted for {probe!r}:\n"
                    f"{buyer.transcript()}"
                )
    finally:
        buyer.close()


def bug_3_answers_about_itself(new_buyer) -> None:
    """Questions about Nera are answered from its own config, never escalated."""
    questions = (
        "I want to know what you sell",
        "what do you actually sell?",
        "who are you",
        "what are you",
        "are you a human?",
        "what makes you different",
        "tell me about your company",
        "what kind of AI do you build",
    )

    for question in questions:
        buyer = new_buyer()

        try:
            buyer.start()
            reply = buyer.say(question)

            # The structural form of the bug: the reply was produced by the
            # don't-know fallback and handed to a person.
            if buyer.escalated:
                raise Failure(
                    f"Nera escalated a question about itself ({question!r}), "
                    f"rule {buyer.rule!r}:\n{buyer.transcript()}"
                )

            if buyer.rule == "unknown":
                raise Failure(
                    f"Nera fell through to the unknown-question rule for "
                    f"{question!r}:\n{buyer.transcript()}"
                )

            if len(reply.strip()) < 40:
                raise Failure(
                    f"Nera's answer to {question!r} was too thin to be an "
                    f"answer:\n{buyer.transcript()}"
                )
        finally:
            buyer.close()


def bug_3b_a_question_is_not_an_answer(new_buyer) -> None:
    """Asking what Nera sells must not be recorded as choosing what to buy.

    The nastier half of BUG 3, and the one no transcript makes obvious: the intake
    swallowed "what do you sell" as if it were the answer to "what do you need",
    put a product on the scope nobody had chosen, and moved on. The buyer sees a
    plausible reply and finds out later they are being priced for something they
    never asked for.
    """
    buyer = new_buyer()

    try:
        buyer.start()
        buyer.say("what do you sell")

        # Read the thread back rather than the reply: the damage is in the stored
        # scope, not in the sentence, and a reply can look fine while the intake
        # has silently recorded a choice.
        chosen = buyer.interested_plan_code

        if chosen:
            raise Failure(
                f"Asking what Nera sells recorded a plan choice ({chosen!r}):\n"
                f"{buyer.transcript()}"
            )

        reply = buyer.say("what do you sell")

        if "noted" in reply.lower():
            raise Failure(
                "A question about Nera was recorded as an intake answer:\n"
                f"{buyer.transcript()}"
            )
    finally:
        buyer.close()


def the_fallback_still_exists(new_buyer) -> None:
    """The negative control.

    Every check above passes trivially if Nera simply never refuses anything. The
    escalation was narrowed, not deleted: a question about the *buyer's* business
    that Nera has no data on must still reach a human rather than be guessed at.
    """
    buyer = new_buyer()

    try:
        buyer.start()
        buyer.say("what was our revenue in Q3 last year, and who signed off on it?")

        if not buyer.escalated:
            raise Failure(
                "Nera did not escalate a question it cannot possibly know "
                f"(rule {buyer.rule!r}):\n{buyer.transcript()}"
            )
    finally:
        buyer.close()


CHECKS = (
    ("BUG 1  discovery before any price", bug_1_discovery_before_price),
    ("BUG 1b discovery survives a hurry", bug_1b_discovery_survives_a_hurry),
    ("BUG 2  withdrawn tier unreachable", bug_2_no_withdrawn_tier),
    ("BUG 3  answers about itself", bug_3_answers_about_itself),
    ("BUG 3b a question is not an answer", bug_3b_a_question_is_not_an_answer),
    ("CONTROL the fallback still exists", the_fallback_still_exists),
)


def _run(surface: str, new_buyer) -> int:
    """Every check against one surface. Returns the number of failures."""
    print(f"--- {surface} ---")

    failures = 0

    for name, check in CHECKS:
        try:
            check(new_buyer)
        except Failure as exc:
            failures += 1
            print(f"FAIL  {name}\n{exc}\n")
        except httpx.HTTPError as exc:
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}\n")
        except Exception as exc:  # noqa: BLE001 - a crash is a failed check
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}\n")
        else:
            print(f"pass  {name}")

    print()

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Skip the Telegram path. Use when the database is not seeded.",
    )
    args = parser.parse_args()

    try:
        httpx.get(f"{args.base}/", timeout=10.0)
    except httpx.HTTPError:
        print(f"Nothing is listening on {args.base} — start the server first.")
        return 2

    # One token per run, so a run interrupted before cleanup leaves rows that are
    # obviously synthetic and traceable to a single run rather than scattered.
    run_token = secrets.token_hex(4)

    print(f"Verifying against {args.base}  (run {run_token})\n")

    failures = _run(f"website — HTTP {args.base}", lambda: Client(args.base))

    if not args.web_only:
        counter = {"n": 0}

        def new_telegram_buyer():
            counter["n"] += 1
            return TelegramBuyer(run_token, f"chk{counter['n']}")

        failures += _run(
            "telegram — InboundMessagingService.handle", new_telegram_buyer
        )

    total = len(CHECKS) if args.web_only else len(CHECKS) * 2

    if failures:
        print(f"{failures} of {total} flows still behave as reported.")
        return 1

    surfaces = "the website" if args.web_only else "both surfaces"
    print(f"All {total} flows pass against the live deployment, on {surfaces}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
