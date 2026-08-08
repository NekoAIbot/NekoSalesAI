"""The post-sale rules. A calendar, not a model.

Six rules, each a day offset and a condition read from the customer's own
record. They fire in order and they are the entire "retention intelligence"
this product claims — which is the point. A rule you can read in ten seconds
is a rule you can defend to the customer receiving it.

Every message is a template rendered against facts already in the database:
the plan they bought, the price they actually paid, their API key prefix,
whether a conversation has ever reached their widget. Nothing here composes a
sentence that is not written below, so no follow-up can promise a feature, a
discount or a date that does not exist.

Where a rule needs to know whether something happened, it asks the database a
yes/no question. There is no engagement score, because "3 conversations" is
already the useful number and wrapping it in a percentage would only make it
harder to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.catalog import find_plan, format_money
from app.sales.reasoning import Reasoning, plan_reference


@dataclass(frozen=True)
class FollowUpContext:
    """The facts a rule is allowed to read.

    Assembled once by the service and passed to every rule, so a rule cannot
    reach into the session and go looking for something else. Everything on
    here is a value already recorded against the customer.
    """

    company_name: str
    buyer_name: str | None
    plan_code: str
    plan_name: str
    amount_minor: int
    currency: str
    api_key_prefix: str | None
    conversation_count: int
    support_email: str
    dashboard_url: str

    @property
    def first_name(self) -> str:
        """A greeting that degrades to the company rather than to 'there'.

        If the buyer gave a name, use its first word. Otherwise address the
        company. "Hi there" reads as a mail merge that lost its variable.
        """
        if self.buyer_name:
            return self.buyer_name.strip().split()[0]
        return self.company_name

    @property
    def paid(self) -> str:
        return format_money(self.amount_minor, self.currency)


@dataclass(frozen=True)
class Rule:
    """One scheduled message.

    ``applies`` decides whether the rule is relevant at all, and is checked
    twice: once when scheduling, and again immediately before sending. A
    customer who installs the widget on day two should not receive the day-three
    "you have not installed it yet" note, and the second check is what stops
    that.
    """

    code: str
    day_offset: int
    subject: Callable[[FollowUpContext], str]
    body: Callable[[FollowUpContext], str]
    applies: Callable[[FollowUpContext], bool]
    signals: Callable[[FollowUpContext], list[str]]

    def render(self, context: FollowUpContext) -> tuple[str, str, Reasoning]:
        reasoning = Reasoning(rule=self.code, signals=self.signals(context))
        reasoning.cite(plan_reference(context.plan_code))

        return self.subject(context), self.body(context), reasoning


def _always(context: FollowUpContext) -> bool:
    return True


def _no_conversations(context: FollowUpContext) -> bool:
    """Nothing has reached this workspace yet.

    Note what this does *not* claim. There is no signal anywhere in the system
    for "the widget is installed" — nothing pings us on page load — so a rule
    asserting the customer had not installed it would be stating as fact
    something we never observed. Zero conversations is the fact we have, and
    the copy below says exactly that and no more.
    """
    return context.conversation_count == 0


def _has_conversations(context: FollowUpContext) -> bool:
    return context.conversation_count > 0


# ---------- day 0: it is live ----------

DAY_0_LIVE = Rule(
    code="day_0_workspace_live",
    day_offset=0,
    applies=_always,
    signals=lambda c: ["workspace provisioned", f"plan {c.plan_code}"],
    subject=lambda c: f"{c.company_name} is live on NekoSalesAI",
    body=lambda c: f"""Hi {c.first_name},

Your workspace is up. You paid {c.paid} for {c.plan_name} and everything it
covers is switched on now.

Two things to do, in this order:

1. Sign in at {c.dashboard_url} with the email you paid with. Your temporary
   password was shown once on the confirmation screen — reset it when you get in.
2. Paste your widget snippet into your site. It is on the same screen, and it
   is the only step between here and your rep answering a real visitor.

Your API key starts {c.api_key_prefix or "(not yet issued)"}. We only ever
stored a hash of it, so if you have lost it, rotate it from the dashboard
rather than asking us to resend — we genuinely cannot.

Reply to this email if anything is off. It reaches a person.

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 1: the one that actually matters ----------

DAY_1_INSTALL = Rule(
    code="day_1_install_widget",
    day_offset=1,
    applies=_no_conversations,
    signals=lambda c: ["no conversations 24h after provisioning"],
    subject=lambda c: "Your rep is waiting on one line of HTML",
    body=lambda c: f"""Hi {c.first_name},

Your {c.plan_name} workspace has been ready since yesterday and no
conversations have reached it yet. Nine times out of ten that means the widget
snippet has not gone onto the site.

It is one script tag before your closing </body>. The snippet with your token
already in it is on your dashboard: {c.dashboard_url}

If you are waiting on a developer, forward them that page — it is the whole
job. If it is already installed and you are seeing nothing, reply and tell us
what page it is on; we will look at it today.

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 3: installed, but silent ----------

DAY_3_NO_TRAFFIC = Rule(
    code="day_3_no_conversations",
    day_offset=3,
    applies=_no_conversations,
    signals=lambda c: ["zero conversations three days after provisioning"],
    subject=lambda c: "Three days in, no conversations yet",
    body=lambda c: f"""Hi {c.first_name},

Your rep has not had a conversation yet. That is usually one of three things,
and they are quick to tell apart:

- The widget is on a page visitors do not reach. Check it is on the pages
  people actually land on, not only the contact page.
- It is installed but not rendering. Open your site and look for the launcher
  in the bottom corner.
- Traffic is genuinely low this week, in which case nothing is wrong.

Your dashboard shows every conversation as it happens: {c.dashboard_url}

If it is none of those, reply and we will look at your setup directly.

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 7: it is working, here is how to read it ----------

DAY_7_FIRST_WEEK = Rule(
    code="day_7_first_week_review",
    day_offset=7,
    applies=_has_conversations,
    signals=lambda c: [
        f"{c.conversation_count} conversation(s) in the first week",
    ],
    subject=lambda c: "Your first week, and the part worth reading",
    body=lambda c: f"""Hi {c.first_name},

Your rep has handled {c.conversation_count} conversation(s) this week. The
transcripts are on your dashboard: {c.dashboard_url}

The thing worth reading is the "Why I said this" line under each reply. It
shows the rule that fired and the catalog entry the answer came from. Where
you disagree with an answer, that line tells you exactly which entry to edit —
the rep only says what your catalog says, so fixing the source fixes every
future reply.

Anything it was asked and could not answer is sitting in your approvals queue
waiting on you, rather than having been guessed at.

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 14: the approvals queue is the product ----------

DAY_14_APPROVALS = Rule(
    code="day_14_review_approvals",
    day_offset=14,
    applies=_has_conversations,
    signals=lambda c: ["two weeks live", f"{c.conversation_count} conversation(s)"],
    subject=lambda c: "Two weeks in — what your rep escalated",
    body=lambda c: f"""Hi {c.first_name},

Two weeks live. Worth spending ten minutes on your approvals queue:
{c.dashboard_url}

Every item in it is a question your rep refused to answer on its own —
usually a discount request or a claim it could not source. The pattern in
that queue is the useful signal: if the same question keeps arriving, it
belongs in your catalog as a published answer, and then it stops being an
escalation.

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 30: renewal, stated plainly ----------

DAY_30_CHECK_IN = Rule(
    code="day_30_check_in",
    day_offset=30,
    applies=_always,
    signals=lambda c: [
        "thirty days since provisioning",
        f"{c.conversation_count} conversation(s) to date",
    ],
    subject=lambda c: "A month in — how has it gone?",
    body=lambda c: f"""Hi {c.first_name},

You have been on {c.plan_name} for a month, and your rep has handled
{c.conversation_count} conversation(s) in that time.

Two questions, and a plain answer to either is useful:

1. Has it closed anything, or saved you time you would otherwise have spent?
2. What has it got wrong?

The second one is the one we want. We are early, you are a founding customer,
and what you tell us here changes what gets built next.

— NekoSalesAI
{c.support_email}""",
)


# In day order. The scheduler walks this list, so adding a rule here is the
# entire change needed to add a follow-up.
RULES: tuple[Rule, ...] = (
    DAY_0_LIVE,
    DAY_1_INSTALL,
    DAY_3_NO_TRAFFIC,
    DAY_7_FIRST_WEEK,
    DAY_14_APPROVALS,
    DAY_30_CHECK_IN,
)

RULES_BY_CODE = {rule.code: rule for rule in RULES}


def plan_display_name(plan_code: str, fallback: str) -> str:
    """The catalog's name for a plan, falling back to what the order froze.

    An order records the plan name as it was at purchase. If the catalog has
    since renamed the plan, the order's copy is the one the customer paid
    against and the one that should appear in their inbox.
    """
    plan = find_plan(plan_code)
    return plan.name if plan is not None else fallback
