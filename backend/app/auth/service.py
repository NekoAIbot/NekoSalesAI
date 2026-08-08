import re

from sqlalchemy.orm import Session

from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
)
from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.organization import Organization
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, repository: UserRepository, db: Session):
        self.repository = repository
        self.db = db

    def register(self, data: RegisterRequest):
        if self.repository.email_exists(data.email):
            raise ValueError("Email already exists.")

        # Every user belongs to a workspace. Registering with a company name
        # creates that workspace here; without one, a personal workspace is
        # created under the user's own name so tenant scoping is never null.
        if data.company_name:
            org_name = data.company_name.strip()
        else:
            org_name = f"{data.full_name.strip()}'s Workspace"

        org = Organization(name=org_name, slug=self._unique_slug(org_name))
        self.db.add(org)
        self.db.flush()

        user = self.repository.create(
            full_name=data.full_name,
            email=data.email,
            password_hash=hash_password(data.password),
            is_admin=True,
            organization_id=org.id,
        )

        return user

    def _unique_slug(self, name: str) -> str:
        """Slug from the name, suffixed until it does not collide.

        Organizations are created on every public signup, so a slug collision
        is an ordinary occurrence rather than an edge case.
        """
        base = _slugify(name) or "workspace"
        candidate = base
        counter = 1

        while self._slug_exists(candidate):
            counter += 1
            candidate = f"{base}-{counter}"

        return candidate

    def _slug_exists(self, slug: str) -> bool:
        return (
            self.db.query(Organization)
            .filter(Organization.slug == slug)
            .first()
            is not None
        )

    def login(self, data: LoginRequest):
        user = self.repository.get_by_email(data.email)

        if not user:
            raise ValueError("Invalid email or password.")

        if not verify_password(
            data.password,
            user.password_hash,
        ):
            raise ValueError("Invalid email or password.")

        token = create_access_token(
            subject=str(user.id)
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }


def _slugify(name: str) -> str:
    """Lowercase, keep letters and digits, collapse runs into single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    return slug[:80]
