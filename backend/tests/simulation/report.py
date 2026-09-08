"""Turning a thousand conversations into something a person can act on.

A sweep this size produces findings faster than anyone can read them, and the
temptation is a summary that says "97% passed". That number is worse than no
number: the 3% is the whole point, and a percentage hides whether the failures
are one bug seen three hundred times or three hundred bugs.

So this report is built around grouping. Findings that share a category and a
summary are one defect, counted, with one worked example printed in full — what
the buyer said, what should have happened, what did. The rest are a tally. That
way the length of the report tracks the number of *distinct* problems rather than
the number of personas.

Near-misses are printed in their own section rather than mixed in, because they
are judgement calls rather than facts, and cross-surface inconsistencies get a
section of their own because that is the class of bug this whole exercise exists
to catch — the same buyer, treated differently depending on where they arrived.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from tests.simulation.expectations import FAILURE, NEAR_MISS, Finding

RULE = "─" * 78


def _group(findings: list[Finding]) -> dict:
    """One entry per distinct defect, holding its count and an example."""
    grouped: dict[tuple, dict] = {}

    for finding in findings:
        key = (finding.category, finding.summary)
        entry = grouped.setdefault(
            key,
            {
                "category": finding.category,
                "summary": finding.summary,
                "count": 0,
                "surfaces": Counter(),
                "personas": [],
                "example": finding,
            },
        )

        entry["count"] += 1
        entry["surfaces"][finding.surface] += 1

        if len(entry["personas"]) < 12:
            entry["personas"].append(f"{finding.persona_id}/{finding.surface}")

        # Prefer an example that actually quotes the exchange — a finding with the
        # buyer's words in it is worth ten that only name the rule.
        if not entry["example"].said and finding.said:
            entry["example"] = finding

    return grouped


def _detail(entry: dict) -> str:
    finding = entry["example"]
    surfaces = ", ".join(
        f"{name} ×{count}" for name, count in sorted(entry["surfaces"].items())
    )

    lines = [
        f"[{entry['count']:>4}] {entry['category']}",
        f"       {entry['summary']}",
        f"       surfaces: {surfaces}",
        f"       expected: {finding.expected}",
        f"       actual:   {finding.actual}",
    ]

    if finding.said:
        lines.append(f"       buyer said: {finding.said!r}")

    if finding.reply:
        reply = " ".join(finding.reply.split())
        lines.append(f"       nera said:  {reply[:300]}")

    lines.append(f"       seen on: {', '.join(entry['personas'])}")

    return "\n".join(lines)


def _counted_by_category(findings: list[Finding]) -> str:
    counts = Counter(finding.category for finding in findings)

    if not counts:
        return "       (none)"

    width = max(len(category) for category in counts)

    return "\n".join(
        f"       {category:<{width}}  {count:>5}"
        for category, count in sorted(counts.items(), key=lambda item: -item[1])
    )


def render(
    *,
    conversations: int,
    personas: int,
    surfaces: tuple[str, ...],
    findings: list[Finding],
    purchases: list | None = None,
    turns: int = 0,
) -> str:
    """The whole report, as text. No colour, no spinner — this gets pasted."""
    failures = [f for f in findings if f.severity == FAILURE]
    near = [f for f in findings if f.severity == NEAR_MISS]

    inconsistent = [f for f in failures if f.category.startswith("consistency")]
    other = [f for f in failures if not f.category.startswith("consistency")]

    out = [
        RULE,
        "NEKOSALESAI — BUYER SIMULATION REPORT",
        RULE,
        "",
        f"  personas:       {personas}",
        f"  surfaces:       {', '.join(surfaces)}",
        f"  conversations:  {conversations}",
        f"  buyer turns:    {turns}",
        "",
        f"  hard failures:  {len(failures)}  ({len(_group(failures))} distinct)",
        f"  near misses:    {len(near)}  ({len(_group(near))} distinct)",
        "",
    ]

    if purchases is not None:
        completed = sum(1 for p in purchases if p.completed)
        paid = sum(1 for p in purchases if p.order is not None and p.order.is_paid)
        reached = sum(1 for p in purchases if p.reached_payment)

        out += [
            "  PURCHASES",
            f"    attempted:            {len(purchases)}",
            f"    reached a payment:    {reached}",
            f"    paid at Paystack:     {paid}",
            f"    delivered to buyer:   {completed}",
            "",
        ]

    out += ["  FAILURES BY CATEGORY", _counted_by_category(failures), ""]

    if near:
        out += ["  NEAR MISSES BY CATEGORY", _counted_by_category(near), ""]

    if inconsistent:
        out += [
            RULE,
            "CROSS-PLATFORM INCONSISTENCIES",
            "the same buyer, treated differently depending on where they arrived",
            RULE,
            "",
        ]
        for entry in sorted(
            _group(inconsistent).values(), key=lambda e: -e["count"]
        ):
            out += [_detail(entry), ""]

    if other:
        out += [RULE, "FAILURES", RULE, ""]
        for entry in sorted(_group(other).values(), key=lambda e: -e["count"]):
            out += [_detail(entry), ""]

    if near:
        out += [
            RULE,
            "NEAR MISSES",
            "worth a look, not necessarily wrong",
            RULE,
            "",
        ]
        for entry in sorted(_group(near).values(), key=lambda e: -e["count"]):
            out += [_detail(entry), ""]

    if not failures and not near:
        out += ["  Nothing to report: every check passed on every surface.", ""]

    out += [RULE]

    return "\n".join(out)


def transcript_dump(persona, per_surface: dict) -> str:
    """One buyer's conversation on every surface, side by side.

    For reading a failure rather than counting it. Printed for a handful of
    personas, never for a thousand.
    """
    out = []

    for name, transcript in per_surface.items():
        out.append(f"===== {persona.persona_id} on {name} =====")
        out.append(f"business: {persona.business.text!r} ({persona.business.expectation})")

        if transcript.error:
            out.append(f"  RAISED: {transcript.error}")
            continue

        for index, turn in enumerate(transcript.turns):
            out.append(f"\n[{index}] BUYER: {turn.said}")
            out.append(
                f"    rule={turn.rule} escalated={turn.escalated} stage={turn.stage}"
            )
            out.append(f"    NERA: {turn.text[:700]}")

        out.append("")

    return "\n".join(out)


def per_surface_tally(findings: list[Finding], surfaces: tuple[str, ...]) -> str:
    """Which platform is worst, at a glance."""
    by_surface = defaultdict(Counter)

    for finding in findings:
        by_surface[finding.surface][finding.severity] += 1

    lines = ["       surface     failures  near misses"]

    for surface in surfaces:
        counts = by_surface.get(surface, Counter())
        lines.append(
            f"       {surface:<10} {counts[FAILURE]:>8}  {counts[NEAR_MISS]:>11}"
        )

    return "\n".join(lines)
