"""Fixtures shared by everything under tests/simulation.

Two things every simulation needs and must not get wrong.

The storefront organization: without it the surfaces have nothing to talk to and
every conversation fails identically, which looks like a thousand bugs.

An offline Paystack: the first smoke run went to the real API over TLS, timed
out, and the timeout propagated out of ``ClosingService`` and killed the reply.
Autouse here, so no simulation can accidentally reach the network — a suite that
sometimes hits a live payment provider is a suite whose failures nobody trusts.
"""

import pytest

from app.config.settings import settings
from app.models.organization import Organization
from tests.simulation.paystack import SimulatedPaystack, install


@pytest.fixture
def storefront(db) -> Organization:
    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)

    return org


@pytest.fixture(autouse=True)
def paystack(monkeypatch) -> SimulatedPaystack:
    return install(monkeypatch, SimulatedPaystack())
