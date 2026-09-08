"""Drive personas through surfaces and collect what happened.

One database for the whole run, one storefront organization, a distinct external
id per persona per surface. That is deliberate: a fresh database per conversation
would hide every shared-state bug there is, and shared state is where the
resolver bug and the repeat-buyer bug both lived.
"""

import traceback

from sqlalchemy.orm import Session

from tests.simulation.buyer import BuyerState, next_utterance, opening_line
from tests.simulation.channels import build_surface
from tests.simulation.expectations import Transcript, check, compare_surfaces
from tests.simulation.personas import Persona

MAX_TURNS = 16


def run_one(
    persona: Persona,
    surface_name: str,
    db: Session,
    client,
    max_turns: int = MAX_TURNS,
    surface=None,
) -> Transcript:
    """One buyer, one platform, start to wherever it ends.

    ``surface`` can be passed in when the caller needs to keep talking to the same
    buyer afterwards — the purchase simulation pays, then says "I paid" in the same
    thread, and a fresh surface there would be a different person.
    """
    if surface is None:
        external_id = f"{surface_name}-{persona.persona_id}"
        surface = build_surface(surface_name, db, client, external_id)

    transcript = Transcript(persona=persona, surface=surface_name)

    try:
        surface.open()
        transcript.opening = list(surface.opening)

        state = BuyerState()
        said = opening_line(persona)

        for _ in range(max_turns):
            turn = surface.say(said)
            transcript.turns.append(turn)

            nxt = next_utterance(persona, turn.text, state)
            if nxt is None:
                break

            said = nxt
    except Exception:  # noqa: BLE001 - the traceback *is* the finding
        db.rollback()
        transcript.error = traceback.format_exc(limit=6)

    return transcript


def run_matrix(
    personas: list[Persona],
    surface_names: tuple[str, ...],
    db: Session,
    client,
    max_turns: int = MAX_TURNS,
    on_progress=None,
):
    """Every persona on every surface, checked individually and compared.

    Returns ``(transcripts, findings)`` where transcripts is a list of
    ``(persona, {surface: Transcript})`` so the report can show a failure beside
    what the other platforms did with the same buyer.
    """
    all_transcripts = []
    findings = []

    for position, persona in enumerate(personas):
        per_surface = {}

        for surface_name in surface_names:
            transcript = run_one(persona, surface_name, db, client, max_turns)
            per_surface[surface_name] = transcript
            findings.extend(check(transcript))

        findings.extend(compare_surfaces(per_surface))
        all_transcripts.append((persona, per_surface))

        if on_progress is not None:
            on_progress(position + 1, len(personas))

    return all_transcripts, findings
