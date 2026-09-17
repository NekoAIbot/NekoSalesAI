from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    # Names the workspace created for this user. Optional because the first
    # thing a new signup wants is to be inside the product, not filling in a
    # form; a name is derived from their own when they skip it.
    company_name: str | None = Field(default=None, max_length=150)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    is_admin: bool
    email_verified: bool
    totp_enabled: bool
    organization_id: int | None = None

    model_config = {
        "from_attributes": True
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ===========================
# Password Policy Validation
# ===========================

class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the security policy."""
    pass


def validate_password_policy(password: str) -> None:
    """Validate password meets minimum security requirements.

    Policy:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(password) < 8:
        raise PasswordPolicyError("Password must be at least 8 characters long.")
    if not any(c.isupper() for c in password):
        raise PasswordPolicyError("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        raise PasswordPolicyError("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        raise PasswordPolicyError("Password must contain at least one digit.")


# ===========================
# Email Verification Schemas
# ===========================

class EmailVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


# ===========================
# TOTP MFA Schemas
# ===========================

class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_code: str  # base64-encoded PNG


class TOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TOTPEnableResponse(BaseModel):
    recovery_codes: list[str]


class TOTPStatusResponse(BaseModel):
    enabled: bool


class TOTPLoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str = Field(min_length=6, max_length=6)


# ===========================
# Forgot Password Schemas
# ===========================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ===========================
# Recovery Code Schemas
# ===========================

class RecoveryCodeVerifyRequest(BaseModel):
    email: EmailStr
    password: str
    recovery_code: str
