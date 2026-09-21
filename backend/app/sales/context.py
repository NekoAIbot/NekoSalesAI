"""Structured conversation memory: what Nera has learned about this buyer.

Three layers, kept deliberately separate because they carry different weight:

- Business facts: what the buyer's business *is*. Extracted from natural
  descriptions, updated when the buyer says something newer.
- Requirements: what the buyer needs the AI to do. These are the bridge to
  the deterministic scope — never written into the scope directly.
- Conversation state: where the dialogue is, what was asked, what was
  recommended and how the buyer responded.

Each fact carries provenance: ``stated`` (the buyer said it in these words),
``extracted`` (confidently read from a description), or ``inferred`` (weak —
never silently promoted to commercial state).

Nothing here is authoritative for pricing. The scope and the pricing engine
remain the system of record; memory is context the conversational layer reads
to ask better questions and answer with the buyer's own situation in mind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

# Provenance levels, weakest to strongest.
STATED = "stated"
EXTRACTED = "extracted"
INFERRED = "inferred"

_PROVENANCE_ORDER = {INFERRED: 0, EXTRACTED: 1, STATED: 2}


@dataclass(frozen=True)
class Fact:
    """One remembered thing, with where it came from."""

    value: str
    provenance: str = EXTRACTED
    # The buyer's own words, when the fact was stated directly.
    quote: str = ""

    def to_json(self) -> dict:
        return {
            "value": self.value,
            "provenance": self.provenance,
            "quote": self.quote,
        }

    @classmethod
    def from_json(cls, data) -> "Fact | None":
        if not isinstance(data, dict) or "value" not in data:
            return None
        return cls(
            value=str(data["value"]),
            provenance=data.get("provenance", EXTRACTED),
            quote=str(data.get("quote", "")),
        )


@dataclass
class ConversationMemory:
    """Everything Nera remembers about one thread."""

    # Business facts, keyed by a stable fact name (e.g. "business_type").
    business: dict[str, Fact] = field(default_factory=dict)

    # Requirements the buyer expressed, in their own terms.
    requirements: dict[str, Fact] = field(default_factory=dict)

    # Conversation state.
    intent: str = "discovering"  # discovering | advising | configuring | pricing
    pending_question: str | None = None
    # Buyer questions asked recently, newest last, capped.
    recent_questions: list[str] = field(default_factory=list)
    # Products recommended to this buyer, with the reason given.
    recommendations: list[dict] = field(default_factory=list)
    # Explicit decisions the buyer confirmed ("let's use Workforce").
    decisions: list[dict] = field(default_factory=list)

    # ---------- facts ----------

    def remember(
        self,
        kind: str,
        key: str,
        value: str,
        *,
        provenance: str = EXTRACTED,
        quote: str = "",
    ) -> None:
        """Record a fact, replacing a weaker one with a stronger one.

        A later ``stated`` fact always wins over an earlier ``inferred`` one —
        the buyer's own words are the most recent truth. An ``inferred`` fact
        never overwrites a ``stated`` or ``extracted`` one: weak guesses must
        not silently replace what the buyer actually said.
        """
        store = self.business if kind == "business" else self.requirements
        existing = store.get(key)

        if existing is not None:
            if _PROVENANCE_ORDER.get(provenance, 0) < _PROVENANCE_ORDER.get(
                existing.provenance, 0
            ):
                return
            if existing.value == value and existing.provenance == provenance:
                return

        store[key] = Fact(value=value, provenance=provenance, quote=quote)

    def fact(self, kind: str, key: str) -> str | None:
        store = self.business if kind == "business" else self.requirements
        f = store.get(key)
        return f.value if f else None

    def forget(self, kind: str, key: str) -> None:
        store = self.business if kind == "business" else self.requirements
        store.pop(key, None)

    # ---------- conversation state ----------

    def note_question(self, question: str) -> None:
        q = question.strip()
        if not q:
            return
        if self.recent_questions and self.recent_questions[-1] == q:
            return
        self.recent_questions.append(q)
        if len(self.recent_questions) > 5:
            del self.recent_questions[0]

    def note_recommendation(self, products: list[str], reason: str) -> None:
        self.recommendations.append({"products": products, "reason": reason})
        if len(self.recommendations) > 5:
            del self.recommendations[0]

    def note_decision(self, what: str, detail: str = "") -> None:
        self.decisions.append({"what": what, "detail": detail})
        if len(self.decisions) > 10:
            del self.decisions[0]

    def asked_about(self, topic: str) -> bool:
        """Has the buyer asked about this topic recently?"""
        t = topic.lower()
        return any(t in q.lower() for q in self.recent_questions)

    # ---------- persistence ----------

    def to_json(self) -> str:
        return json.dumps(
            {
                "business": {k: f.to_json() for k, f in self.business.items()},
                "requirements": {
                    k: f.to_json() for k, f in self.requirements.items()
                },
                "intent": self.intent,
                "pending_question": self.pending_question,
                "recent_questions": self.recent_questions,
                "recommendations": self.recommendations,
                "decisions": self.decisions,
            }
        )

    @classmethod
    def from_json(cls, raw: str | None) -> "ConversationMemory":
        if not raw:
            return cls()

        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return cls()

        if not isinstance(data, dict):
            return cls()

        memory = cls()
        for key, val in (data.get("business") or {}).items():
            f = Fact.from_json(val)
            if f:
                memory.business[key] = f
        for key, val in (data.get("requirements") or {}).items():
            f = Fact.from_json(val)
            if f:
                memory.requirements[key] = f

        if isinstance(data.get("intent"), str):
            memory.intent = data["intent"]
        if isinstance(data.get("pending_question"), str):
            memory.pending_question = data["pending_question"]
        if isinstance(data.get("recent_questions"), list):
            memory.recent_questions = [
                q for q in data["recent_questions"] if isinstance(q, str)
            ][-5:]
        if isinstance(data.get("recommendations"), list):
            memory.recommendations = [
                r for r in data["recommendations"] if isinstance(r, dict)
            ][-5:]
        if isinstance(data.get("decisions"), list):
            memory.decisions = [
                d for d in data["decisions"] if isinstance(d, dict)
            ][-10:]

        return memory
