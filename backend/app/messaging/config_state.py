"""Configuration state for interactive scoping on chat surfaces.

The agent's ``Scope`` is the source of truth for what the buyer has answered —
this module holds only what the *UI* needs that the Scope does not: which
options a buyer has toggled in a multi-select step before confirming, and what
step a chat is currently on so a bare "2" can be routed to the right parser.

Everything here is keyed by conversation id, so two buyers can never see each
other's toggles. It is deliberately not persisted: a chat that goes quiet for
an hour restarts with a clean slate, which is the behaviour a buyer who comes
back to an abandoned thread expects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class SelectionState:
    """The interactive state of one chat's configuration flow."""

    # The step currently being presented (e.g. "channels").
    step: str | None = None
    # Values toggled for a multi-select step. Order is preserved so the
    # rendered list can show them in the same order as the catalog.
    selected: list[str] = field(default_factory=list)
    # A free-text answer being composed across several messages. Unused until
    # we need it — present so the shape is stable.
    draft: str = ""

    def toggle(self, value: str) -> bool:
        """Toggle a value in the selection. Returns True if now selected."""
        if value in self.selected:
            self.selected.remove(value)
            return False
        self.selected.append(value)
        return True

    def is_selected(self, value: str) -> bool:
        return value in self.selected

    def reset(self, step: str | None = None) -> None:
        self.step = step
        self.selected = []
        self.draft = ""


class ConfigurationStore:
    """Per-conversation interactive configuration state.

    Process-local. A deployment running several poller workers would need this
    in a shared store; for a single poller (the current deployment) a dict is
    correct and keeps the failure mode to "buyer restarts the step" rather than
    "two workers race and one buyer sees the other's toggles".
    """

    def __init__(self) -> None:
        self._states: dict[int, SelectionState] = {}
        self._lock = Lock()

    def get(self, conversation_id: int) -> SelectionState:
        with self._lock:
            if conversation_id not in self._states:
                self._states[conversation_id] = SelectionState()
            return self._states[conversation_id]

    def start_step(self, conversation_id: int, step: str) -> SelectionState:
        with self._lock:
            state = self._states.get(conversation_id) or SelectionState()
            state.reset(step)
            self._states[conversation_id] = state
            return state

    def clear(self, conversation_id: int) -> None:
        with self._lock:
            self._states.pop(conversation_id, None)


# Module-level store shared by the service and the poller. Tests construct
# their own to keep cases isolated.
store = ConfigurationStore()
