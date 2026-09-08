"""Resolving a customer's problem instead of fetching someone to resolve it.

The delivery message used to close with "anything not working, tell me here and I
will get a person on it", and that line was honest about what the engine could
do: nothing. A paying customer who said "the chat isn't showing on my site" was
answered by the sales intake asking which product they would like to buy. There
was no post-purchase path at all.

This module is that path. It is not a bigger escalation funnel and not a canned
FAQ — the two things that get built when "support" is on a list — and the
difference is in what it is allowed to know.

**A diagnosis is built from facts, not from the symptom alone.** ``SetupFacts``
is what is actually true of one customer's workspace right now: whether the build
finished, whether the snippet on their site has ever executed, which channels they
paid for, which of those are actually live, how many conversations their agent has
answered. The same sentence — "it's not working" — gets a different answer
depending on those, because it *is* a different problem. Generic advice is what a
customer who has already tried the generic advice gets nothing from, and that is
the state most people are in by the time they type the complaint.

**Escalation is a decision, not a fallback.** ``needs_human`` is set for three
reasons and no others: money, a change to what was built, and the case where the
facts say we cannot fix this from here — most importantly the channel a customer
paid for that provisioning does not yet create, where the truthful answer is that
this one is on us. "It will take several steps to explain" is not on the list.
Neither is "I am not certain", which is what the clarifying question is for.

**Nothing here invents a fact.** Every finding is drawn from ``SetupFacts`` and
every step from ``app.payments.install``, which is the same text the delivery
message and the credentials email are built from. That is why the install steps
live there as data: three surfaces need to say the same thing about installation,
and copy that has drifted is worse than copy that is thin.

Deterministic, like the rest of the engine. When the LLM understanding layer
lands it goes in front of ``read_symptom`` — reading a rambling complaint into a
symptom is exactly the job a model is better at — and the diagnosis stays here,
because what we tell a customer is true of their workspace must not be a
generation. The seam is deliberate: ``read_symptom`` takes text and returns one of
a closed set of symptoms, and everything downstream reads facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.payments.install import PLATFORMS, TROUBLESHOOTING, platform_for

# ---------------------------------------------------------------------------
# What can be wrong
# ---------------------------------------------------------------------------

# The widget was installed, or the customer believes it was, and no chat appears.
SYMPTOM_NOT_VISIBLE = "widget_not_visible"

# The chat is there and says nothing back.
SYMPTOM_NO_REPLY = "agent_not_replying"

# It answers, and the answers are wrong, thin, or off-brand.
SYMPTOM_WRONG_ANSWERS = "answers_are_wrong"

# They have not managed to install it — a different problem from a broken
# install, and the one where platform-specific steps are the whole answer.
SYMPTOM_CANNOT_INSTALL = "cannot_install"

# A channel they paid for is not there.
SYMPTOM_CHANNEL_MISSING = "channel_not_live"

# Something is wrong and the message does not say what.
SYMPTOM_UNCLEAR = "problem_unclear"


# Ordered: the first match wins, so the more specific symptoms are tried before
# the general "nothing works". A customer usually reports one thing badly rather
# than several things well.
_SYMPTOM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        SYMPTOM_CHANNEL_MISSING,
        # Every pattern here needs all three parts: the channel, the thing that
        # ought to exist, and its absence.
        #
        # It used to need only a channel name near a negation, and that is the
        # same sentence as an ordinary answer to the intake question about
        # channels — "telegram only, no whatsapp" was read as a complaint that
        # WhatsApp had not been provisioned. A buyer choosing channels and a
        # customer missing one are not distinguishable by their words alone
        # unless the words include what is missing.
        (
            r"\bwhere('?s| is| are)?\b[^.!?]{0,25}\b(telegram|whats ?app)\b",
            r"\b(telegram|whats ?app)\b[^.!?]{0,25}\b(is|are|isn'?t|aren'?t|"
            r"not|never|hasn'?t|has not|was ?n'?t|still)\b[^.!?]{0,25}"
            r"\b(set ?up|working|live|connected|ready|activated|created|there|"
            r"available|arrived|configured|come through|showed up)\b",
            r"\b(no|not|missing|never got|never received|haven'?t got|"
            r"did ?n'?t get|hasn'?t)\b[^.!?]{0,25}\b(telegram|whats ?app)\b"
            r"[^.!?]{0,25}\b(bot|number|account|link|access|agent|"
            r"integration)\b",
            r"\b(telegram|whats ?app)\b[^.!?]{0,20}\b(bot|number|account|link|"
            r"access|agent|integration)\b[^.!?]{0,30}\b(not|isn'?t|missing|"
            r"never|hasn'?t|nowhere|no|yet|where)\b",
            r"\b(paid|bought|ordered|purchased|added) (for )?\b[^.!?]{0,40}"
            r"\b(telegram|whats ?app)\b",
            r"\bno (telegram|whats ?app) (bot|number|account|link|access|"
            r"agent)\b",
        ),
    ),
    (
        SYMPTOM_WRONG_ANSWERS,
        (
            # Words that can only be describing output. "wrong" and "incorrect"
            # are deliberately not in this list: "something is wrong" is the most
            # common way anyone opens a support conversation and says nothing at
            # all about the answers, and reading it as "the answers are wrong"
            # skips straight past the one question worth asking.
            r"\b(nonsense|rubbish|made up|inaccurate|irrelevant|"
            r"gibberish)\b",
            # Inventing an answer, in the way people actually say it. "made up"
            # above only catches the adjective; this catches the verb, which is
            # the form the complaint arrives in.
            r"\b(mak(e|es|ing)|made) (things|stuff|it|that|them|answers|prices) "
            r"up\b",
            r"\b(invent(s|ed|ing)?|fabricat(es|ed|ing))\b",
            r"\b(says|said|saying|answers?|answered|replies|replied|telling)\b"
            r"[^.!?]{0,30}\b(wrong|the wrong|nonsense|rubbish|not true|"
            r"incorrect(ly)?)\b",
            r"\b(gave|giving|quoted|quoting) (the )?wrong (price|answer|"
            r"amount|number|figure)\b",
            r"\bdoes ?n'?t know\b",
            r"\bwrong (price|answer|name|amount|number|figure|information)\b",
            # The same complaint with the words the other way round: "the price
            # it quoted was wrong", "its answers are wrong".
            r"\b(answers?|repl(y|ies)|responses?|price|prices|info|"
            r"information|details?)\b[^.!?]{0,20}\b(wrong|incorrect)\b",
        ),
    ),
    (
        SYMPTOM_NO_REPLY,
        (
            r"\b(no|not|never|isn'?t|does ?n'?t|won'?t|wont|stopped)\b"
            r"[^.!?]{0,30}\b(repl(y|ies|ying)|respond(ing|s)?|answer(ing|s)?|"
            r"say(s|ing)? anything)\b",
            r"\b(silent|no response|no answer|no reply)\b",
            r"\b(type|typed|typing|sent|send|asked|ask)\b[^.!?]{0,40}"
            r"\b(nothing happens?|nothing happened|no reply|nothing back|"
            r"no response)\b",
            r"\bjust (sits|spins|loads)\b",
        ),
    ),
    (
        SYMPTOM_NOT_VISIBLE,
        (
            r"\b(widget|chat|chat ?box|chat ?bubble|bubble|icon|button|"
            r"agent|it)\b[^.!?]{0,40}\b(not (show|showing|appear|appearing|"
            r"visible|there|display|displaying|loading)|isn'?t (show|showing|"
            r"appearing|there|visible|loading)|does ?n'?t (show|appear|"
            r"display|load)|won'?t (show|appear|load)|missing|invisible|"
            r"nowhere)\b",
            r"\b(can'?t|cannot|do ?n'?t|unable to) (see|find|locate)\b"
            r"[^.!?]{0,30}\b(widget|chat|chat ?box|bubble|icon|button|agent|"
            r"it|anything)\b",
            r"\bnothing (shows|appears|showed|appeared|is showing|there)\b",
            r"\b(pasted|added|installed|put)\b[^.!?]{0,50}\b(nothing|"
            r"no change|still nothing|not there|does ?n'?t work)\b",
            r"\bblank\b",
        ),
    ),
    (
        SYMPTOM_CANNOT_INSTALL,
        (
            r"\b(how|where) (do|can|should) i\b[^.!?]{0,30}\b(install|paste|"
            r"add|put|embed|set ?up)\b",
            r"\b(where) (do|does|is|are)\b[^.!?]{0,30}\b(snippet|code|script|"
            r"tag|it) go\b",
            r"\b(can'?t|cannot|do ?n'?t know how to|not sure how to|unable to)"
            r"\b[^.!?]{0,30}\b(install|paste|add|embed|find the code|set it "
            r"up|set ?up)\b",
            r"\b(no|not|never) (received|got|seen)\b[^.!?]{0,30}"
            r"\b(snippet|code|script|instructions?)\b",
            r"\bwhat (is|do i do with) (the )?(snippet|script|code)\b",
        ),
    ),
    (
        SYMPTOM_UNCLEAR,
        (
            r"\b(not working|does ?n'?t work|isn'?t working|broken|"
            r"stopped working|not functioning|no longer works?)\b",
            r"\bsomething('?s| is) wrong\b",
            # "what's wrong with it" is a question, not a description, and the
            # answer is still the same clarifying question.
            r"\bwhat('?s| is| has|'?ve| have) (gone )?wrong\b",
            r"\b(having|got|there'?s) (a|an) (problem|issue|error|trouble)\b",
            r"\b(it|this) (fail(s|ed)?|crash(es|ed)?)\b",
            r"\bhelp\b[^.!?]{0,20}\bnot working\b",
        ),
    ),
)


# Reported as a problem, but the thing to do about it is not a diagnosis.
#
# Money and unwinding what was built are the two categories a human genuinely
# owns: one moves funds and the other undoes something already paid for and
# provisioned. Kept separate from the symptom list so that a refund request
# cannot be answered with install steps, which is the failure mode of every
# support bot that classifies before it checks.
#
# "upgrade" and "add" are deliberately absent. A customer asking for more than
# they bought is a sale, and Nera can quote it — routing that to a person would
# put a queue in front of money coming in. Only the directions that take money
# back out are here.
_NEEDS_A_PERSON = (
    r"\b(refund|money back|charge ?back|reverse the payment|cancel my "
    r"(order|subscription|payment|account)|double ?charg(e|ed)|charged twice|"
    r"billed twice)\b",
    r"\b(change|swap|remove|downgrade|cancel) (my |the |our )?"
    r"(order|plan|package|product|agent|subscription)\b",
    r"\b(invoice|receipt|vat|tax) (for|please|copy)\b",
    r"\b(legal|contract|lawyer|sue|police|fraud|scam)\b",
)


def read_symptom(text: str) -> str | None:
    """Which known problem this message is reporting, if any.

    Returns None for anything that is not a problem report, and the caller must
    treat that as "not my turn" rather than "no problem" — the sales path handles
    the great majority of messages and must not lose them to a support module
    that reads too eagerly.

    The seam for the LLM layer. A model reading a three-paragraph complaint into
    one of these constants is strictly better than these patterns; what it must
    not do is decide what is *true* of the workspace, which is the next function's
    job and is answered from the database.
    """
    lowered = (text or "").lower()

    if not lowered.strip():
        return None

    for symptom, patterns in _SYMPTOM_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return symptom

    return None


def asks_for_a_person(text: str) -> bool:
    """Whether this is one of the things a person actually owns.

    Money and changes to what was built. Checked before the symptom, so "I want a
    refund, the widget never worked" reaches a human with the complaint attached
    rather than getting a checklist.
    """
    return any(re.search(pattern, (text or "").lower()) for pattern in _NEEDS_A_PERSON)


# ---------------------------------------------------------------------------
# What is true
# ---------------------------------------------------------------------------

# How recently the snippet must have run for "I can see it loading" to be a claim
# worth making. Longer than the write throttle in the widget route, so a site that
# is simply quiet for a few minutes is not reported as broken.
SEEN_RECENTLY = timedelta(hours=24)


@dataclass(frozen=True)
class SetupFacts:
    """What is actually true of one customer's workspace, right now.

    Passed in rather than looked up, for the same reason ``order_paid`` is: the
    agent is pure, and a diagnosis is exactly the place where a fact must be a
    fact rather than a plausible sentence. Everything here is read from the
    database by ``app.sales.service`` and handed over.

    The defaults describe a visitor who has bought nothing, which is the common
    case and must produce no diagnosis at all.
    """

    # Is there a provisioned workspace behind this conversation? False for a
    # prospect, which is what keeps the sales path unaffected.
    is_customer: bool = False

    agent_name: str = ""

    # Did the build finish? False means the problem is ours and outstanding.
    workspace_ready: bool = False

    # Has provisioning issued the token the snippet needs?
    has_widget_token: bool = False

    # When the snippet on their site last executed. None means never seen.
    widget_last_seen: datetime | None = None

    # What they paid for, and what is actually live. The gap between these two is
    # the honest reason for an escalation rather than an excuse for one.
    bought_channels: tuple[str, ...] = ()
    live_channels: tuple[str, ...] = ()

    # How many conversations their agent has answered. A non-zero count is proof
    # the agent itself works, which changes the diagnosis of "it's not replying"
    # from "it is not installed" to "this page or this browser".
    conversations_handled: int = 0

    # Their site platform, if we have been told. Turns the install steps from a
    # list of six platforms into the one they are on.
    platform: str = ""

    @property
    def widget_seen_recently(self) -> bool:
        if self.widget_last_seen is None:
            return False

        seen = self.widget_last_seen

        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)

        return datetime.now(UTC) - seen <= SEEN_RECENTLY

    @property
    def widget_never_seen(self) -> bool:
        return self.widget_last_seen is None

    @property
    def channels_owed(self) -> tuple[str, ...]:
        """Channels paid for that are not live. The debt, in one place."""
        return tuple(
            channel for channel in self.bought_channels
            if channel not in self.live_channels
        )


@dataclass
class Diagnosis:
    """One answer to one problem, with its reasoning kept separate from its prose.

    ``finding`` is what we can see and is only ever populated from facts.
    ``cause`` is the most likely explanation given the symptom and those facts.
    ``steps`` is what to do about it. ``question`` is the single thing we need
    them to tell us, and is empty when the facts already discriminate — asking a
    question we can answer ourselves is the other way to waste someone's time.
    """

    symptom: str
    cause: str
    finding: str = ""
    steps: tuple[str, ...] = ()
    question: str = ""
    needs_human: bool = False
    human_reason: str = ""
    signals: list[str] = field(default_factory=list)

    def render(self) -> str:
        """The message, assembled in the order a person would say it."""
        parts: list[str] = []

        if self.finding:
            parts.append(self.finding)

        parts.append(self.cause)

        if self.steps:
            parts.append("\n".join(self.steps))

        if self.question:
            parts.append(self.question)

        return "\n\n".join(part for part in parts if part.strip())


# ---------------------------------------------------------------------------
# Putting the two together
# ---------------------------------------------------------------------------


def diagnose(symptom: str, facts: SetupFacts) -> Diagnosis:
    """The most likely cause of this symptom for this workspace, and the fix.

    Dispatches on the symptom, but every branch reads facts before it decides —
    which is the whole distinction between this and a FAQ. "It isn't showing"
    from a workspace whose snippet has never run and "it isn't showing" from one
    whose snippet loaded four minutes ago are not the same problem and must not
    get the same answer.
    """
    if symptom == SYMPTOM_CHANNEL_MISSING:
        return _channel_missing(facts)

    if not facts.workspace_ready:
        # Nothing else can be diagnosed until the thing exists. Said first
        # whatever they reported, because every other answer would be advice
        # about installing something that is not finished.
        return _still_building(symptom, facts)

    if symptom == SYMPTOM_CANNOT_INSTALL:
        return _cannot_install(facts)

    if symptom == SYMPTOM_NOT_VISIBLE:
        return _not_visible(facts)

    if symptom == SYMPTOM_NO_REPLY:
        return _no_reply(facts)

    if symptom == SYMPTOM_WRONG_ANSWERS:
        return _wrong_answers(facts)

    return _unclear(facts)


def _still_building(symptom: str, facts: SetupFacts) -> Diagnosis:
    """The build has not finished, so the problem is ours and not theirs.

    Emphatically not an escalation. A workspace that is mid-provisioning is a
    normal state with a known end, and the useful thing is to say so and say what
    happens next. Fetching a person to explain that a build is still building is
    how a queue fills with rows nobody needs to read.
    """
    return Diagnosis(
        symptom=symptom,
        finding=(
            "Before anything else — I can see your workspace hasn't finished "
            "being set up yet, so nothing is wrong on your end."
        ),
        cause=(
            "Until it's ready there's no code for you to install and no agent to "
            "answer anyone, which would explain everything you're seeing."
        ),
        steps=(
            "I'll message you here the moment it's live, with the code and where "
            "to put it.",
        ),
        question=(
            "If it's been more than an hour since you paid, say so and I'll get "
            "someone to look at why it's stuck."
        ),
        signals=["workspace not ready"],
    )


def _channel_missing(facts: SetupFacts) -> Diagnosis:
    """A channel they paid for and do not have.

    The one branch that escalates on the facts rather than on the question, and
    it is honest about why: provisioning issues a website widget and nothing
    else. A customer who paid the Telegram add-on has bought something we do not
    yet create, and no amount of walking them through anything fixes that.

    Telling them to go and make their own bot at @BotFather would be worse than
    escalating — it would be charging for something and then asking the customer
    to build it.
    """
    owed = facts.channels_owed

    if not owed:
        return Diagnosis(
            symptom=SYMPTOM_CHANNEL_MISSING,
            finding=(
                "Your account shows "
                + _listed(facts.live_channels)
                + " as set up on your side."
            ),
            cause=(
                "So this is most likely a connection that has dropped rather "
                "than something that was never built."
            ),
            question=(
                "Tell me which one you're trying to use and what you see when "
                "you message it, and I'll work through it with you."
            ),
            signals=["channels bought are all live"],
        )

    return Diagnosis(
        symptom=SYMPTOM_CHANNEL_MISSING,
        finding=(
            "You're right, and I'd rather say so plainly: you paid for "
            + _listed(owed)
            + " and it isn't set up."
        ),
        cause=(
            "That one is on us, not on anything you've done, and it isn't "
            "something I can switch on from here."
        ),
        steps=(
            "I've flagged it to the team with your account attached.",
            "Your website agent is unaffected and working — this is only the "
            "messaging side.",
        ),
        needs_human=True,
        human_reason="Channel paid for but not provisioned",
        signals=[f"owed channels: {', '.join(owed)}"],
    )


def _cannot_install(facts: SetupFacts) -> Diagnosis:
    """They have not got it on the site yet, and want to be shown how.

    The only branch where the full platform list is the right answer, because the
    question is "how", not "why isn't it working". If we know their platform, they
    get that one; otherwise they get asked, because six sets of steps is the same
    as none.
    """
    platform = platform_for(facts.platform)

    if platform is not None:
        return Diagnosis(
            symptom=SYMPTOM_CANNOT_INSTALL,
            cause=f"Here's exactly where it goes on {platform.label}.",
            steps=(platform.render(),),
            question=(
                "Work through that and tell me what you see — if it still isn't "
                "there afterwards, say so and we'll find out why."
            ),
            signals=[f"platform known: {facts.platform}"],
        )

    return Diagnosis(
        symptom=SYMPTOM_CANNOT_INSTALL,
        cause=(
            "Happy to walk you through it — the steps are different depending "
            "on how your site was built, and I'd rather give you the right ones "
            "than all of them."
        ),
        question=(
            "What is your site built with? "
            + _platform_prompt()
            + " If you're not sure, tell me the address and I'll work it out."
        ),
        signals=["platform unknown"],
    )


def _not_visible(facts: SetupFacts) -> Diagnosis:
    """Installed, or believed to be, and no chat on the page.

    The branch the last-seen stamp was added for. Whether the snippet has ever
    executed splits this cleanly into two different problems with two different
    fixes, and without that fact both get the same checklist — which is what a
    customer who has already tried the checklist has already had.
    """
    if not facts.has_widget_token:
        return Diagnosis(
            symptom=SYMPTOM_NOT_VISIBLE,
            finding=(
                "I can see your workspace is ready but no website code has been "
                "issued for it, which is a gap on our side."
            ),
            cause="So there is nothing on your page to show yet.",
            needs_human=True,
            human_reason="Workspace ready with no widget token",
            signals=["no widget token"],
        )

    if facts.widget_never_seen:
        return Diagnosis(
            symptom=SYMPTOM_NOT_VISIBLE,
            finding=(
                "I've checked from this end: the code has never once loaded from "
                "your site, so it hasn't reached us at all yet."
            ),
            cause=(
                "That narrows it a lot. When the snippet is on a live page it "
                "calls us every time someone opens it — so either it isn't saved "
                "yet, or it is saved somewhere that isn't published, which is by "
                "far the most common one."
            ),
            steps=("The three things that cause this, in the order they cause it:",)
            + tuple(
                f"{index}. {cause[0].upper()}{cause[1:]}. {fix}"
                for index, (cause, fix) in enumerate(TROUBLESHOOTING, 1)
            ),
            question=(
                "Two things and I can tell you which it is: what is your site "
                "built with, and after you saved it, did you publish or update "
                "the site?"
            ),
            signals=["widget never seen loading"],
        )

    if facts.widget_seen_recently:
        return Diagnosis(
            symptom=SYMPTOM_NOT_VISIBLE,
            finding=(
                "The code is loading from your site — I can see it running, so "
                "the install itself is right."
            ),
            cause=(
                "That rules out the usual causes and leaves the ones that only "
                "affect what you're looking at: a cached copy of the page, or a "
                "page the snippet isn't on."
            ),
            steps=(
                "• Hard-refresh the page: Ctrl+Shift+R, or Cmd+Shift+R on a Mac.",
                "• Try it in a private/incognito window, which ignores the cache "
                "entirely.",
                "• If an ad-blocker is on, turn it off for your own site just "
                "long enough to check.",
            ),
            question=(
                "Which page are you looking at, and does it appear in a private "
                "window? If it does, it's cache and it'll clear. If it doesn't, "
                "tell me and we'll keep going."
            ),
            signals=["widget seen loading recently"],
        )

    return Diagnosis(
        symptom=SYMPTOM_NOT_VISIBLE,
        finding=(
            "The code has loaded from your site before, but not in the last day."
        ),
        cause=(
            "So it was installed correctly at some point and something has "
            "changed since — most often a theme update or a redesign that "
            "replaced the file it was in."
        ),
        steps=(
            "• Check the snippet is still where you put it — theme updates "
            "overwrite theme files, which is why it goes in a footer/custom-code "
            "box rather than in the theme itself.",
            "• If it's gone, paste it back and republish.",
        ),
        question=(
            "Has anything changed on the site recently — a theme update, a new "
            "design, a plugin removed?"
        ),
        signals=["widget seen, but not recently"],
    )


def _no_reply(facts: SetupFacts) -> Diagnosis:
    """The chat is there and answers nothing.

    Split on whether the agent has ever answered anybody. If it has, the agent
    works and the problem is local to what they are looking at; if it has not,
    the more likely story is that the thing they are typing into is not actually
    connected to us.
    """
    if facts.widget_never_seen:
        return Diagnosis(
            symptom=SYMPTOM_NO_REPLY,
            finding=(
                "Nothing has ever loaded from your site from where I'm sitting."
            ),
            cause=(
                "If you're typing into a chat box and nothing comes back, and "
                "we've never seen the page call us, then the box on your screen "
                "isn't connected to your agent — usually an old copy of the page, "
                "or a different chat tool still installed from before."
            ),
            question=(
                "Where are you seeing the chat box — your live site, or a preview "
                "or builder view? And is there any other chat plugin installed?"
            ),
            signals=["no reply reported", "widget never seen loading"],
        )

    if facts.conversations_handled > 0:
        return Diagnosis(
            symptom=SYMPTOM_NO_REPLY,
            finding=(
                f"Your agent has answered {facts.conversations_handled} "
                "conversation"
                + ("s" if facts.conversations_handled != 1 else "")
                + " already, and the code is loading from your site."
            ),
            cause=(
                "So the agent itself is working, which points at this particular "
                "page or browser rather than the setup."
            ),
            steps=(
                "• Hard-refresh and try once more: Ctrl+Shift+R, or Cmd+Shift+R "
                "on a Mac.",
                "• Try a private window, or your phone on mobile data.",
            ),
            question=(
                "Tell me exactly what you typed and how long you waited, and "
                "whether the message appeared in the chat as yours. That tells me "
                "whether it left the page at all."
            ),
            signals=[
                "no reply reported",
                f"agent has handled {facts.conversations_handled} conversations",
            ],
        )

    return Diagnosis(
        symptom=SYMPTOM_NO_REPLY,
        finding=(
            "The code is loading from your site, and your agent hasn't answered "
            "anyone yet — so you'd be the first."
        ),
        cause=(
            "That usually means the message isn't leaving the page: a blocker, a "
            "stale copy of the script, or the send not registering."
        ),
        steps=(
            "• Hard-refresh the page first: Ctrl+Shift+R, or Cmd+Shift+R on a Mac.",
            "• Then try in a private window with any ad-blocker off.",
        ),
        question=(
            "When you send a message, does your own message appear in the chat? "
            "If it does and nothing comes back, that's a different problem from "
            "it not appearing at all, and I'll take it from there."
        ),
        signals=["no reply reported", "agent has handled no conversations"],
    )


def _wrong_answers(facts: SetupFacts) -> Diagnosis:
    """It replies, and the replies are wrong.

    Deliberately does not fetch a person, and deliberately does not promise a
    fix. The agent answers out of the material in its workspace, so a wrong
    answer is nearly always a gap or an error in that material — which is
    fixable, and fixable by them, once they know that is what it is. What it
    needs from them is the actual exchange.
    """
    return Diagnosis(
        symptom=SYMPTOM_WRONG_ANSWERS,
        finding=(
            f"{facts.agent_name or 'Your agent'} answers out of the material in "
            "your workspace and nothing else — it has no general knowledge to "
            "fall back on."
        ),
        cause=(
            "So a wrong answer is nearly always a wrong or missing entry rather "
            "than the agent inventing something, and that's fixable."
        ),
        question=(
            "Paste me what was asked and what it said, word for word. From those "
            "two I can tell you which entry it came from, and what to change so "
            "it stops."
        ),
        signals=["wrong answers reported"],
    )


def _unclear(facts: SetupFacts) -> Diagnosis:
    """Something is wrong and we have not been told what.

    The branch that most wants to be an escalation and least should be. "It's not
    working" is the most common opening line of a support conversation and the
    least informative, and the answer is one good question — narrowed by what we
    can already see, so it is not the same question we would ask anybody.
    """
    if facts.widget_never_seen:
        return Diagnosis(
            symptom=SYMPTOM_UNCLEAR,
            finding=(
                "One thing I can already see: the code has never loaded from "
                "your site, so whatever else is going on, it isn't live on a "
                "published page yet."
            ),
            cause="That's usually the whole problem, and it's a quick one.",
            question=(
                "Have you pasted the snippet in and published the site? And what "
                "is the site built with — I'll give you the exact steps for it."
            ),
            signals=["problem unspecified", "widget never seen loading"],
        )

    return Diagnosis(
        symptom=SYMPTOM_UNCLEAR,
        finding=(
            "The code is loading from your site, so the install is fine — which "
            "means it's something more specific."
        ),
        cause="I need one detail to know which.",
        question=(
            "Which is it: the chat doesn't appear at all, it appears and doesn't "
            "answer, or it answers with the wrong thing?"
        ),
        signals=["problem unspecified", "widget seen loading"],
    )


def _listed(channels: tuple[str, ...]) -> str:
    """Channel codes as a buyer would say them."""
    names = {
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "web": "your website",
        "email": "email",
    }
    spoken = [names.get(channel, channel) for channel in channels]

    if not spoken:
        return "nothing"
    if len(spoken) == 1:
        return spoken[0]

    return ", ".join(spoken[:-1]) + f" and {spoken[-1]}"


def _platform_prompt() -> str:
    """The platforms we have steps for, named from the same table as the steps."""
    labels = [platform.label for platform in PLATFORMS]

    return ", ".join(labels[:-1]) + f", or {labels[-1]}?"
