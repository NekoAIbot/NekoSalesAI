"""Interactive configuration flow for Telegram and WhatsApp.

Sits between the messaging pipe and the sales agent. On scoping steps that
have bounded options (products, channels, languages) it presents buttons /
lists the buyer can tap instead of typing. On free-text steps (volume,
integrations) it falls through to the agent unchanged.

The agent is still the source of truth for the words; this class only adds
controls to the reply and routes the buyer's selections back into the
conversation as the text the scoping parser expects.

The flow never calls the agent itself. It returns either a list of channel
messages to send immediately (a step rendered with controls) or a selection
text for the caller to feed to the agent. This keeps the messaging service
in control of the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.messaging.config_state import ConfigurationStore, SelectionState, store as _default_store
from app.messaging.presentation import ChannelMessage, parse_callback, render_step
from app.messaging.inbound import (
    COMMAND_RESET,
    COMMAND_START,
    KIND_COMMAND,
    KIND_TEXT,
    InboundMessage,
)
from app.models.conversation import Conversation
from app.sales.options import for_step
from app.sales.scoping import Scope, answer as scoping_answer


@dataclass
class FlowResult:
    """What the flow produced for one message."""

    # Messages to send, in order. Empty means "nothing to say".
    replies: list[ChannelMessage]
    # When True the agent should not be consulted with the original message
    # text — the flow has handled the message itself.
    handled: bool = False
    # When not None, the caller should feed THIS text to the agent instead of
    # the original message. Set when the buyer completes a selection.
    selection_text: str | None = None
    # When True the scope is now complete and the agent should price it.
    complete: bool = False


class ConfigurationFlow:
    """One buyer's interactive configuration, keyed by conversation id.

    The flow is *stateless about the product* — it reads the catalog via
    ``for_step`` and the current scope from the conversation. What it tracks
    is purely UI state: which options are toggled for a multi-select step.
    """

    def __init__(self, store: ConfigurationStore | None = None) -> None:
        self._store = store or _default_store

    # ---------- entry ----------

    def handle_message(
        self,
        conversation: Conversation,
        message: InboundMessage,
        scope: Scope,
    ) -> FlowResult:
        """One message from the buyer, with the conversation's current scope.

        Only intercepts messages that ARE selections (callbacks, numbered
        lists). Free text always falls through to the agent.
        """
        if message.kind == KIND_COMMAND:
            return self._handle_command(conversation, message, scope)

        if message.kind != KIND_TEXT:
            return FlowResult(replies=[])

        step = scope.next_step

        # If scope is complete or step is free-text, let the agent handle it.
        if step is None:
            return FlowResult(replies=[])

        options = for_step(step)
        if options.free_text:
            return FlowResult(replies=[])

        # Track state for the current selectable step.
        state = self._store.get(conversation.id)
        if state.step != step:
            state = self._store.start_step(conversation.id, step)

        # 1) Telegram inline keyboard callback?
        parsed = parse_callback(message.text.strip())
        if parsed is not None:
            cb_step, value = parsed
            if cb_step == step and value == "__next__":
                return self._commit_selection(conversation.id, scope, state)
            if cb_step == step:
                if options.multi:
                    return self._toggle(conversation.id, scope, state, value)
                else:
                    state.selected = [value]
                    return self._commit_selection(conversation.id, scope, state)

        # 2) WhatsApp numbered selection like "1" or "1, 3"?
        numbered = self._parse_numbered_selection(message.text, options)
        if numbered is not None:
            state.selected = numbered
            if options.multi:
                # Re-render with the new selection for the buyer to confirm.
                return FlowResult(
                    replies=[self._render_step(scope, state)],
                    handled=True,
                )
            else:
                return self._commit_selection(conversation.id, scope, state)

        # 3) Not a selection — let the agent read the words.
        return FlowResult(replies=[])

    def present_step(
        self,
        scope: Scope,
    ) -> ChannelMessage | None:
        """Render the current scoping step with interactive controls.

        Returns None if the step is free-text or the scope is complete.
        """
        step = scope.next_step
        if step is None:
            return None
        options = for_step(step)
        if options.free_text or not options.options:
            return None

        # present_step is called when the agent has just advanced to a new
        # step. We don't have a conversation id here, so we render without
        # per-conversation selection state — the first render is always clean.
        state = SelectionState(step=step)
        return self._render_step(scope, state)

    # ---------- commands ----------

    def _handle_command(
        self,
        conversation: Conversation,
        message: InboundMessage,
        scope: Scope,
    ) -> FlowResult:
        if message.command in (COMMAND_RESET, COMMAND_START):
            self._store.clear(conversation.id)
            return FlowResult(replies=[])
        return FlowResult(replies=[])

    # ---------- selections ----------

    def _toggle(
        self,
        conversation_id: int,
        scope: Scope,
        state: SelectionState,
        value: str,
    ) -> FlowResult:
        """Toggle an option in a multi-select step and re-render."""
        state.toggle(value)
        return FlowResult(
            replies=[self._render_step(scope, state)],
            handled=True,
        )

    def _commit_selection(
        self,
        conversation_id: int,
        scope: Scope,
        state: SelectionState,
    ) -> FlowResult:
        """Turn the buyer's selection into text the scoping parser expects.

        Returns a ``FlowResult`` with ``selection_text`` set so the caller can
        feed it to the agent. The caller is responsible for checking whether
        the scope is now complete.
        """
        step = state.step
        if step is None or not state.selected:
            # Nothing selected — re-render the step so the buyer can pick.
            return FlowResult(
                replies=[self._render_step(scope, state)],
                handled=True,
            )

        # Build the text the scoping parser expects: comma-separated labels.
        options = for_step(step)
        by_value = {opt.value: opt.label for opt in options.options}
        labels = [by_value.get(v, v) for v in state.selected]
        text = ", ".join(labels)

        new_scope = scoping_answer(scope, step, text)
        if new_scope is None:
            # The parser did not recognise the selection — re-render.
            return FlowResult(
                replies=[self._render_step(scope, state)],
                handled=True,
            )

        # Clear the UI state; the caller will feed the selection to the agent.
        self._store.clear(conversation_id)

        return FlowResult(
            replies=[],
            handled=True,
            selection_text=text,
            complete=new_scope.next_step is None,
        )

    def _parse_numbered_selection(
        self,
        text: str,
        options,
    ) -> list[str] | None:
        """Parse "1" or "1, 3, 4" as a selection from the option list.

        Returns None if the text does not look like a numbered selection.
        """
        import re

        if not re.fullmatch(r"[\d,\s]+", text.strip()):
            return None

        try:
            indices = [int(p.strip()) for p in text.split(",") if p.strip()]
        except ValueError:
            return None

        if not indices:
            return None

        result = []
        for i in indices:
            if 1 <= i <= len(options.options):
                result.append(options.options[i - 1].value)
        return result if result else None

    def _is_numbered_selection(self, text: str, options) -> bool:
        """Check if the text looks like a numbered selection without parsing."""
        return self._parse_numbered_selection(text, options) is not None

    # ---------- rendering ----------

    def _render_step(
        self,
        scope: Scope,
        state: SelectionState,
    ) -> ChannelMessage:
        """Render a scoping step with the buyer's current selection marked."""
        step = scope.next_step or state.step or "products"

        question = scope.question() or ""

        # Show what the buyer has selected so far for multi-select steps.
        options = for_step(step)
        if state.selected and options.multi:
            by_value = {opt.value: opt.label for opt in options.options}
            selected_labels = [by_value.get(v, v) for v in state.selected]
            question = f"{question}\n\nSelected: {', '.join(selected_labels)}"

        msg = render_step(question, step)

        # For multi-select, mark selected options with a ✓ in the Telegram
        # keyboard. Tuples of dicts are frozen; rebuild with marks.
        if options.multi and msg.telegram_inline_keyboard:
            marked_rows = []
            for row in msg.telegram_inline_keyboard:
                new_row = []
                for btn in row:
                    cb = btn.get("callback_data", "")
                    parsed = parse_callback(cb)
                    if parsed is not None and parsed[1] in state.selected:
                        new_btn = dict(btn)
                        if not btn["text"].startswith("✓"):
                            new_btn["text"] = f"✓ {btn['text']}"
                        new_row.append(new_btn)
                    else:
                        new_row.append(dict(btn))
                marked_rows.append(tuple(new_row))
            msg = ChannelMessage(
                text=msg.text,
                telegram_inline_keyboard=tuple(marked_rows),
                whatsapp_list_rows=msg.whatsapp_list_rows,
                whatsapp_list_header=msg.whatsapp_list_header,
                whatsapp_list_button=msg.whatsapp_list_button,
                free_text=msg.free_text,
            )

        return msg
