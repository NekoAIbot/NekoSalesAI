"""Seeding is the app's only writer of a credential nobody chose.

These tests exist because of a specific near-miss. The demo login's password
is published in the repo, which is harmless while the server only answers on
127.0.0.1 and an open door the moment it does not. Making it configurable was
the fix; the first attempt read os.environ, which the app never populates, so
setting it in .env changed nothing and the log cheerfully printed the old
password as though it had worked.

So: assert the override is actually honoured, assert an already-seeded
database gets reconciled rather than skipped, and assert a real password is
not echoed.
"""

from app.config.settings import Settings
from app.core.security import verify_password
from app.models import User
from app.seed import seed_organization, seed_user

PUBLISHED_DEFAULT = Settings.model_fields["DEMO_USER_PASSWORD"].default


def test_the_published_default_is_what_seed_falls_back_to(monkeypatch):
    """Guards the constant the other tests are written against."""
    assert PUBLISHED_DEFAULT == "demo-password-2026"


def test_seeding_uses_the_configured_password(db, monkeypatch):
    """The override has to reach the hash, not just the settings object."""
    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", "chosen-not-published")

    org = seed_organization(db)
    user = seed_user(db, org)

    assert verify_password("chosen-not-published", user.password_hash)
    assert not verify_password(PUBLISHED_DEFAULT, user.password_hash)


def test_reseeding_rotates_a_password_that_was_already_set(db, monkeypatch):
    """The case that made this a real bug rather than a theoretical one.

    A database seeded before the password was configured already holds the
    published default. Returning early on "user exists" would leave that hash
    in place forever, so setting the variable would look like it worked while
    the old password kept on working too.
    """
    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", PUBLISHED_DEFAULT)
    org = seed_organization(db)
    seed_user(db, org)

    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", "rotated-in-place")
    user = seed_user(db, org)

    assert verify_password("rotated-in-place", user.password_hash)
    assert not verify_password(PUBLISHED_DEFAULT, user.password_hash)


def test_reseeding_does_not_create_a_second_user(db, monkeypatch):
    """Rotation must not come at the cost of idempotence.

    dev.sh seeds on every start, so this runs constantly.
    """
    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", "steady-state")
    org = seed_organization(db)

    first = seed_user(db, org)
    second = seed_user(db, org)

    assert first.id == second.id
    assert db.query(User).count() == 1


def test_an_unchanged_password_is_left_alone(db, monkeypatch):
    """No pointless rehash-and-commit on every server start."""
    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", "steady-state")
    org = seed_organization(db)

    original_hash = seed_user(db, org).password_hash
    assert seed_user(db, org).password_hash == original_hash


def test_a_real_password_is_not_written_to_the_log(db, monkeypatch, caplog):
    """Logs get redirected to files and pasted into chats."""
    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", "sup3r-secret-value")

    with caplog.at_level("INFO"):
        from app.seed import seed

        monkeypatch.setattr("app.seed.get_db", lambda: iter([db]))
        seed()

    assert "sup3r-secret-value" not in caplog.text
    assert "<set in .env>" in caplog.text


def test_the_published_default_is_still_echoed(db, monkeypatch, caplog):
    """While it is public knowledge, printing it saves a trip to the source."""
    monkeypatch.setattr("app.seed.DEMO_USER_PASSWORD", PUBLISHED_DEFAULT)

    with caplog.at_level("INFO"):
        from app.seed import seed

        monkeypatch.setattr("app.seed.get_db", lambda: iter([db]))
        seed()

    assert PUBLISHED_DEFAULT in caplog.text
