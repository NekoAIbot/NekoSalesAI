"""The post-sale rules. A calendar, not a model.

Ten rules from the day a workspace goes live to six months in, each a day offset
and a condition read from the customer's own record. They fire in order and they
are the entire "retention intelligence" this product claims — which is the point.
A rule you can read in ten seconds is a rule you can defend to the customer
receiving it.

Every message is a template rendered against facts already in the database:
the plan they bought, the price they actually paid, their API key prefix,
whether a conversation has ever reached their widget, whether the snippet has
ever loaded from their site. Nothing here composes a sentence that is not written
below, so no follow-up can promise a feature, a discount or a date that does not
exist. In particular nothing claims a second charge, because nothing in the
system makes one — the plans are quoted per month and billing is a person's job.

Where a rule needs to know whether something happened, it asks the database a
yes/no question. There is no engagement score, because "3 conversations" is
already the useful number and wrapping it in a percentage would only make it
harder to check.

Bodies are drafted when the calendar is written and re-rendered at send time
against that day's facts, which is what lets a rule branch on something that was
not knowable on day 0 — whether the snippet ever loaded, most of all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.catalog import find_plan, format_money
from app.payments.install import website_steps
from app.sales.reasoning import Reasoning, plan_reference

# Long enough that a customer whose site is quiet overnight is not told their
# install has stopped working, short enough that a snippet wiped by a theme
# update is noticed. The same window ``SetupFacts`` uses, for the same reason.
SEEN_RECENTLY = timedelta(hours=24)

# Nera first, a person only for what Nera cannot do.
#
# Every one of these emails used to close on "reply and it reaches a person",
# which made a human the default route for every question including the ones
# already answered above. But the honest version of the fix has to account for
# the medium: a reply to this email lands in a mailbox, not in Nera, so telling
# somebody to "ask me here" would be pointing them at nothing. So it names the
# place that can actually resolve it — the chat on their own desk, which can see
# their setup — and is straight about where a reply goes.
CLOSING = (
    "Stuck on any of this? The chat on your desk is the fastest way through it: "
    "it can see your setup and will work through it with you step by step. "
    "Replying to this email reaches a person, which is the right route for "
    "billing or anything about your order."
)


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
    # The agent's own name and token, so an email can print the snippet the
    # customer is being told to paste instead of sending them to look for it.
    agent_name: str = ""
    widget_token: str | None = None
    # When the snippet last ran on their site, or None if it never has. Defaults
    # are here so an existing caller that has not been taught these yet degrades
    # to "we do not know" rather than to a confident wrong answer.
    widget_last_seen: datetime | None = None

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

    @property
    def widget_never_loaded(self) -> bool:
        """The snippet has never once executed on their site."""
        return self.widget_last_seen is None

    @property
    def widget_loaded_recently(self) -> bool:
        """It ran within the last day, so it is installed and running now."""
        if self.widget_last_seen is None:
            return False

        seen = self.widget_last_seen
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)

        return datetime.now(timezone.utc) - seen <= SEEN_RECENTLY

    @property
    def install_steps(self) -> str:
        """Every step of putting the widget on a site, or "" with no token.

        Shares one implementation with the delivery message rather than keeping a
        shortened copy here. A second, vaguer set of instructions in the emails is
        how "paste your widget snippet into your site" survived being fixed in the
        chat — the sentence was corrected in one place and left standing in the
        other.
        """
        if not self.widget_token:
            return ""

        return website_steps(
            ((self.agent_name or self.plan_name, self.widget_token),)
        )


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

    This used to carry a note saying there was no signal anywhere in the system
    for "the widget is installed" — nothing pinged us on page load — so no rule
    could claim it. That is no longer true: the widget asks the API for its config
    every time it loads, and ``workspace_profiles.widget_last_seen_at`` records
    when it last did. A request can only come from a page carrying the snippet, so
    the column is direct evidence and the rules below now discriminate on it
    instead of guessing.

    Zero conversations is still what decides whether these rules fire at all.
    Whether the snippet is running only changes what they say.
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

Step 1 — sign in at {c.dashboard_url} with the email you paid with. Your
temporary password was shown once on the confirmation screen; reset it when you
get in.

Step 2 — put your agent on your site. Every step is below, so you should not
need to work anything out.

{c.install_steps}

Your API key starts {c.api_key_prefix or "(not yet issued)"}. We only ever
stored a hash of it, so if you have lost it, rotate it from the dashboard
rather than asking us to resend — we genuinely cannot.

{CLOSING}

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 1: the one that actually matters ----------


def _day_1_subject(context: FollowUpContext) -> str:
    if context.widget_never_loaded:
        return "Your rep is waiting on one line of HTML"
    if context.widget_loaded_recently:
        return "Your rep is installed and running, and nobody has used it yet"
    return "Your rep was running, and has gone quiet"


def _day_1_body(context: FollowUpContext) -> str:
    """One rule, three messages, chosen by what the site actually did.

    This used to say "nine times out of ten that means the snippet has not gone
    onto the site" to everybody, including the customers whose snippet was
    demonstrably loading. Being told to do the thing you have already done is the
    reason support email gets ignored, and it was avoidable: the widget tells us
    every time it loads.
    """
    signed = f"{CLOSING}\n\n— NekoSalesAI\n{context.support_email}"

    if context.widget_never_loaded:
        return f"""Hi {context.first_name},

Your {context.plan_name} workspace has been ready since yesterday and no
conversations have reached it yet. I can see why: the snippet has not loaded
from your site even once, so it is not on the page yet.

Here is the whole job, start to finish.

{context.install_steps}

{signed}"""

    if context.widget_loaded_recently:
        return f"""Hi {context.first_name},

Your {context.plan_name} workspace has been ready since yesterday and no
conversations have reached it yet — but the install is fine. The snippet is
loading from your site, so the button is on the page and your rep is waiting.

So this is about who is seeing it, not about the setup:

- Check it is on the pages people actually land on. On most sites the snippet
  goes into a footer or theme file that every page shares; if it went onto one
  page only, most of your visitors never see it.
- Open your own site and send the rep a message. It should appear on your desk
  within seconds: {context.dashboard_url}
- If your traffic is genuinely light this week, nothing is wrong and there is
  nothing to fix.

{signed}"""

    return f"""Hi {context.first_name},

Your {context.plan_name} workspace has been ready since yesterday and no
conversations have reached it yet. The snippet did load from your site at one
point, and it has not in the last day — so it was installed and something has
since removed it.

The usual cause is a theme update or a republish overwriting the file it was
pasted into. Two things worth checking:

- Open your site and look for the chat button in the bottom-right corner. If it
  is gone, the snippet has been overwritten and needs pasting back in.
- If you edited or reinstalled your theme, check whichever footer or custom-code
  box you used the first time — that is what gets reset.

The snippet is unchanged, so pasting it back is all that is needed:

{context.install_steps}

{signed}"""


DAY_1_INSTALL = Rule(
    code="day_1_install_widget",
    day_offset=1,
    applies=_no_conversations,
    signals=lambda c: [
        "no conversations 24h after provisioning",
        (
            "widget never loaded"
            if c.widget_never_loaded
            else "widget loading now"
            if c.widget_loaded_recently
            else "widget loaded once, not in the last day"
        ),
    ],
    subject=_day_1_subject,
    body=_day_1_body,
)


# ---------- day 3: installed, but silent ----------


def _day_3_body(context: FollowUpContext) -> str:
    """Three days in, and the guessing narrowed down to one thing.

    The original listed three possible causes and asked the customer to tell them
    apart. Two of the three — "the widget is on a page visitors do not reach" and
    "it is installed but not rendering" — are answered by whether the snippet has
    loaded, which we know. Only the third is genuinely about their traffic.
    """
    signed = f"{CLOSING}\n\n— NekoSalesAI\n{context.support_email}"

    if context.widget_never_loaded:
        return f"""Hi {context.first_name},

Three days and your rep has not had a single conversation, and the reason is
not a mystery: the snippet has never loaded from your site, so there is nothing
on the page for a visitor to click.

Nothing else is worth checking until that is done, and it is a two-minute job:

{context.install_steps}

If you have pasted it and it still has not loaded, tell the chat on your desk
which platform your site is built on and what you are seeing after a
hard-refresh, and it will work through it with you.

{signed}"""

    if context.widget_loaded_recently:
        return f"""Hi {context.first_name},

Three days in and your rep has not had a conversation yet. The install is not
the problem — the snippet is loading from your site, so the button is there.

Which leaves two things, and they are quick to tell apart:

- It is not on the pages people land on. The snippet loading proves it is on at
  least one page, not on every page. If it went into a single page's custom-code
  box instead of the shared footer or theme file, most visitors never see it.
- Traffic is genuinely low this week, in which case nothing is wrong and this
  email is the only thing that needs no action.

Every conversation shows up on your desk the moment it happens, so you do not
have to watch for it: {context.dashboard_url}

{signed}"""

    return f"""Hi {context.first_name},

Three days in and your rep has not had a conversation yet. The snippet did load
from your site earlier on and has not in the last day, which means it was
installed and has since been removed — almost always a theme update or a
republish overwriting the file it went into.

Open your site and look for the chat button in the bottom-right corner. If it is
missing, pasting the snippet back is the whole fix:

{context.install_steps}

{signed}"""


DAY_3_NO_TRAFFIC = Rule(
    code="day_3_no_conversations",
    day_offset=3,
    applies=_no_conversations,
    signals=lambda c: [
        "zero conversations three days after provisioning",
        (
            "widget never loaded"
            if c.widget_never_loaded
            else "widget loading now"
            if c.widget_loaded_recently
            else "widget loaded once, not in the last day"
        ),
    ],
    subject=lambda c: (
        "Three days in, and the snippet has not gone on yet"
        if c.widget_never_loaded
        else "Three days in, no conversations yet"
    ),
    body=_day_3_body,
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


# ---------- day 60: two months, and the honest question ----------


def _day_60_dormant_body(context: FollowUpContext) -> str:
    """Two months, never used once. The email nobody wants to send.

    Deliberately blunt, and deliberately not a sales email. A workspace with no
    conversations after two months is somebody who bought something and never got
    the value of it, and the useful thing is to name that and offer both ways out —
    get it working, or stop. Pretending it is going fine is how a customer arrives
    at the renewal conversation feeling sold to.

    It makes no claim about billing. Nothing in the system charges a second time,
    so this cannot say "you have paid twice" or offer a refund; billing is a
    person's decision and the copy routes it to one.
    """
    signed = f"— NekoSalesAI\n{context.support_email}"

    if context.widget_never_loaded:
        return f"""Hi {context.first_name},

Two months since your {context.plan_name} workspace went live, and it has never
handled a single conversation. I can tell you exactly why: the snippet has never
loaded from your site, so your rep has never been on the page.

I would rather say that plainly than keep sending you tips.

Two ways out of it, and either is fine:

1. Finish the install. It is genuinely a two-minute job and every step is below.
2. If it is not going to happen — the site is on hold, the developer never came
   back, it is not the right fit — reply to this email and a person will sort out
   your account with you. You should not be carrying a plan you have never used.

{context.install_steps}

{signed}"""

    return f"""Hi {context.first_name},

Two months since your {context.plan_name} workspace went live, and it has not
handled a conversation yet. The install is not the problem — the snippet has
loaded from your site, so your rep is on the page and waiting.

That points at reach rather than setup, and it is worth ten minutes to check
which: open the pages your visitors actually land on and look for the chat button
in the bottom-right corner. If it is only on one page, that is the whole story.

And if the honest answer is that this is not earning its place, say so. Reply to
this email and a person will go through your account with you. I would rather
know than keep emailing you about a rep nobody is using.

{signed}"""


DAY_60_DORMANT = Rule(
    code="day_60_never_used",
    day_offset=60,
    applies=_no_conversations,
    signals=lambda c: [
        "zero conversations sixty days after provisioning",
        (
            "widget never loaded"
            if c.widget_never_loaded
            else "widget has loaded, no conversations"
        ),
    ],
    subject=lambda c: (
        "Two months, and your rep has never been on your site"
        if c.widget_never_loaded
        else "Two months, and no conversations yet"
    ),
    body=_day_60_dormant_body,
)


DAY_60_AUDIT = Rule(
    code="day_60_spot_check",
    day_offset=60,
    applies=_has_conversations,
    signals=lambda c: [
        "two months live",
        f"{c.conversation_count} conversation(s) to date",
    ],
    subject=lambda c: "Two months in — worth spot-checking a few replies",
    body=lambda c: f"""Hi {c.first_name},

{c.conversation_count} conversation(s) handled since your workspace went live.
At this point the useful exercise is not a tip, it is a check.

Open five transcripts on your desk, pick the replies that quoted a price or made
a claim, and read the "Why I said this" line under each one. It names the rule
that fired and the catalog entry the answer came from. Every one should trace
back to something you published.

That is the guarantee this product is built on: your rep does not decide prices
and does not invent capabilities — it quotes your catalog or it asks you. If you
find a single reply that says something your catalog does not, that is a bug and
we want it. Reply to this email with the transcript and it goes straight to us.

Your desk: {c.dashboard_url}

{CLOSING}

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 90: the catalog has been sitting still for a quarter ----------

DAY_90_CATALOG_DRIFT = Rule(
    code="day_90_catalog_review",
    day_offset=90,
    applies=_has_conversations,
    signals=lambda c: [
        "three months live",
        f"{c.conversation_count} conversation(s) to date",
    ],
    subject=lambda c: "Three months on, your catalog is the thing to check",
    body=lambda c: f"""Hi {c.first_name},

Three months and {c.conversation_count} conversation(s). This one is about a
limitation rather than a feature, because it is the one that costs real money if
nobody says it out loud.

Your rep answers from your catalog and nowhere else. That is what stops it
inventing prices — and it is also why it cannot tell that a price has gone stale.
If something went up two months ago and the catalog still says the old figure,
your rep will quote the old figure to every buyer who asks, confidently, and
nothing in the system will flag it. It is not wrong from where it is standing.

So a quarterly pass is worth putting in the diary:

- Prices, on everything you sell often.
- Anything you have stopped selling. An entry that is still published is still
  quotable.
- Delivery times, terms and anything seasonal.

Editing an entry changes every future reply that touches it, so it is one edit
rather than a correction campaign: {c.dashboard_url}

{CLOSING}

— NekoSalesAI
{c.support_email}""",
)


# ---------- day 180: six months of your customers' own words ----------

DAY_180_HALF_YEAR = Rule(
    code="day_180_half_year",
    day_offset=180,
    applies=_has_conversations,
    signals=lambda c: [
        "six months live",
        f"{c.conversation_count} conversation(s) to date",
    ],
    subject=lambda c: "Six months of transcripts, and what they are worth",
    body=lambda c: f"""Hi {c.first_name},

Six months, {c.conversation_count} conversation(s). What you have on your desk
now is a record of what your customers actually ask, in their own words, which is
not something most businesses this size ever get to read.

Two things worth doing with it:

1. Read your approvals queue as a list rather than as tasks. The question that
   keeps coming back is telling you something — either it belongs in your
   catalog as a published answer, or it is a gap in what you offer.
2. Look at what people ask for and do not get. Six months of "do you also
   do…" is market research you did not have to commission.

And if some other job in your business looks like this one — the same question
arriving over and over, from people you cannot always answer in time — the chat
on your desk will scope it and price it line by line, the same way this one was
priced. No obligation and no call: ask it what something would cost and it will
tell you.

Your desk: {c.dashboard_url}

{CLOSING}

— NekoSalesAI
{c.support_email}""",
)


# In day order. The scheduler walks this list, so adding a rule here is the
# entire change needed to add a follow-up.
#
# Every offset is days since the workspace went live — ``ready_at`` plus the
# offset — so the whole calendar is counted from day 0 and not from the message
# before it. Two rules may share an offset when the right message depends on a
# fact: day 60 is one email for a workspace nobody has used and a different one
# for a workspace that is working, and their conditions are mutually exclusive so
# exactly one of them ever sends.
RULES: tuple[Rule, ...] = (
    DAY_0_LIVE,
    DAY_1_INSTALL,
    DAY_3_NO_TRAFFIC,
    DAY_7_FIRST_WEEK,
    DAY_14_APPROVALS,
    DAY_30_CHECK_IN,
    DAY_60_DORMANT,
    DAY_60_AUDIT,
    DAY_90_CATALOG_DRIFT,
    DAY_180_HALF_YEAR,
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
