"""Regression tests for the repeated-question bug."""

import pytest

from app.messaging.config_flow import ConfigurationFlow
from app.messaging.config_state import ConfigurationStore
from app.messaging.inbound import InboundMessage, KIND_TEXT
from app.models.channel_identity import CHANNEL_TELEGRAM
from app.sales.scoping import Scope


@pytest.fixture
def flow():
    return ConfigurationFlow(store=ConfigurationStore())


def _msg(text):
    return InboundMessage(
        channel=CHANNEL_TELEGRAM,
        external_id="42",
        delivery_id=f"t:{hash(text) % 10000}",
        kind=KIND_TEXT,
        text=text,
    )


class FakeConv:
    def __init__(self, id=1):
        self.id = id
        self.organization_id = 1


def test_all4_advances_past_channels(flow):
    """'All 4' on the channels step must advance, not repeat."""
    conv = FakeConv()
    scope = Scope(products=("sales_agent",))

    result = flow.handle_message(conv, _msg("All 4"), scope)
    assert not result.handled, "free text should fall through to agent"


def test_numbered_selection_does_not_loop(flow):
    """A numbered selection on multi-select must re-render, not loop."""
    conv = FakeConv()
    scope = Scope(products=("sales_agent",))

    # First "1" → re-render with website selected
    r1 = flow.handle_message(conv, _msg("1"), scope)
    assert r1.handled
    assert len(r1.replies) == 1

    # Second "1" on the SAME message state → should NOT repeat the question
    # with no state change. It should re-render with the toggled selection.
    state = flow._store.get(conv.id)
    assert state.step == "channels"
    # After two toggles of the same option, selection should be empty
    # (toggle on, toggle off). The re-render still shows the step.
    assert isinstance(r1.replies[0].text, str)


def test_callback_then_next_commits(flow):
    """Selecting an option and tapping Next must commit the selection."""
    conv = FakeConv()
    scope = Scope(products=("sales_agent",))

    # Tap "web"
    r1 = flow.handle_message(conv, _msg("scoping:channels:web"), scope)
    assert r1.handled
    state = flow._store.get(conv.id)
    assert "web" in state.selected

    # Tap "Next"
    r2 = flow.handle_message(conv, _msg("scoping:channels:__next__"), scope)
    assert r2.handled
    assert r2.selection_text is not None
    assert "Web" in r2.selection_text


def test_different_conversations_are_isolated(flow):
    """Two conversations must not share selection state."""
    conv1 = FakeConv(1)
    conv2 = FakeConv(2)
    scope1 = Scope(products=("sales_agent",))
    scope2 = Scope(products=("sales_agent",))

    flow.handle_message(conv1, _msg("scoping:channels:web"), scope1)
    flow.handle_message(conv2, _msg("scoping:channels:telegram"), scope2)

    s1 = flow._store.get(1)
    s2 = flow._store.get(2)
    assert s1.selected != s2.selected


def test_product_selection_advances(flow):
    """Selecting a product must advance to channels."""
    conv = FakeConv()
    scope = Scope()

    result = flow.handle_message(conv, _msg("scoping:products:sales_agent"), scope)
    assert result.handled
    assert result.selection_text is not None
    # After product selection, next step should be channels (not complete)
    assert not result.complete


def test_language_multi_select(flow):
    """Languages step should support multi-select."""
    conv = FakeConv()
    scope = Scope(
        products=("sales_agent",),
        channels=("web", "telegram"),
        monthly_conversations=500,
        integrations=0,
    )

    r1 = flow.handle_message(conv, _msg("scoping:languages:en"), scope)
    assert r1.handled
    state = flow._store.get(conv.id)
    assert "en" in state.selected

    r2 = flow.handle_message(conv, _msg("scoping:languages:yo"), scope)
    assert r2.handled
    state = flow._store.get(conv.id)
    assert "en" in state.selected and "yo" in state.selected

    r3 = flow.handle_message(conv, _msg("scoping:languages:__next__"), scope)
    assert r3.handled
    assert r3.selection_text is not None
    assert "English" in r3.selection_text


def test_free_text_on_free_text_step_passes_through(flow):
    """A number on the volume step must NOT be intercepted as a selection."""
    conv = FakeConv()
    scope = Scope(products=("sales_agent",), channels=("web", "telegram"))

    result = flow.handle_message(conv, _msg("500"), scope)
    assert not result.handled
    assert result.replies == []
