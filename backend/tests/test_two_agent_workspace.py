"""One workspace, two agents: which one is the visitor talking to?

A customer who buys both products gets one organization holding two agents — a
sales agent that quotes and closes, and a support agent that answers questions.
That combination shipped before anything could tell them apart. ``resolve_config``
took the organization's *first* workspace profile, so both widgets were served
whichever agent happened to be inserted first.

The visible half was cosmetic: the support widget opened with "I'm Ada, the sales
rep for Bright Dental". The other half was not. Role is read from the profile
column rather than the stored config precisely so a customer cannot promote their
own support agent into one that quotes prices and takes money — and resolving to
the wrong profile did exactly that promotion, on the customer's behalf, without
anybody editing anything.

So these tests are about identity and permission together, and they buy through
the real checkout and provisioning path rather than hand-building two profiles.
The bug lived in the gap between "provisioning writes a correct config per role"
(it did, all along) and "something asks for the right one".
"""

import pytest

from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile
from app.models.organization import Organization
from app.payments.checkout import CheckoutService
from app.payments.paystack import PaystackClient
from app.payments.provisioning import ProvisioningService
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT
from app.products.resolver import resolve_config
from app.sales.service import ConversationService

from tests.test_checkout import (
    BOTH_PRODUCTS_BUILD,
    SALES_BUILD,
    SUPPORT_BUILD,
    TEST_SECRET,
    FakeTransport,
    make_order,
)


# ---------- fixtures ----------


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def checkout(db, transport) -> CheckoutService:
    return CheckoutService(
        db, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
    )


@pytest.fixture
def storefront(db) -> Organization:
    from app.config.settings import settings

    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def buy(db, checkout, transport, storefront, build, email="buyer@example.com") -> tuple:
    """Pay for a build and stand up what it bought. Returns the profiles.

    The email matters more than it looks: it is what identifies the buyer, so two
    calls with the same one are the same customer buying twice and land in one
    workspace. Tests about two *tenants* have to say two addresses.
    """
    order = make_order(checkout, storefront, build=build, buyer_email=email)

    transport.paid = True
    transport.amount_override = order.amount_minor

    order = checkout.confirm_by_reference(order.paystack_reference)
    result = ProvisioningService(db).provision(order)

    # Unwrap ProvisionedAgent (frozen) so tests can mutate profile.status
    return tuple(agent.profile for agent in result.profiles)


def by_role(profiles, role: str) -> WorkspaceProfile:
    for profile in profiles:
        if profile.role == role:
            return profile

    raise AssertionError(f"no {role} in this workspace")


# ---------- what provisioning built ----------


def test_buying_both_products_builds_two_distinct_agents(
    db, checkout, transport, storefront
):
    """The precondition. One workspace, two profiles, two different names."""
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)

    assert len(profiles) == 2
    assert {profile.role for profile in profiles} == {
        ROLE_SALES_AGENT,
        ROLE_SUPPORT_AGENT,
    }
    assert len({profile.organization_id for profile in profiles}) == 1
    assert len({profile.agent_name for profile in profiles}) == 2


# ---------- resolving the config ----------


def test_each_agent_resolves_to_its_own_config(db, checkout, transport, storefront):
    """The fix, stated directly. Naming the profile is what makes it right."""
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)

    sales = by_role(profiles, ROLE_SALES_AGENT)
    support = by_role(profiles, ROLE_SUPPORT_AGENT)

    sales_config = resolve_config(db, sales.organization_id, sales.id)
    support_config = resolve_config(db, support.organization_id, support.id)

    assert sales_config.role == ROLE_SALES_AGENT
    assert support_config.role == ROLE_SUPPORT_AGENT
    assert sales_config.agent_name != support_config.agent_name


def test_the_support_agent_never_inherits_permission_to_sell(
    db, checkout, transport, storefront
):
    """The half of this bug that was not cosmetic.

    ``can_sell`` is what lets an agent quote a price and move a conversation
    toward payment. Resolving the support widget to the sales profile handed it
    that permission — the exact promotion the profile-column rule exists to
    prevent.
    """
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)
    support = by_role(profiles, ROLE_SUPPORT_AGENT)

    assert not resolve_config(db, support.organization_id, support.id).can_sell


def test_a_profile_from_another_tenant_is_refused(
    db, checkout, transport, storefront, caplog
):
    """Cross-tenant is the worst outcome available here.

    Honouring a profile id that belongs to a different organization would mean
    one customer's agent answering with another customer's catalog and prices. It
    falls back to organization resolution, which is at least scoped to the right
    tenant.
    """
    mine = buy(db, checkout, transport, storefront, SALES_BUILD, "mine@example.com")
    theirs = buy(db, checkout, transport, storefront, SUPPORT_BUILD, "theirs@example.com")

    mine_profile = mine[0]
    theirs_profile = theirs[0]

    assert mine_profile.organization_id != theirs_profile.organization_id

    config = resolve_config(db, mine_profile.organization_id, theirs_profile.id)

    assert config.company_name == mine_profile.company_name
    assert config.role == ROLE_SALES_AGENT


def test_a_single_agent_workspace_still_resolves_without_being_told(
    db, checkout, transport, storefront
):
    """Back-compatibility. Threads written before the column carry no profile."""
    profiles = buy(db, checkout, transport, storefront, SUPPORT_BUILD)
    profile = profiles[0]

    config = resolve_config(db, profile.organization_id)

    assert config.role == ROLE_SUPPORT_AGENT
    assert config.company_name == profile.company_name


def test_an_organization_with_no_workspace_is_the_storefront(db, storefront):
    from app.catalog import STOREFRONT_CONFIG

    assert resolve_config(db, storefront.id) is STOREFRONT_CONFIG


def test_an_unknown_profile_id_falls_back_rather_than_failing(
    db, checkout, transport, storefront
):
    profiles = buy(db, checkout, transport, storefront, SUPPORT_BUILD)
    profile = profiles[0]

    config = resolve_config(db, profile.organization_id, 9_999_999)

    assert config.role == ROLE_SUPPORT_AGENT


# ---------- what the visitor actually reads ----------


def test_the_support_widget_greets_as_the_support_agent(
    db, client, checkout, transport, storefront
):
    """The live symptom, end to end through the route a customer embeds.

    Nera's own support widget introduced itself as Ada, the sales rep, because
    Ada's profile was created first. A visitor asking a support question was
    greeted by a salesperson who then could not answer it.
    """
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)

    sales = by_role(profiles, ROLE_SALES_AGENT)
    support = by_role(profiles, ROLE_SUPPORT_AGENT)

    for profile in (sales, support):
        profile.status = PROVISION_READY

    db.commit()

    started = client.post(f"/api/v1/widget/{support.widget_token}/conversations")

    assert started.status_code == 201

    opening = started.json()["messages"][0]["body"]

    assert support.agent_name.split()[0] in opening
    assert sales.agent_name.split()[0] not in opening


def test_the_sales_widget_still_greets_as_the_sales_agent(
    db, client, checkout, transport, storefront
):
    """The other side of it: fixing support must not break the one that worked."""
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)

    sales = by_role(profiles, ROLE_SALES_AGENT)
    support = by_role(profiles, ROLE_SUPPORT_AGENT)

    for profile in (sales, support):
        profile.status = PROVISION_READY

    db.commit()

    started = client.post(f"/api/v1/widget/{sales.widget_token}/conversations")
    opening = started.json()["messages"][0]["body"]

    assert sales.agent_name.split()[0] in opening
    assert support.agent_name.split()[0] not in opening


def test_the_thread_remembers_which_agent_it_belongs_to(
    db, client, checkout, transport, storefront
):
    """Recorded on the conversation, not re-guessed per turn.

    A turn that re-derived the agent from the organization would drift the moment
    the workspace held two, which is how the greeting and the answers came to be
    from different agents in the same thread.
    """
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)
    support = by_role(profiles, ROLE_SUPPORT_AGENT)

    for profile in profiles:
        profile.status = PROVISION_READY

    db.commit()

    token = client.post(
        f"/api/v1/widget/{support.widget_token}/conversations"
    ).json()["token"]

    conversation = ConversationService(db).get_by_token(token)

    assert conversation.workspace_profile_id == support.id


def test_the_other_widget_in_the_same_workspace_cannot_continue_the_thread(
    db, client, checkout, transport, storefront
):
    """A support thread answered by the sales agent is a different conversation.

    Same tenant, so this is not a data leak — it is an identity one. The engine
    would answer with the other agent's name and the other agent's permission to
    quote, halfway through a thread the visitor opened with somebody else.
    """
    profiles = buy(db, checkout, transport, storefront, BOTH_PRODUCTS_BUILD)

    sales = by_role(profiles, ROLE_SALES_AGENT)
    support = by_role(profiles, ROLE_SUPPORT_AGENT)

    for profile in profiles:
        profile.status = PROVISION_READY

    db.commit()

    token = client.post(
        f"/api/v1/widget/{support.widget_token}/conversations"
    ).json()["token"]

    crossed = client.get(f"/api/v1/widget/{sales.widget_token}/conversations/{token}")

    assert crossed.status_code == 404

    # And the widget it was opened with still works.
    assert (
        client.get(
            f"/api/v1/widget/{support.widget_token}/conversations/{token}"
        ).status_code
        == 200
    )


# ---------- buying again ----------
#
# Two real orders came from one email address and produced two organizations,
# ``nekosalesai`` and ``nekosalesai-2``. The buyer's login points at the first
# one, so the agents the second order paid for were standing up in a workspace
# that account could not open. Everything about that sale was correct except
# where it landed.


def test_a_returning_buyer_joins_the_workspace_they_already_have(
    db, checkout, transport, storefront
):
    from app.models.user import User

    first = buy(db, checkout, transport, storefront, SALES_BUILD, "neko@example.com")
    second = buy(
        db, checkout, transport, storefront, SUPPORT_BUILD, "neko@example.com"
    )

    assert first[0].organization_id == second[0].organization_id

    # And it is the organization their login can actually open.
    user = db.query(User).filter(User.email == "neko@example.com").one()

    assert user.organization_id == second[0].organization_id


def test_buying_the_second_product_later_ends_up_beside_the_first(
    db, checkout, transport, storefront
):
    """The realistic path: one agent now, the other next month."""
    buy(db, checkout, transport, storefront, SALES_BUILD, "neko@example.com")
    buy(db, checkout, transport, storefront, SUPPORT_BUILD, "neko@example.com")

    org_id = db.query(WorkspaceProfile).first().organization_id
    roles = {
        profile.role
        for profile in db.query(WorkspaceProfile)
        .filter(WorkspaceProfile.organization_id == org_id)
        .all()
    }

    assert roles == {ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT}


def test_buying_the_same_agent_twice_does_not_break_the_live_one(
    db, checkout, transport, storefront
):
    """A renewal must not take the customer's agent off their website.

    The widget token is pasted into their page source. Minting a replacement
    because they paid again would mean their site starts calling a token that no
    longer exists — punishing the customer for buying.
    """
    first = buy(db, checkout, transport, storefront, SALES_BUILD, "neko@example.com")
    token_before = first[0].widget_token
    key_before = first[0].api_key_hash

    second = buy(db, checkout, transport, storefront, SALES_BUILD, "neko@example.com")

    assert len(second) == 1
    assert second[0].id == first[0].id
    assert second[0].widget_token == token_before
    assert second[0].api_key_hash == key_before


def test_a_different_buyer_still_gets_their_own_workspace(
    db, checkout, transport, storefront
):
    """The check that keeps the fix from becoming a tenancy bug."""
    mine = buy(db, checkout, transport, storefront, SALES_BUILD, "one@example.com")
    theirs = buy(db, checkout, transport, storefront, SALES_BUILD, "two@example.com")

    assert mine[0].organization_id != theirs[0].organization_id


def test_the_renewed_agent_is_delivered_against_the_new_order(
    db, checkout, transport, storefront
):
    """Delivery reads profiles by order id, so a renewal has to re-point it.

    Otherwise the second purchase is paid, provisioned and undeliverable: nothing
    is attached to the order, so the reconciler decides the workspace is not up
    yet and waits forever.
    """
    from app.payments.delivery import DeliveryService

    buy(db, checkout, transport, storefront, SALES_BUILD, "neko@example.com")

    order = make_order(
        checkout, storefront, build=SALES_BUILD, buyer_email="neko@example.com"
    )
    transport.paid = True
    transport.amount_override = order.amount_minor
    order = checkout.confirm_by_reference(order.paystack_reference)
    ProvisioningService(db).provision(order)

    assert DeliveryService(db).profiles_for(order)
