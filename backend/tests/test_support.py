"""The support path: a customer's problem, resolved rather than forwarded.

Written against a stated standard rather than against the code, because the code
did not exist and the standard is the point: *"When a customer reports something
not working, it should ask clarifying questions, reason through likely causes,
and walk them through fixes step by step — not just acknowledge and hand off"*,
and *"Escalate to a human only when something genuinely requires a human
decision or access Nera doesn't have — not just because an issue takes several
steps to resolve."*

So the assertions come in three kinds, and the second two are the ones that
matter:

1. The symptom was read correctly.
2. **The answer changed with the facts.** A diagnosis that reads the same
   whatever is true of the customer's workspace is a checklist wearing a
   diagnosis's clothes, and a customer who has already tried the checklist gets
   nothing from it. Several tests here assert two different workspaces get
   *different* text for the same sentence, which is the only way to test that
   from the outside.
3. **It did not escalate.** ``needs_human`` is asserted False across every
   ordinary fault, and True only for money, unwinding a purchase, and the
   provisioning gap — because the easiest way to pass a support test suite is to
   hand everything to a person, and that is the behaviour being fixed.

The negative direction gets as much attention as the positive one. A support
module that reads too eagerly breaks selling to fix support, so the largest
single test here feeds the classifier every ordinary sales message and asserts it
claims none of them.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.conversation import STAGE_CLOSED_WON
from app.sales.agent import (
    RULE_DIAGNOSED,
    RULE_SUPPORT_ESCALATED,
    compose_reply,
)
from app.sales.scoping import Scope
from app.sales.support import (
    SYMPTOM_CANNOT_INSTALL,
    SYMPTOM_CHANNEL_MISSING,
    SYMPTOM_NO_REPLY,
    SYMPTOM_NOT_VISIBLE,
    SYMPTOM_UNCLEAR,
    SYMPTOM_WRONG_ANSWERS,
    SetupFacts,
    asks_for_a_person,
    diagnose,
    read_symptom,
)

NOW = datetime.now(UTC)


def facts(**overrides) -> SetupFacts:
    """A working, installed, web-only customer — then whatever the test changes.

    The base case is the boring one on purpose. Every test below is about one
    fact being different, and a helper that made each test restate all nine would
    hide which one it was.
    """
    base = dict(
        is_customer=True,
        agent_name="Ada",
        workspace_ready=True,
        has_widget_token=True,
        widget_last_seen=NOW - timedelta(minutes=3),
        bought_channels=("web",),
        live_channels=("web",),
        conversations_handled=8,
    )
    base.update(overrides)

    return SetupFacts(**base)


# ---------------------------------------------------------------------------
# Reading the complaint
# ---------------------------------------------------------------------------

# Grouped by what they are, so a pattern change that blurs two symptoms together
# fails on the pair rather than passing on both.
SYMPTOMS = [
    (SYMPTOM_NOT_VISIBLE, "the widget is not showing on my site"),
    (SYMPTOM_NOT_VISIBLE, "I pasted the code but nothing shows"),
    (SYMPTOM_NOT_VISIBLE, "chat bubble isn't appearing"),
    (SYMPTOM_NOT_VISIBLE, "I can't see the chat anywhere on my page"),
    (SYMPTOM_NOT_VISIBLE, "the icon is missing"),
    (SYMPTOM_NO_REPLY, "the chat is there but it doesn't reply"),
    (SYMPTOM_NO_REPLY, "I typed a message and nothing happens"),
    (SYMPTOM_NO_REPLY, "my agent stopped replying"),
    (SYMPTOM_NO_REPLY, "no response when I send anything"),
    (SYMPTOM_WRONG_ANSWERS, "it gave the wrong price to a customer"),
    (SYMPTOM_WRONG_ANSWERS, "the answers are nonsense"),
    (SYMPTOM_WRONG_ANSWERS, "it's making things up"),
    (SYMPTOM_WRONG_ANSWERS, "the price it quoted was wrong"),
    (SYMPTOM_CANNOT_INSTALL, "how do I install this"),
    (SYMPTOM_CANNOT_INSTALL, "where do I paste the snippet"),
    (SYMPTOM_CANNOT_INSTALL, "I don't know how to add the code"),
    (SYMPTOM_CANNOT_INSTALL, "I never received the snippet"),
    (SYMPTOM_CHANNEL_MISSING, "where is my telegram bot"),
    (SYMPTOM_CHANNEL_MISSING, "whatsapp is not set up"),
    (SYMPTOM_CHANNEL_MISSING, "I paid for telegram but there's no bot"),
    (SYMPTOM_UNCLEAR, "it's not working"),
    (SYMPTOM_UNCLEAR, "something is wrong"),
    (SYMPTOM_UNCLEAR, "what's wrong with it"),
    (SYMPTOM_UNCLEAR, "it stopped working"),
]


@pytest.mark.parametrize(("expected", "message"), SYMPTOMS)
def test_a_complaint_is_read_as_the_problem_it_describes(expected, message):
    assert read_symptom(message) == expected


# Every one of these is something a buyer says on the way to paying, and the
# support module must claim none of them.
#
# This is the largest block in the file because it is the expensive direction. A
# missed symptom costs one clumsy reply; a stolen sales message costs the sale —
# a buyer answering "telegram and whatsapp" and being told their Telegram bot is
# being looked into by the team has been thrown out of the purchase entirely.
NOT_SUPPORT = [
    "hi",
    "hello",
    "what can you build",
    "who are you",
    "what is nera",
    "how much for a sales agent",
    "I run a bakery",
    "I'm running a food store",
    "AI for my clothing business, 2k conversations/month on WhatsApp and Telegram",
    "Profit and more customers of course",
    "do you integrate with shopify",
    "can you give me a discount",
    "I want to buy the sales rep",
    "the sales one",
    "both",
    # Channel answers. The exact shape that used to read as a complaint that a
    # paid-for channel had never been provisioned.
    "telegram and whatsapp",
    "telegram only, no whatsapp",
    "no whatsapp, just telegram",
    "web only, no telegram or whatsapp",
    "just whatsapp",
    "I need telegram",
    # Volume, language, integration and contact answers.
    "2000",
    "5000 conversations a month",
    "we need it in english and yoruba",
    "no integrations",
    "my email is bob@example.com",
    # Payment status. Handled by the paid-patterns branch, and must not be
    # intercepted here on the way.
    "I paid",
    "done",
    "confirmed",
    "yes",
    "no",
]


@pytest.mark.parametrize("message", NOT_SUPPORT)
def test_an_ordinary_sales_message_is_not_read_as_a_problem(message):
    assert read_symptom(message) is None


PERSON_OWNS_THESE = [
    "I want a refund",
    "I was charged twice",
    "please cancel my subscription",
    "I need to change my order",
    "can I downgrade my plan",
    "this is a scam",
]


@pytest.mark.parametrize("message", PERSON_OWNS_THESE)
def test_money_and_unwinding_a_purchase_belong_to_a_person(message):
    assert asks_for_a_person(message) is True


# An upsell is not a support ticket. Routing "I want to add a support agent" to a
# human puts a queue in front of money coming in, which is the opposite of the
# job.
WANTS_TO_SPEND_MORE = [
    "can I upgrade to add whatsapp",
    "I want to add a support agent too",
    "how much to also get the support one",
]


@pytest.mark.parametrize("message", WANTS_TO_SPEND_MORE)
def test_wanting_to_buy_more_is_not_handed_to_a_person(message):
    assert asks_for_a_person(message) is False


# ---------------------------------------------------------------------------
# The answer depends on the facts
# ---------------------------------------------------------------------------


def test_a_widget_that_never_loaded_is_told_so():
    """The claim the last-seen column was added to make.

    "I've checked" is only worth saying if something was checked, and this is the
    assertion that it was.
    """
    diagnosis = diagnose(SYMPTOM_NOT_VISIBLE, facts(widget_last_seen=None))

    assert "never" in diagnosis.finding.lower()
    assert diagnosis.needs_human is False


def test_a_widget_that_is_loading_is_not_told_to_check_the_install():
    """The other half, and the one a frustrated customer notices.

    Somebody whose snippet is demonstrably running does not need to be asked
    whether they pasted it in. Being asked is what makes a support bot feel like
    a wall.
    """
    diagnosis = diagnose(SYMPTOM_NOT_VISIBLE, facts())

    assert "loading" in diagnosis.finding.lower()
    assert "never" not in diagnosis.finding.lower()
    assert diagnosis.needs_human is False


def test_the_same_complaint_gets_a_different_answer_from_a_different_workspace():
    """The property that separates a diagnosis from a checklist.

    Asserted as a difference rather than against fixed strings, because the copy
    will be rewritten and the property must survive that. If these two ever match,
    the facts have stopped being read and nothing else in this file would notice.
    """
    never = diagnose(SYMPTOM_NOT_VISIBLE, facts(widget_last_seen=None))
    loading = diagnose(SYMPTOM_NOT_VISIBLE, facts())

    assert never.render() != loading.render()
    assert never.cause != loading.cause


def test_an_install_that_worked_and_stopped_is_told_that_it_stopped():
    """A theme update overwriting the snippet, which is its own story.

    Neither "never installed" nor "working fine" — and reading it as either sends
    the customer to the wrong place.
    """
    diagnosis = diagnose(
        SYMPTOM_NOT_VISIBLE, facts(widget_last_seen=NOW - timedelta(days=9))
    )

    assert "not in the last day" in diagnosis.finding
    assert diagnosis.needs_human is False


def test_a_build_that_has_not_finished_says_so_before_anything_else():
    """The fault is ours, and saying so first stops a pointless hunt.

    Not an escalation: a workspace mid-provision is a normal state with a known
    end, and putting a person in the loop to say "it is still building" fills a
    queue with rows nobody needs to read.
    """
    diagnosis = diagnose(SYMPTOM_NOT_VISIBLE, facts(workspace_ready=False))

    assert "hasn't finished" in diagnosis.finding
    assert "nothing is wrong on your end" in diagnosis.finding
    assert diagnosis.needs_human is False


@pytest.mark.parametrize(
    "symptom",
    [
        SYMPTOM_NOT_VISIBLE,
        SYMPTOM_NO_REPLY,
        SYMPTOM_CANNOT_INSTALL,
        SYMPTOM_UNCLEAR,
    ],
)
def test_an_unfinished_build_explains_itself_whatever_was_reported(symptom):
    """Because every other answer would be advice about installing nothing."""
    diagnosis = diagnose(symptom, facts(workspace_ready=False))

    assert "hasn't finished" in diagnosis.finding


def test_a_working_agent_is_used_as_proof_when_it_will_not_reply():
    """Evidence, quoted back.

    An agent that has answered other people works, and that single fact moves the
    problem from the setup to this page or this browser. It is also the most
    reassuring thing we can truthfully say.
    """
    diagnosis = diagnose(SYMPTOM_NO_REPLY, facts(conversations_handled=41))

    assert "41" in diagnosis.finding
    assert diagnosis.needs_human is False


def test_a_first_conversation_is_not_described_as_a_working_agent():
    """The same branch, told the truth in the other direction."""
    diagnosis = diagnose(SYMPTOM_NO_REPLY, facts(conversations_handled=0))

    assert "you'd be the first" in diagnosis.finding
    assert diagnosis.needs_human is False


def test_a_known_platform_gets_its_own_steps_and_not_a_menu():
    """Six sets of instructions is the same as none."""
    diagnosis = diagnose(SYMPTOM_CANNOT_INSTALL, facts(platform="shopify"))
    rendered = diagnosis.render()

    assert "theme.liquid" in rendered
    assert "WordPress" not in rendered
    assert diagnosis.needs_human is False


def test_an_unknown_platform_is_asked_for_rather_than_guessed():
    diagnosis = diagnose(SYMPTOM_CANNOT_INSTALL, facts(platform=""))

    assert "WordPress" in diagnosis.question
    assert diagnosis.question.endswith(
        "If you're not sure, tell me the address and I'll work it out."
    )
    assert diagnosis.needs_human is False


def test_wrong_answers_are_explained_rather_than_forwarded():
    """A wrong answer is a wrong entry, and that is fixable by the customer.

    The one branch with no steps in it, deliberately: the useful next move is to
    see the actual exchange, and guessing at fixes before that would be the
    generic scripting this whole module exists to replace.
    """
    diagnosis = diagnose(SYMPTOM_WRONG_ANSWERS, facts())

    assert "Ada" in diagnosis.finding
    assert "word for word" in diagnosis.question
    assert diagnosis.needs_human is False


def test_every_diagnosis_either_gives_steps_or_asks_something():
    """No branch is allowed to be an acknowledgement.

    "Sorry to hear that, I'm looking into it" is the reply this module was written
    to make impossible, and a branch with neither steps nor a question is exactly
    that reply.
    """
    for symptom, _ in SYMPTOMS:
        for workspace in (facts(), facts(widget_last_seen=None)):
            diagnosis = diagnose(symptom, workspace)

            assert diagnosis.steps or diagnosis.question, (symptom, diagnosis)


# ---------------------------------------------------------------------------
# When a person is genuinely required
# ---------------------------------------------------------------------------


def test_a_channel_that_was_paid_for_and_never_built_is_owned_not_explained():
    """The one fact-driven escalation, and the honest one.

    Provisioning issues a website widget and nothing else. A customer who paid
    the Telegram add-on has bought something we do not yet create, and no
    walkthrough fixes that — so the reply says it is on us and raises it.

    Sending them to @BotFather to build their own would be worse than escalating:
    charging for something and then asking the customer to make it.
    """
    diagnosis = diagnose(
        SYMPTOM_CHANNEL_MISSING,
        facts(bought_channels=("web", "telegram"), live_channels=("web",)),
    )

    assert diagnosis.needs_human is True
    assert "Telegram" in diagnosis.finding
    assert "on us" in diagnosis.cause


def test_a_channel_complaint_with_nothing_owed_is_worked_through_instead():
    """Same sentence, different facts, and now nothing to escalate."""
    diagnosis = diagnose(
        SYMPTOM_CHANNEL_MISSING,
        facts(bought_channels=("web",), live_channels=("web",)),
    )

    assert diagnosis.needs_human is False
    assert diagnosis.question


def test_a_ready_workspace_with_no_snippet_issued_is_our_problem():
    """Ready, and nothing to install. Not something to ask the customer about."""
    diagnosis = diagnose(SYMPTOM_NOT_VISIBLE, facts(has_widget_token=False))

    assert diagnosis.needs_human is True
    assert "gap on our side" in diagnosis.finding


def test_nothing_else_needs_a_human():
    """The standard, asserted directly.

    Everything an ordinary fault can look like, across both a never-installed and
    a working workspace, and none of it reaches a person. When a branch is added
    that escalates, this test is where the argument for it has to be made.
    """
    escalating = [
        (symptom, workspace_name)
        for symptom, _ in SYMPTOMS
        for workspace_name, workspace in (
            ("installed", facts()),
            ("never installed", facts(widget_last_seen=None)),
            ("no conversations yet", facts(conversations_handled=0)),
        )
        if diagnose(symptom, workspace).needs_human
    ]

    assert escalating == []


# ---------------------------------------------------------------------------
# Through the engine
# ---------------------------------------------------------------------------


def test_a_customer_reporting_a_fault_is_not_asked_what_they_want_to_buy():
    """The defect that started this, asserted at the level it happened.

    Before the support path existed, this exact call returned
    ``scoping_the_build`` and a body asking which product the customer would like.
    They had already bought it.
    """
    reply = compose_reply(
        "the widget is not showing on my site",
        STAGE_CLOSED_WON,
        scope=Scope(),
        setup=facts(widget_last_seen=None),
    )

    assert reply.reasoning.rule == RULE_DIAGNOSED
    assert reply.reasoning.escalated is False
    assert reply.needs_approval is False
    # The literal copy that went to a paying customer. Asserted as strings
    # because it is the wrongness of these particular sentences, in this
    # particular situation, that is being fixed.
    assert "Which of these do you need?" not in reply.body
    assert "price this on what you actually need" not in reply.body


def test_a_prospect_saying_the_same_thing_is_unaffected():
    """The gate, tested from outside.

    Nothing about the sales path may change because support was added, and the
    cheap way to guarantee that is for a conversation with no paid order behind it
    never to reach any of it.
    """
    reply = compose_reply(
        "the widget is not showing on my site",
        STAGE_CLOSED_WON,
        scope=Scope(),
    )

    assert reply.reasoning.rule != RULE_DIAGNOSED
    assert reply.reasoning.rule != RULE_SUPPORT_ESCALATED


def test_a_refund_request_reaches_a_person_with_the_message_attached():
    reply = compose_reply(
        "I want a refund, the widget never worked",
        STAGE_CLOSED_WON,
        scope=Scope(),
        setup=facts(),
    )

    assert reply.reasoning.rule == RULE_SUPPORT_ESCALATED
    assert reply.needs_approval is True
    assert reply.approval_request == "I want a refund, the widget never worked"


def test_a_refund_request_is_not_answered_with_install_steps():
    """Checked before the symptom for exactly this reason.

    The sentence contains a widget complaint. Reading it as one and replying with
    a troubleshooting checklist is the specific way support bots insult people who
    are already unhappy.
    """
    reply = compose_reply(
        "I want a refund, the widget never worked",
        STAGE_CLOSED_WON,
        scope=Scope(),
        setup=facts(widget_last_seen=None),
    )

    assert "Ctrl+Shift+R" not in reply.body
    assert "Footer" not in reply.body


def test_a_customer_who_wants_to_buy_more_still_gets_sold_to():
    """A customer is still a buyer.

    The support gate opens on a paid order, so every one of these conversations
    has one — and if that gate swallowed purchase intent, the support path would
    have closed the upsell channel to fix the complaint channel.
    """
    reply = compose_reply(
        "how much to add a support agent as well",
        STAGE_CLOSED_WON,
        scope=Scope(),
        setup=facts(),
    )

    assert reply.reasoning.rule != RULE_SUPPORT_ESCALATED
    assert reply.reasoning.escalated is False
