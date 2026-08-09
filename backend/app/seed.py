"""Seed the development database with demo data.

Idempotent: running it repeatedly will not create duplicates. Safe to run on
every dev-server start.

    python -m app.seed
"""

from sqlalchemy.orm import Session

from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, settings
from app.core.security import hash_password, verify_password
from app.database.session import get_db
from app.models import Customer, Lead, Organization, User

logger = get_logger(__name__)

# The storefront org is the one the public landing page and chat sell for, so
# the slug comes from settings rather than being defined twice.
DEMO_ORG_SLUG = settings.STOREFRONT_ORG_SLUG
DEMO_USER_EMAIL = settings.DEMO_USER_EMAIL

# Read through settings rather than os.environ so that .env is honoured — the
# app never exports these into the process environment, so os.environ.get here
# would silently miss a value set in .env and hand back the published default.
DEMO_USER_PASSWORD = settings.DEMO_USER_PASSWORD


def seed_organization(db: Session) -> Organization:
    org = (
        db.query(Organization)
        .filter(Organization.slug == DEMO_ORG_SLUG)
        .first()
    )

    if org:
        return org

    org = Organization(
        name="NekoSalesAI Demo",
        slug=DEMO_ORG_SLUG,
        email="hello@nekosales.ai",
        industry="Software",
        country="Nigeria",
        currency="NGN",
        subscription_plan="free",
    )

    db.add(org)
    db.commit()
    db.refresh(org)

    return org


def seed_user(db: Session, org: Organization) -> User:
    user = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()

    if user:
        # Reconcile the password rather than returning early. The demo user
        # outlives any single run, so a database seeded before
        # DEMO_USER_PASSWORD was set would keep the published fallback
        # password forever and setting the variable would appear to work
        # while changing nothing.
        if not verify_password(DEMO_USER_PASSWORD, user.password_hash):
            user.password_hash = hash_password(DEMO_USER_PASSWORD)
            db.commit()
            db.refresh(user)
            logger.info("Demo user password updated from the environment")

        return user

    user = User(
        organization_id=org.id,
        full_name="Neko Founder",
        email=DEMO_USER_EMAIL,
        password_hash=hash_password(DEMO_USER_PASSWORD),
        is_admin=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


DEMO_LEADS = [
    {
        "first_name": "Amara",
        "last_name": "Nwosu",
        "email": "amara@brightretail.ng",
        "company": "Bright Retail",
        "job_title": "Operations Lead",
        "source": "Landing Page",
        "status": "New",
        "notes": "Clicked 'talk to our AI rep' from the pricing section.",
    },
    {
        "first_name": "Tunde",
        "last_name": "Adeyemi",
        "email": "tunde@swiftlogistics.ng",
        "company": "Swift Logistics",
        "job_title": "Founder",
        "source": "Demo Request",
        "status": "Qualified",
        "notes": "Asked about response times and per-seat pricing.",
    },
    {
        "first_name": "Grace",
        "last_name": "Mensah",
        "email": "grace@dayspa.co",
        "company": "Day Spa Collective",
        "job_title": "Owner",
        "source": "Referral",
        "status": "New",
        "notes": "Referred by an existing user. Wants to handle booking questions.",
    },
]


def seed_leads(db: Session, org: Organization) -> int:
    created = 0

    for entry in DEMO_LEADS:
        exists = (
            db.query(Lead)
            .filter(
                Lead.organization_id == org.id,
                Lead.email == entry["email"],
            )
            .first()
        )

        if exists:
            continue

        db.add(Lead(organization_id=org.id, **entry))
        created += 1

    db.commit()

    return created


DEMO_CUSTOMERS = [
    {
        "first_name": "Ifeoma",
        "last_name": "Balogun",
        "email": "ifeoma@greenfields.ng",
        "company": "Greenfields Foods",
        "job_title": "Head of Sales",
        "lifecycle_stage": "ENGAGED",
        "buying_intent": "HIGH",
        "engagement_score": 72,
        "opportunity_score": 68,
    },
    {
        "first_name": "Samuel",
        "last_name": "Eze",
        "email": "samuel@paystackpartners.co",
        "company": "Partner Works",
        "job_title": "Managing Director",
        "lifecycle_stage": "NEW",
        "buying_intent": "MEDIUM",
        "engagement_score": 34,
        "opportunity_score": 40,
    },
]


def seed_customers(db: Session, org: Organization) -> int:
    created = 0

    for entry in DEMO_CUSTOMERS:
        exists = (
            db.query(Customer)
            .filter(
                Customer.organization_id == org.id,
                Customer.email == entry["email"],
            )
            .first()
        )

        if exists:
            continue

        db.add(Customer(organization_id=org.id, **entry))
        created += 1

    db.commit()

    return created


def seed() -> None:
    db = next(get_db())

    try:
        org = seed_organization(db)
        seed_user(db, org)
        leads = seed_leads(db, org)
        customers = seed_customers(db, org)

        # The password is echoed only while it is the published default, where
        # printing it saves a trip to the source and gives away nothing. Once
        # it has been overridden it is a real credential, and real credentials
        # do not belong in a log that gets scrolled past, redirected to a file
        # and pasted into chats.
        is_default_password = (
            DEMO_USER_PASSWORD == Settings.model_fields["DEMO_USER_PASSWORD"].default
        )

        logger.info(
            "Seed complete: org=%s, +%d leads, +%d customers (login: %s / %s)",
            org.slug,
            leads,
            customers,
            DEMO_USER_EMAIL,
            DEMO_USER_PASSWORD if is_default_password else "<set in .env>",
        )
    finally:
        db.close()


if __name__ == "__main__":
    configure_logging()
    seed()
