"""Tests for the LLM semantic-understanding layer.

Two halves:

1. ``llm_understanding`` — the client and its validation: aliases map to
   canonical codes, hallucinated values are dropped, unparseable output
   yields None, and the deterministic path is untouched when the key is
   missing.

2. The agent's LLM slow path — a fake client injects interpretations and
   the tests verify they are applied through the deterministic machinery,
   that low-confidence reads are ignored, and that every fallback still
   behaves exactly as before.
"""

import pytest

import app.sales.agent as agent_module
from app.sales.agent import compose_reply
from app.sales.context import ConversationMemory
from app.sales.llm_understanding import (
    SemanticResult,
    UnderstandingLLM,
    _extract_json,
    _validate,
    build_context_summary,
)
from app.sales.scoping import Scope


# ---------- validation ----------


def test_product_aliases_map_to_canonical_codes():
    r = _validate({"intent": "configuration", "products": ["sales", "support"]})
    # "sales" + "support" = both components = Workforce, per catalog logic.
    assert set(r.products) == {"sales_agent", "support_agent"}


def test_workforce_alias():
    r = _validate({"intent": "configuration", "products": ["workforce"]})
    assert r.products == ("workforce_agent",)


def test_hallucinated_product_is_dropped():
    r = _validate({"intent": "configuration", "products": ["crm_agent", "telepathy"]})
    assert r.products == ()


def test_hallucinated_channel_is_dropped():
    r = _validate({"intent": "configuration", "channels": ["sms", "fax", "whatsapp"]})
    assert r.channels == ("whatsapp",)


def test_hallucinated_language_is_dropped():
    r = _validate({"intent": "configuration", "languages": ["klingon", "yo"]})
    assert r.languages == ("yo",)


def test_volume_is_read_from_strings():
    r = _validate({"volume": "12,000"})
    assert r.volume == 12000


def test_unknown_intent_becomes_other():
    r = _validate({"intent": "sales_and_support"})
    assert r.intent == "other"


def test_confidence_is_clamped():
    r = _validate({"confidence": 7.5})
    assert r.confidence == 1.0
    r = _validate({"confidence": -2})
    assert r.confidence == 0.0


def test_remove_validates_against_channels_and_languages():
    r = _validate({"remove": ["hausa", "whatsapp", "mars"]})
    assert set(r.remove) == {"ha", "whatsapp"}


def test_json_extraction_handles_wrapper_prose():
    assert _extract_json('Sure! {"intent": "question"}') == {"intent": "question"}
    assert _extract_json('{"intent": "question"}') == {"intent": "question"}
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


# ---------- the client ----------


class FakeTransport:
    def __init__(self, content=None, status=200, fail=False):
        self.content = content
        self.status = status
        self.fail = fail
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs.get("json", {})))
        if self.fail:
            raise ConnectionError("network down")
        return _FakeResp(self.status, self.content)


class _FakeResp:
    def __init__(self, status, content):
        self.status_code = status
        self._content = content

    def json(self):
        if self._content is None:
            raise ValueError("no body")
        return {"choices": [{"message": {"content": self._content}}]}

    @property
    def text(self):
        return str(self._content)


def test_disabled_client_returns_none_without_calling():
    llm = UnderstandingLLM(api_key="")
    assert llm.enabled is False
    assert llm.understand("anything") is None


def test_failed_call_returns_none():
    llm = UnderstandingLLM(api_key="k", transport=FakeTransport(fail=True))
    assert llm.understand("hello") is None


def test_http_error_returns_none():
    llm = UnderstandingLLM(api_key="k", transport=FakeTransport(status=500))
    assert llm.understand("hello") is None


def test_unparseable_output_returns_none():
    llm = UnderstandingLLM(api_key="k", transport=FakeTransport(content="not json"))
    assert llm.understand("hello") is None


def test_successful_call_is_validated():
    llm = UnderstandingLLM(
        api_key="k",
        transport=FakeTransport(content='{"intent": "question", "topic": "orders", "confidence": 0.9}'),
    )
    r = llm.understand("can it take orders?")
    assert r is not None
    assert r.intent == "question"
    assert r.topic == "orders"
    assert r.from_llm is True


def test_context_summary_is_bounded_and_structured():
    mem = ConversationMemory()
    mem.remember("business", "business_type", "clothing", provenance="extracted")
    scope = Scope(products=("workforce_agent",))
    summary = build_context_summary(mem, scope)
    assert "clothing" in summary
    assert "workforce_agent" in summary
    assert "pending question: channels" in summary


# ---------- the agent slow path ----------


class FakeLLM:
    """An UnderstandingLLM stand-in returning a canned result."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    @property
    def enabled(self):
        return True

    def understand(self, message, context_summary=""):
        self.calls.append((message, context_summary))
        return self.result


@pytest.fixture
def llm_ctx():
    return {}


@pytest.fixture
def with_llm(monkeypatch):
    def _install(result):
        fake = FakeLLM(result)
        monkeypatch.setattr(agent_module, "_llm_client", fake)
        monkeypatch.setattr(agent_module, "_get_llm_client", lambda: fake)
        return fake

    yield _install
    monkeypatch.setattr(agent_module, "_llm_client", None)


def _complete_scope():
    return Scope(
        products=("workforce_agent",),
        channels=("web", "whatsapp"),
        monthly_conversations=12000,
        integrations=15,
        languages=("en", "yo", "ha", "ig", "pid"),
    )


def test_llm_correction_updates_scope_and_reprices(with_llm):
    """'Forget what I said about Hausa' via the LLM: scope updates, quote re-prices."""
    fake = with_llm(
        SemanticResult(intent="correction", remove=("ha",), confidence=0.95, from_llm=True)
    )
    reply = compose_reply(
        "Forget what I said about Hausa.",
        "qualified",
        scope=_complete_scope(),
        memory=ConversationMemory(),
    )
    assert "ha" not in reply.scope.languages
    assert len(reply.scope.languages) == 4
    # The quote was regenerated from the corrected scope.
    assert reply.quoted is not None
    assert reply.quoted.total_minor < _complete_scope_quote_total()
    assert fake.calls, "the LLM was actually consulted"


def _complete_scope_quote_total():
    from app.pricing.complexity import price

    return price(_complete_scope().to_requirement()).total_minor


def test_llm_volume_correction_overrides_stale_value(with_llm):
    with_llm(SemanticResult(intent="correction", volume=12000, confidence=0.95, from_llm=True))
    scope = Scope(
        products=("workforce_agent",),
        channels=("web",),
        monthly_conversations=25000,
        integrations=0,
        languages=("en",),
    )
    reply = compose_reply(
        "I said 12,000, not 25,000.",
        "qualified",
        scope=scope,
        memory=ConversationMemory(),
    )
    assert reply.scope.monthly_conversations == 12000


def test_low_confidence_llm_read_is_ignored(with_llm):
    """Below the confidence floor the deterministic fallback stands."""
    with_llm(SemanticResult(intent="correction", remove=("ha",), confidence=0.3, from_llm=True))
    reply = compose_reply(
        "Forget what I said about Hausa.",
        "qualified",
        scope=_complete_scope(),
        memory=ConversationMemory(),
    )
    # Scope untouched: 5 languages still.
    assert len(reply.scope.languages) == 5


def test_llm_question_answered_from_catalog(with_llm):
    """A semantically-read question is answered from PRODUCT_CAPABILITIES."""
    with_llm(
        SemanticResult(
            intent="question", topic="take orders", confidence=0.9, from_llm=True
        )
    )
    scope = Scope(products=("workforce_agent",))
    reply = compose_reply(
        "Can it basically run my sales side while I focus on the business?",
        "qualified",
        scope=scope,
        memory=ConversationMemory(),
    )
    assert "Paystack" in reply.body
    assert "Workforce" in reply.body
    # The pending question is preserved underneath.
    assert "Where should it answer" in reply.body
    # Scope untouched by a question.
    assert reply.scope.products == ("workforce_agent",)
    assert reply.scope.channels is None


def test_llm_configuration_answer_applies_through_deterministic_validation(with_llm):
    """A semantic channels answer lands on the scope like a typed one."""
    with_llm(
        SemanticResult(
            intent="configuration",
            channels=("whatsapp",),
            confidence=0.9,
            from_llm=True,
        )
    )
    scope = Scope(products=("workforce_agent",))
    reply = compose_reply(
        "Most of my buyers chat with me there on that green app",
        "qualified",
        scope=scope,
        memory=ConversationMemory(),
    )
    assert "whatsapp" in reply.scope.channels
    assert "web" in reply.scope.channels  # web always included


def test_llm_hallucinated_values_cannot_reach_the_scope(with_llm):
    """A hallucinated product code is dropped by validation before the scope."""
    # The validation happened in _validate; here the result carries only
    # canonical codes because that is what _validate produces. The agent
    # applies only what survived.
    with_llm(
        SemanticResult(
            intent="configuration",
            products=(),  # hallucinated codes were dropped upstream
            channels=("whatsapp",),
            confidence=0.9,
            from_llm=True,
        )
    )
    scope = Scope(channels=None)
    reply = compose_reply(
        "I want the telepathy agent on whatsapp",
        "qualified",
        scope=Scope(),
        memory=ConversationMemory(),
    )
    # Channels may apply; products stay unset because nothing valid was read.
    assert reply.scope.products is None


def test_llm_unavailable_falls_back_to_deterministic(monkeypatch):
    """No client -> the existing behaviour, byte for byte."""
    monkeypatch.setattr(agent_module, "_get_llm_client", lambda: None)
    scope = _complete_scope()
    reply = compose_reply(
        "hmm interesting",
        "qualified",
        scope=scope,
        memory=ConversationMemory(),
    )
    # The deterministic "could not read" path: same scope back, question re-asked.
    assert reply.scope == scope


def test_deterministic_fast_path_never_calls_the_llm(with_llm):
    """A message the deterministic engine reads fine skips the LLM entirely."""
    fake = with_llM = with_llm(
        SemanticResult(intent="configuration", channels=("whatsapp",), confidence=0.99, from_llm=True)
    )
    scope = Scope(products=("workforce_agent",))
    # "my website and whatsapp" is read deterministically — no LLM call.
    reply = compose_reply(
        "my website and whatsapp",
        "qualified",
        scope=scope,
        memory=ConversationMemory(),
    )
    assert fake.calls == []
    assert reply.scope.channels == ("web", "whatsapp")


def test_llm_products_both_components_become_workforce(with_llm):
    with_llm(
        SemanticResult(
            intent="configuration",
            products=("sales_agent", "support_agent"),
            confidence=0.95,
            from_llm=True,
        )
    )
    reply = compose_reply(
        "Actually, I need something for sales AND support.",
        "qualified",
        scope=Scope(),
        memory=ConversationMemory(),
    )
    assert reply.scope.products == ("workforce_agent",)


def test_a_pure_acknowledgement_never_calls_the_llm(with_llm):
    """\"continue\" after a quote is agreement, not a question or a correction.

    The completed-scope correction path used to send it to the LLM — a ~2.5s
    round-trip to interpret the one word a human never needs explained.
    """
    fake = with_llm(
        SemanticResult(intent="other", confidence=0.99, from_llm=True)
    )
    reply = compose_reply(
        "continue",
        "ready_to_buy",
        scope=_complete_scope(),
        memory=ConversationMemory(),
    )
    assert fake.calls == []
    assert reply.reasoning.rule == "courtesy"


def test_a_courtesy_acknowledgement_mid_scoping_never_calls_the_llm(with_llm):
    """\"okay\" mid-configuration is an acknowledgement, not a question."""
    fake = with_llm(
        SemanticResult(intent="question", confidence=0.99, from_llm=True)
    )
    reply = compose_reply(
        "okay",
        "qualified",
        scope=Scope(products=("workforce_agent",)),
        memory=ConversationMemory(),
    )
    assert fake.calls == []
