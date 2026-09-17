import base64
import io
import re
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
import qrcode
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    validate_password_policy,
)
from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.config.settings import settings
from app.mail.transport import Message, send
from app.models.email_verification_code import EmailVerificationCode
from app.models.organization import Organization
from app.models.password_reset_token import PasswordResetToken
from app.repositories.user_repository import UserRepository

# ===========================
# Constants
# ===========================

TOTP_ISSUER = "NekoSalesAI"
TOTP_DIGITS = 6
TOTP_INTERVAL = 30
EMAIL_CODE_LENGTH = 6
EMAIL_CODE_EXPIRY_MINUTES = 15
EMAIL_CODE_MAX_ATTEMPTS = 3
EMAIL_CODE_RESEND_COOLDOWN_SECONDS = 60
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 1
RECOVERY_CODES_COUNT = 8
RECOVERY_CODE_LENGTH = 10


def _hash_secret(secret: str) -> str:
    """Hash a secret (TOTP seed, verification code, recovery code) for storage."""
    return hash_password(secret)


def _verify_secret(secret: str, hashed: str) -> bool:
    """Verify a secret against its hash."""
    return verify_password(secret, hashed)


def _generate_signed_token(data: str) -> str:
    """Generate a signed token using itsdangerous."""
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    return serializer.dumps(data)


def _verify_signed_token(token: str, max_age_seconds: int) -> str | None:
    """Verify a signed token. Returns the data or None if invalid/expired."""
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    try:
        return serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def _generate_numeric_code(length: int = EMAIL_CODE_LENGTH) -> str:
    """Generate a random numeric code of specified length."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def _generate_recovery_code() -> str:
    """Generate a single recovery code."""
    return secrets.token_hex(RECOVERY_CODE_LENGTH // 2).upper()


def _generate_recovery_codes(count: int = RECOVERY_CODES_COUNT) -> list[str]:
    """Generate a list of recovery codes."""
    return [_generate_recovery_code() for _ in range(count)]


def _send_verification_email(email: str, code: str) -> None:
    """Send email verification code to user."""
    body = (
        f"Your NekoSalesAI verification code is:\n\n"
        f"  {code}\n\n"
        f"This code expires in {EMAIL_CODE_EXPIRY_MINUTES} minutes.\n"
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"— {settings.MAIL_FROM_NAME}\n{settings.MAIL_FROM}\n"
    )
    message = Message(
        to=email,
        subject=f"Your verification code: {code}",
        body=body,
    )
    send(message)


def _send_password_reset_email(email: str, reset_url: str) -> None:
    """Send password reset link to user."""
    body = (
        f"You requested a password reset for your NekoSalesAI account.\n\n"
        f"Click the link below to set a new password:\n\n"
        f"  {reset_url}\n\n"
        f"This link expires in {PASSWORD_RESET_TOKEN_EXPIRY_HOURS} hour(s) and can only be used once.\n"
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"— {settings.MAIL_FROM_NAME}\n{settings.MAIL_FROM}\n"
    )
    message = Message(
        to=email,
        subject="Reset your NekoSalesAI password",
        body=body,
    )
    send(message)


class AuthService:
    def __init__(self, repository: UserRepository, db: Session):
        self.repository = repository
        self.db = db

    def register(self, data: RegisterRequest):
        if self.repository.email_exists(data.email):
            raise ValueError("Email already exists.")

        # Validate password policy
        validate_password_policy(data.password)

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

        # Send email verification code on registration
        self._send_email_verification(user.id, user.email)

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

        # If TOTP is enabled, require TOTP code
        if user.totp_enabled:
            raise ValueError("TOTP code required. Use /auth/login/totp")

        token = create_access_token(
            subject=str(user.id)
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }

    def login_with_totp(self, email: str, password: str, totp_code: str):
        """Login with TOTP code for users who have MFA enabled."""
        user = self.repository.get_by_email(email)

        if not user:
            raise ValueError("Invalid email or password.")

        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password.")

        if not user.totp_enabled or not user.totp_secret:
            raise ValueError("TOTP not enabled for this account.")

        if not self._verify_totp(user.totp_secret, totp_code):
            raise ValueError("Invalid TOTP code.")

        token = create_access_token(subject=str(user.id))

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }

    def login_with_recovery_code(self, email: str, password: str, recovery_code: str):
        """Login using a recovery code (bypasses TOTP)."""
        user = self.repository.get_by_email(email)

        if not user:
            raise ValueError("Invalid email or password.")

        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password.")

        if not user.totp_enabled:
            raise ValueError("TOTP not enabled for this account.")

        if not self._verify_and_consume_recovery_code(user, recovery_code):
            raise ValueError("Invalid or already used recovery code.")

        token = create_access_token(subject=str(user.id))

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }

    # ===========================
    # Email Verification
    # ===========================

    def _send_email_verification(self, user_id: int, email: str) -> None:
        """Generate and send email verification code."""
        # Invalidate any existing codes for this user
        existing_codes = self.db.query(EmailVerificationCode).filter(
            EmailVerificationCode.user_id == user_id
        ).all()
        for ec in existing_codes:
            self.db.delete(ec)

        # Generate new code
        code = _generate_numeric_code()
        code_hash = _hash_secret(code)

        verification = EmailVerificationCode(
            code_hash=code_hash,
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=EMAIL_CODE_EXPIRY_MINUTES),
            attempts=0,
        )
        self.db.add(verification)
        self.db.commit()

        _send_verification_email(email, code)

    def send_email_verification(self, email: str) -> None:
        """Resend email verification code with cooldown."""
        user = self.repository.get_by_email(email)
        if not user:
            # Don't reveal whether email exists
            return

        if user.email_verified:
            raise ValueError("Email already verified.")

        # Check cooldown: find the most recent code
        latest_code = (
            self.db.query(EmailVerificationCode)
            .filter(EmailVerificationCode.user_id == user.id)
            .order_by(EmailVerificationCode.created_at.desc())
            .first()
        )

        if latest_code:
            cooldown_end = latest_code.created_at + timedelta(seconds=EMAIL_CODE_RESEND_COOLDOWN_SECONDS)
            if datetime.now(UTC) < cooldown_end:
                remaining = int((cooldown_end - datetime.now(UTC)).total_seconds())
                raise ValueError(f"Please wait {remaining} seconds before requesting a new code.")

        self._send_email_verification(user.id, user.email)

    def verify_email(self, email: str, code: str) -> bool:
        """Verify email with the provided code."""
        user = self.repository.get_by_email(email)
        if not user:
            raise ValueError("Invalid email or code.")

        if user.email_verified:
            raise ValueError("Email already verified.")

        # Find the most recent valid code
        verification = (
            self.db.query(EmailVerificationCode)
            .filter(
                EmailVerificationCode.user_id == user.id,
                EmailVerificationCode.expires_at > datetime.now(UTC),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .first()
        )

        if not verification:
            raise ValueError("No valid verification code found. Please request a new one.")

        # Check max attempts
        if verification.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
            raise ValueError("Too many attempts. Please request a new code.")

        # Increment attempts
        verification.attempts += 1
        self.db.commit()

        # Verify code
        if not _verify_secret(code, verification.code_hash):
            raise ValueError("Invalid code.")

        # Mark email as verified
        user.email_verified = True
        self.db.delete(verification)
        self.db.commit()

        return True

    # ===========================
    # TOTP MFA
    # ===========================

    def setup_totp(self, user_id: int) -> dict:
        """Set up TOTP for a user. Returns secret, provisioning URI, and QR code."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        if user.totp_enabled:
            raise ValueError("TOTP is already enabled. Disable it first to reconfigure.")

        # Generate new TOTP secret
        secret = pyotp.random_base32()

        # Create provisioning URI
        totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=TOTP_ISSUER,
        )

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Store the secret temporarily (not enabled until verified)
        user.totp_secret = secret
        self.db.commit()

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code": f"data:image/png;base64,{qr_base64}",
        }

    def enable_totp(self, user_id: int, code: str) -> list[str]:
        """Enable TOTP after verifying the initial code. Returns recovery codes."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        if not user.totp_secret:
            raise ValueError("TOTP not set up. Call /auth/totp/setup first.")

        if user.totp_enabled:
            raise ValueError("TOTP is already enabled.")

        # Verify the code
        if not self._verify_totp(user.totp_secret, code):
            raise ValueError("Invalid TOTP code. Please try again.")

        # Generate recovery codes
        recovery_codes = _generate_recovery_codes()
        hashed_codes = [_hash_secret(rc) for rc in recovery_codes]

        # Enable TOTP
        user.totp_enabled = True
        user.recovery_codes = ",".join(hashed_codes)
        self.db.commit()

        return recovery_codes

    def disable_totp(self, user_id: int, code: str) -> bool:
        """Disable TOTP after verifying a code."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        if not user.totp_enabled:
            raise ValueError("TOTP is not enabled.")

        if not self._verify_totp(user.totp_secret, code):
            raise ValueError("Invalid TOTP code.")

        user.totp_enabled = False
        user.totp_secret = None
        user.recovery_codes = None
        self.db.commit()

        return True

    def get_totp_status(self, user_id: int) -> dict:
        """Get TOTP status for a user."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        return {"enabled": user.totp_enabled}

    def _verify_totp(self, secret: str, code: str) -> bool:
        """Verify a TOTP code against a secret."""
        totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
        return totp.verify(code, valid_window=1)

    # ===========================
    # Recovery Codes
    # ===========================

    def _verify_and_consume_recovery_code(self, user, recovery_code: str) -> bool:
        """Verify a recovery code and consume it if valid."""
        if not user.recovery_codes:
            return False

        stored_codes = user.recovery_codes.split(",")
        for i, hashed_code in enumerate(stored_codes):
            if _verify_secret(recovery_code.upper(), hashed_code):
                # Remove the used code
                stored_codes.pop(i)
                user.recovery_codes = ",".join(stored_codes) if stored_codes else None
                self.db.commit()
                return True

        return False

    def regenerate_recovery_codes(self, user_id: int, totp_code: str) -> list[str]:
        """Regenerate recovery codes (requires TOTP verification)."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        if not user.totp_enabled:
            raise ValueError("TOTP is not enabled.")

        if not self._verify_totp(user.totp_secret, totp_code):
            raise ValueError("Invalid TOTP code.")

        recovery_codes = _generate_recovery_codes()
        hashed_codes = [_hash_secret(rc) for rc in recovery_codes]
        user.recovery_codes = ",".join(hashed_codes)
        self.db.commit()

        return recovery_codes

    # ===========================
    # Forgot Password
    # ===========================

    def forgot_password(self, email: str) -> None:
        """Initiate forgot password flow."""
        user = self.repository.get_by_email(email)
        if not user:
            # Don't reveal whether email exists
            return

        # Invalidate any existing tokens for this user
        existing_tokens = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id
        ).all()
        for t in existing_tokens:
            self.db.delete(t)

        # Generate signed token
        token = _generate_signed_token(str(user.id))
        token_hash = _hash_secret(token)

        reset_token = PasswordResetToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRY_HOURS),
            used=False,
        )
        self.db.add(reset_token)
        self.db.commit()

        # Build reset URL
        reset_url = f"{settings.PUBLIC_BASE_URL}/reset-password?token={token}"
        _send_password_reset_email(email, reset_url)

    def reset_password(self, token: str, new_password: str) -> bool:
        """Reset password using a signed token."""
        # Verify the signed token
        user_id_str = _verify_signed_token(token, PASSWORD_RESET_TOKEN_EXPIRY_HOURS * 3600)
        if not user_id_str:
            raise ValueError("Invalid or expired reset token.")

        user_id = int(user_id_str)

        # Find the token in database
        token_hash = _hash_secret(token)
        reset_token = (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used == False,
                PasswordResetToken.expires_at > datetime.now(UTC),
            )
            .first()
        )

        if not reset_token:
            raise ValueError("Invalid or expired reset token.")

        # Validate new password
        validate_password_policy(new_password)

        # Update password
        user = self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        user.password_hash = hash_password(new_password)
        reset_token.used = True
        self.db.commit()

        return True


def _slugify(name: str) -> str:
    """Lowercase, keep letters and digits, collapse runs into single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    return slug[:80]
