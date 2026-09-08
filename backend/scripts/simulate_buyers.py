#!/usr/bin/env python
"""Run the buyer simulation at full size and print a report.

    .venv/bin/python scripts/simulate_buyers.py                 # 400 personas × 3
    .venv/bin/python scripts/simulate_buyers.py --personas 40    # a quick pass
    .venv/bin/python scripts/simulate_buyers.py --purchases 60   # more real payments
    .venv/bin/python scripts/simulate_buyers.py --transcripts 3  # print examples

Why a script and not a test: a thousand conversations take minutes and produce a
report to read, not an assertion to block a commit on. The must-never-regress
subset lives in ``tests/simulation/`` and runs with the suite. This is the wide
sweep — the thing that found the web/Telegram divergence nobody was looking for.

Everything is in-process and offline. The database is a throwaway SQLite file,
Paystack is simulated, and no chat platform is reachable, so this cannot move
money, message a real person, or touch the live database.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Point at a scratch database before anything imports settings. Getting this
# wrong would run a thousand simulated purchases through the live one.
os.environ["DATABASE_URL"] = "sqlite:///" + str(BACKEND / "var" / "simulation.db")
os.environ.setdefault("ENVIRONMENT", "development")


def build_session():
    """A fresh in-memory database with the schema the models describe."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database.base import Base
    import app.models  # noqa: F401 - registers every table

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def build_client(db):
    """The real app over real HTTP, with the session wired to our database."""
    from fastapi.testclient import TestClient

    from app.database.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db

    return TestClient(app)


class _Patch:
    """monkeypatch, minus pytest.

    ``tests.simulation.paystack.install`` wants a monkeypatch-shaped object, and
    the alternative was duplicating the patch target here — which is exactly how
    a simulation ends up reaching the real payment provider six months from now.
    """

    def __init__(self):
        self._undo = []

    def setattr(self, target: str, value):
        module_name, attribute = target.rsplit(".", 1)
        module = __import__(module_name, fromlist=[attribute])
        self._undo.append((module, attribute, getattr(module, attribute)))
        setattr(module, attribute, value)

    def undo(self):
        for module, attribute, original in reversed(self._undo):
            setattr(module, attribute, original)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personas", type=int, default=400)
    parser.add_argument("--purchases", type=int, default=30)
    parser.add_argument("--concurrent", type=int, default=6)
    parser.add_argument("--transcripts", type=int, default=0)
    parser.add_argument("--turns", type=int, default=16)
    parser.add_argument("--out", type=str, default="")
    parser.add_argument(
        "--surfaces",
        type=str,
        default="web,telegram,whatsapp",
        help="comma-separated subset to run",
    )
    args = parser.parse_args()

    from app.config.settings import settings
    from app.models.organization import Organization
    from tests.simulation import report as reporting
    from tests.simulation.channels import SURFACE_NAMES
    from tests.simulation.paystack import SimulatedPaystack, install
    from tests.simulation.personas import generate
    from tests.simulation.purchases import PurchaseRun, buy_concurrently
    from tests.simulation.run import run_matrix

    surfaces = tuple(
        name.strip() for name in args.surfaces.split(",") if name.strip()
    )

    for name in surfaces:
        if name not in SURFACE_NAMES:
            parser.error(f"unknown surface {name!r}; choose from {SURFACE_NAMES}")

    db = build_session()

    db.add(Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG))
    db.commit()

    client = build_client(db)

    patch = _Patch()
    paystack = install(patch, SimulatedPaystack())

    personas = generate(limit=args.personas)

    print(
        f"Running {len(personas)} personas × {len(surfaces)} surfaces "
        f"= {len(personas) * len(surfaces)} conversations.",
        flush=True,
    )

    started = time.time()
    last = [0.0]

    def progress(done: int, total: int) -> None:
        now = time.time()
        if now - last[0] < 2 and done != total:
            return
        last[0] = now
        rate = done / max(now - started, 0.001)
        remaining = (total - done) / max(rate, 0.001)
        print(
            f"  {done}/{total} personas  ({rate:.1f}/s, ~{remaining:.0f}s left)",
            flush=True,
        )

    transcripts, findings = run_matrix(
        personas, surfaces, db, client, max_turns=args.turns, on_progress=progress
    )

    conversation_seconds = time.time() - started

    # ---------- purchases ----------

    purchases = []

    if args.purchases:
        print(f"\nRunning {args.purchases} full purchases through Paystack.", flush=True)

        run = PurchaseRun(db, client, paystack)
        payable = [p for p in personas if p.should_reach_a_quote][: args.purchases]

        for position, persona in enumerate(payable):
            surface = surfaces[position % len(surfaces)]

            try:
                purchase = run.buy(persona, surface)
            except Exception as exc:  # noqa: BLE001 - a crash is the finding
                import traceback

                print(f"  {persona.persona_id} on {surface} RAISED: {exc}")
                traceback.print_exc(limit=4)
                db.rollback()
                continue

            purchases.append(purchase)
            findings.extend(purchase.findings)

            if (position + 1) % 10 == 0:
                print(f"  {position + 1}/{len(payable)} purchases", flush=True)

    if args.concurrent > 1:
        print(f"\nRunning {args.concurrent} buyers paying at the same time.", flush=True)

        crowd = [p for p in personas if p.should_reach_a_quote][-args.concurrent :]

        try:
            together = buy_concurrently(db, client, paystack, crowd, "telegram")
            purchases.extend(together)
            for purchase in together:
                findings.extend(purchase.findings)
        except Exception as exc:  # noqa: BLE001
            import traceback

            print(f"  concurrent run RAISED: {exc}")
            traceback.print_exc(limit=4)
            db.rollback()

    # ---------- report ----------

    turns = sum(
        len(transcript.turns)
        for _, per_surface in transcripts
        for transcript in per_surface.values()
    )

    text = reporting.render(
        conversations=len(personas) * len(surfaces),
        personas=len(personas),
        surfaces=surfaces,
        findings=findings,
        purchases=purchases,
        turns=turns,
    )

    text += "\n\n  PER SURFACE\n" + reporting.per_surface_tally(findings, surfaces)
    text += (
        f"\n\n  {conversation_seconds:.0f}s of conversation, "
        f"{time.time() - started:.0f}s total.\n"
    )

    print("\n" + text)

    if args.transcripts:
        failed_ids = {
            finding.persona_id
            for finding in findings
            if finding.severity == "failure"
        }

        shown = 0
        print("\n" + reporting.RULE)
        print("EXAMPLE TRANSCRIPTS")
        print(reporting.RULE)

        for persona, per_surface in transcripts:
            if shown >= args.transcripts:
                break
            if failed_ids and persona.persona_id not in failed_ids:
                continue

            print("\n" + reporting.transcript_dump(persona, per_surface))
            shown += 1

    if args.out:
        Path(args.out).write_text(text)
        print(f"\nWritten to {args.out}")

    patch.undo()

    hard = sum(1 for finding in findings if finding.severity == "failure")

    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
