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
)
from app.auth.service import AuthService
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

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
        raise HTTPException(401, str(e)) from e


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
        raise HTTPException(401, str(e)) from e


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
