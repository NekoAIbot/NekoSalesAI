from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    ForceChangePasswordRequest,
    ChangePasswordRequest,
    EmailVerificationRequest,
    EmailVerificationVerify,
    ForgotPasswordRequest,
    LoginRequest,
    PhoneVerificationSendRequest,
    PhoneVerificationVerifyRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    TOTPEnableResponse,
    TOTPLoginRequest,
    TOTPSetupResponse,
    TOTPStatusResponse,
    TOTPVerifyRequest,
    UserResponse,
    RecoveryCodeVerifyRequest,
    ClaimWorkspaceRequest,
    CompleteSetupRequest,
)
from app.auth.service import AuthService
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from datetime import UTC

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(UserRepository(db), db)

    try:
        return service.register(payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(UserRepository(db), db)

    try:
        result = service.login(payload)

        return {
            "access_token": result["access_token"],
            "token_type": "bearer",
        }

    except ValueError as e:
        code = status.HTTP_403_FORBIDDEN if str(e) == "EMAIL_UNVERIFIED" else status.HTTP_401_UNAUTHORIZED
        message = "Email verification required." if code == status.HTTP_403_FORBIDDEN else str(e)
        raise HTTPException(status_code=code, detail=message) from e


@router.post(
    "/login/totp",
    response_model=TokenResponse,
)
def login_with_totp(
    payload: TOTPLoginRequest,
    db: Session = Depends(get_db),
):
    """Login with TOTP code for users with MFA enabled."""
    service = AuthService(UserRepository(db), db)

    try:
        result = service.login_with_totp(
            email=payload.email,
            password=payload.password,
            totp_code=payload.totp_code,
        )

        return {
            "access_token": result["access_token"],
            "token_type": "bearer",
        }

    except ValueError as e:
        code = status.HTTP_403_FORBIDDEN if str(e) == "EMAIL_UNVERIFIED" else status.HTTP_401_UNAUTHORIZED
        message = "Email verification required." if code == status.HTTP_403_FORBIDDEN else str(e)
        raise HTTPException(code, message) from e


@router.post(
    "/login/recovery-code",
    response_model=TokenResponse,
)
def login_with_recovery_code(
    payload: RecoveryCodeVerifyRequest,
    db: Session = Depends(get_db),
):
    """Login using a recovery code (bypasses TOTP)."""
    service = AuthService(UserRepository(db), db)

    try:
        result = service.login_with_recovery_code(
            email=payload.email,
            password=payload.password,
            recovery_code=payload.recovery_code,
        )

        return {
            "access_token": result["access_token"],
            "token_type": "bearer",
        }

    except ValueError as e:
        raise HTTPException(401, str(e)) from e


@router.get(
    "/me",
    response_model=UserResponse,
)
def current_user(
    current_user: User = Depends(get_current_user),
):
    return UserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        email_verified=current_user.email_verified,
        totp_enabled=current_user.totp_enabled,
        organization_id=current_user.organization_id,
        organization_name=current_user.organization.name if current_user.organization else None,
    )


@router.put(
    "/profile",
    response_model=UserResponse,
)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update profile information (full_name and optional organization company_name)."""
    service = AuthService(UserRepository(db), db)
    user = service.update_profile(
        current_user,
        payload.full_name,
        payload.company_name,
    )
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        email_verified=user.email_verified,
        totp_enabled=user.totp_enabled,
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else None,
    )


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password securely verifying current password and policy."""
    service = AuthService(UserRepository(db), db)
    try:
        service.change_password(
            current_user,
            payload.current_password,
            payload.new_password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return {"message": "Password updated successfully."}


@router.post(
    "/force-change-password",
    status_code=status.HTTP_200_OK,
)
def force_change_password(
    payload: ForceChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace a temporary password right after the first sign-in."""
    service = AuthService(UserRepository(db), db)
    try:
        service.force_change_password(current_user, payload.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return {"message": "Password updated successfully."}


# ===========================
# Email Verification Routes
# ===========================

@router.post(
    "/email-verification/send",
    status_code=status.HTTP_200_OK,
)
def send_email_verification(
    payload: EmailVerificationRequest,
    db: Session = Depends(get_db),
):
    """Send or resend email verification code."""
    service = AuthService(UserRepository(db), db)

    try:
        service.send_email_verification(payload.email)
        return {"message": "Verification code sent."}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/email-verification/verify",
    status_code=status.HTTP_200_OK,
)
def verify_email(
    payload: EmailVerificationVerify,
    db: Session = Depends(get_db),
):
    """Verify email with the provided code."""
    service = AuthService(UserRepository(db), db)

    try:
        service.verify_email(payload.email, payload.code)
        return {"message": "Email verified successfully."}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/phone/send", status_code=status.HTTP_200_OK)
def send_phone_verification(
    payload: PhoneVerificationSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(UserRepository(db), db)
    try:
        service.send_phone_verification(current_user, payload.phone_number)
        return {"message": "Verification code sent."}
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE if "unavailable" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/phone/verify", status_code=status.HTTP_200_OK)
def verify_phone(
    payload: PhoneVerificationVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(UserRepository(db), db)
    try:
        service.verify_phone(current_user, payload.code)
        return {"message": "Phone verified successfully."}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ===========================
# TOTP MFA Routes
# ===========================

@router.post(
    "/totp/setup",
    response_model=TOTPSetupResponse,
)
def setup_totp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set up TOTP for the current user. Returns secret, URI, and QR code."""
    service = AuthService(UserRepository(db), db)

    try:
        return service.setup_totp(current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/totp/enable",
    response_model=TOTPEnableResponse,
)
def enable_totp(
    payload: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enable TOTP after verifying initial code. Returns recovery codes."""
    service = AuthService(UserRepository(db), db)

    try:
        recovery_codes = service.enable_totp(current_user.id, payload.code)
        return {"recovery_codes": recovery_codes}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/totp/disable",
    status_code=status.HTTP_200_OK,
)
def disable_totp(
    payload: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable TOTP for the current user."""
    service = AuthService(UserRepository(db), db)

    try:
        service.disable_totp(current_user.id, payload.code)
        return {"message": "TOTP disabled successfully."}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get(
    "/totp/status",
    response_model=TOTPStatusResponse,
)
def get_totp_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get TOTP status for the current user."""
    service = AuthService(UserRepository(db), db)

    try:
        return service.get_totp_status(current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/totp/recovery-codes/regenerate",
    response_model=TOTPEnableResponse,
)
def regenerate_recovery_codes(
    payload: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate recovery codes (requires TOTP verification)."""
    service = AuthService(UserRepository(db), db)

    try:
        recovery_codes = service.regenerate_recovery_codes(current_user.id, payload.code)
        return {"recovery_codes": recovery_codes}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ===========================
# Forgot Password Routes
# ===========================

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """Initiate forgot password flow."""
    service = AuthService(UserRepository(db), db)

    service.forgot_password(payload.email)
    return {"message": "If the email exists, a reset link has been sent."}


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Reset password using a signed token."""
    service = AuthService(UserRepository(db), db)

    try:
        service.reset_password(payload.token, payload.new_password)
        return {"message": "Password reset successfully."}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ===========================
# Workspace Setup Claim Routes
# ===========================

@router.post(
    "/claim-workspace",
    status_code=status.HTTP_200_OK,
)
def claim_workspace(
    payload: ClaimWorkspaceRequest,
    db: Session = Depends(get_db),
):
    """Validate a 24-hour single-use workspace claim token with buyer email ownership check."""
    import hashlib
    from app.models.credential_claim import CredentialClaim

    token_hash = hashlib.sha256(payload.claim_token.strip().encode("utf-8")).hexdigest()
    claim = db.query(CredentialClaim).filter(CredentialClaim.token_hash == token_hash).first()

    if not claim:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or unknown setup token.")

    if claim.claimed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This setup link has already been used.")

    if claim.is_expired:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Setup link has expired.")

    if claim.user.email.strip().lower() != payload.email.strip().lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email address does not match the purchase record.")

    return {
        "valid": True,
        "email": claim.user.email,
        "company_name": claim.order.buyer_company or (claim.user.organization.name if claim.user.organization else ""),
        "expires_at": claim.expires_at.isoformat(),
    }


@router.post(
    "/complete-setup",
    status_code=status.HTTP_200_OK,
)
def complete_setup(
    payload: CompleteSetupRequest,
    db: Session = Depends(get_db),
):
    """Complete workspace onboarding: verify token & email, set password, and return API key."""
    import hashlib
    from datetime import datetime
    from sqlalchemy import update
    from app.core.security import hash_password
    from app.models.credential_claim import CredentialClaim
    from app.models.workspace_profile import WorkspaceProfile
    from app.payments.provisioning import ProvisioningService

    token_hash = hashlib.sha256(payload.claim_token.strip().encode("utf-8")).hexdigest()
    claim = db.query(CredentialClaim).filter(CredentialClaim.token_hash == token_hash).first()

    if not claim:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or unknown setup token.")

    if claim.claimed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This setup link has already been used.")

    if claim.is_expired:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Setup link has expired.")

    if claim.user.email.strip().lower() != payload.email.strip().lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email address does not match the purchase record.")

    # Atomic conditional update to claim the token and prevent concurrent race conditions (F-03 / Correction D)
    now = datetime.now(UTC)
    try:
        stmt = (
            update(CredentialClaim)
            .where(
                CredentialClaim.token_hash == token_hash,
                CredentialClaim.claimed_at.is_(None),
            )
            .values(claimed_at=now)
            .execution_options(synchronize_session=False)
        )
        res = db.execute(stmt)
        if res.rowcount == 0:
            db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This setup link has already been used.")

        user = claim.user
        user.password_hash = hash_password(payload.password)
        user.is_active = True

        # Retrieve workspace profile and rotate/fetch the API key once
        profile = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == claim.order_id).first()
        new_api_key = None
        if profile:
            new_api_key = ProvisioningService(db).rotate_api_key(profile, commit=False)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An error occurred while setting up your workspace credentials. Please try again.",
        ) from exc

    return {
        "message": "Workspace setup completed successfully.",
        "email": user.email,
        "api_key": new_api_key,
        "api_key_prefix": profile.api_key_prefix if profile else None,
    }

