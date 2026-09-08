"""Smoke the harness itself before trusting a thousand runs of it.

Prints the first transcript so a plumbing failure looks like a plumbing failure
rather than like Nera misbehaving.
"""

import pytest

from tests.simulation.channels import SURFACE_NAMES
from tests.simulation.personas import generate
from tests.simulation.run import run_one


def test_smoke(db, client, storefront, capsys):
    personas = generate(limit=6)

    for persona in personas[:2]:
        for surface in SURFACE_NAMES:
            transcript = run_one(persona, surface, db, client)

            with capsys.disabled():
                print(f"\n===== {persona.persona_id} on {surface} =====")
                print(f"business: {persona.business.text!r} ({persona.business.expectation})")
                print(f"wants: {persona.product_ask!r} / {persona.channel_ask!r} / "
                      f"{persona.volume_ask!r} / {persona.integration_ask!r}")
                if transcript.error:
                    print("ERROR:", transcript.error)
                for index, turn in enumerate(transcript.turns):
                    print(f"\n[{index}] BUYER: {turn.said}")
                    print(f"    rule={turn.rule} escalated={turn.escalated} stage={turn.stage}")
                    print(f"    NERA: {turn.text[:400]}")
