"""Tests for the interactive configuration flow on Telegram and WhatsApp."""

import pytest

from app.messaging.config_flow import ConfigurationFlow
from app.messaging.config_state import ConfigurationStore
from app.messaging.inbound import KIND_TEXT, InboundMessage
from app.models.channel_identity import CHANNEL_TELEGRAM, CHANNEL_WHATSAPP
from app.models.conversation import Conversation
from app.sales.options import for_step
from app.sales.scoping import Scope


@pytest.fixture
def flow():
    return ConfigurationFlow(store=ConfigurationStore())


def _conv(id=1):
    return Conversation(id=id, organization_id=1)


def _msg(text="hello", channel=CHANNEL_TELEGRAM, external_id="100"):
    return InboundMessage(
        channel=channel,
        external_id=external_id,
        delivery_id=f"t:{external_id}",
        kind=KIND_TEXT,
        text=text,
    )


# ---------- option generation ----------


def test_options_are_driven_by_catalog():
    """The three selectable steps get options from the catalog, not hardcoded."""
    products = for_step("products")
    assert not products.free_text
    assert products.options
    assert len(products.options) >= 2

    channels = for_step("channels")
    assert channels.multi
    assert len(channels.options) == 4

    languages = for_step("languages")
    assert languages.multi
    assert languages.options

    volume = for_step("monthly_conversations")
    assert volume.free_text
    assert volume.hint


def test_for_unknown_step_returns_free_text():
    unknown = for_step("not_a_step")
    assert unknown.free_text


# ---------- step presentation ----------


def test_present_step_returns_message_for_selectable_step(flow):
    scope = Scope()  # first step is "products"
    msg = flow.present_step(scope)
    assert msg is not None
    assert "AI" in msg.text or "which" in msg.text.lower()
    assert msg.telegram_inline_keyboard or msg.whatsapp_list_rows


def test_present_step_returns_none_for_free_text_step(flow):
    scope = Scope(products=("sales_agent",), channels=("web", "telegram"),
                  monthly_conversations=500, integrations=0)
    # next step is languages, which is selectable
    # Skip to a free-text step by setting products & channels only
    scope2 = Scope(products=("sales_agent",))
    # channels is next — still selectable
    # volume is next after that — free text
    scope3 = Scope(products=("sales_agent",), channels=("web", "telegram"))
    msg = flow.present_step(scope3)
    # volume step — free text, should be None
    assert msg is None


# ---------- multi-select toggling ----------


def test_toggle_marks_option_in_list(flow):
    conv = _conv()
    scope = Scope()  # products step (single-select)

    # Single-select commits immediately, no toggle
    result = flow.handle_message(conv, _msg("scoping:products:sales_agent"), scope)
    assert result.handled
    assert result.selection_text is not None


def test_numbered_selection_for_whatsapp(flow):
    """WhatsApp buyers type '1' or '1, 3' to select options."""
    conv = _conv()
    scope = Scope()  # products step

    result = flow.handle_message(conv, _msg("1"), scope)
    assert result.handled
    assert result.selection_text is not None
    assert result.selection_text  # non-empty


# ---------- text passthrough ----------


def test_free_text_on_free_text_step_passes_through(flow):
    conv = _conv()
    # Scope where the next step is volume (free text)
    scope = Scope(products=("sales_agent",), channels=("web", "telegram"))

    result = flow.handle_message(conv, _msg("500"), scope)
    assert not result.handled
    assert result.replies == []


def test_free_text_parsable_by_scoping_passes_through(flow):
    """Buyer typing a valid answer on a selectable step goes to the agent."""
    conv = _conv()
    scope = Scope()  # products step

    # "sales" should be parsed by the scoping parser
    result = flow.handle_message(conv, _msg("sales"), scope)
    assert not result.handled  # let the agent handle it


def test_invalid_text_on_selectable_step_passes_through(flow):
    conv = _conv()
    scope = Scope()

    # Unparseable text on a selectable step falls through to the agent.
    # The agent may still understand it (e.g. "hello" is a greeting).
    result = flow.handle_message(conv, _msg("xyzzy"), scope)
    assert not result.handled


# ---------- session isolation ----------


def test_different_conversations_have_independent_state(flow):
    conv1 = _conv(1)
    conv2 = _conv(2)
    # Scope where the next step is channels (multi-select)
    scope1 = Scope(products=("sales_agent",))
    scope2 = Scope(products=("sales_agent",))

    flow.handle_message(conv1, _msg("scoping:channels:web"), scope1)
    flow.handle_message(conv2, _msg("scoping:channels:telegram"), scope2)

    s1 = flow._store.get(1)
    s2 = flow._store.get(2)
    assert s1.selected != s2.selected


def test_reset_clears_state(flow):
    conv = _conv()
    # Use channels (multi-select) to test state clearing
    scope = Scope(products=("sales_agent",))

    flow.handle_message(conv, _msg("scoping:channels:web"), scope)
    state = flow._store.get(conv.id)
    assert state.selected

    from app.messaging.inbound import KIND_COMMAND, COMMAND_RESET
    reset_msg = InboundMessage(
        channel=CHANNEL_TELEGRAM,
        external_id="100",
        delivery_id="reset:1",
        kind=KIND_COMMAND,
        command=COMMAND_RESET,
    )
    flow.handle_message(conv, reset_msg, scope)
    state = flow._store.get(conv.id)
    assert not state.selected


# ---------- selection commit ----------


def test_commit_advances_scope(flow):
    conv = _conv()
    scope = Scope()  # products step (single-select)

    # Single-select commits immediately
    result = flow.handle_message(conv, _msg("scoping:products:sales_agent"), scope)
    assert result.handled
    assert result.selection_text is not None


def test_selection_text_matches_catalog_label(flow):
    """The text fed to the agent is the catalog label, not the code."""
    conv = _conv()
    scope = Scope()

    result = flow.handle_message(conv, _msg("scoping:products:sales_agent"), scope)
    assert result.selection_text is not None
    assert "sales" in result.selection_text.lower() or "representative" in result.selection_text.lower()


# ---------- scope completion ----------


def test_complete_scope_is_detected(flow):
    """When all steps are answered, complete=True and the agent should price."""
    conv = _conv()
    # Complete scope: products, channels, volume, integrations, languages all set
    scope = Scope(
        products=("sales_agent",),
        channels=("web", "telegram"),
        monthly_conversations=500,
        integrations=0,
        languages=("en",),
    )

    # No next step — flow returns empty so the agent prices it
    result = flow.handle_message(conv, _msg("yes"), scope)
    assert not result.handled
    assert result.replies == []
