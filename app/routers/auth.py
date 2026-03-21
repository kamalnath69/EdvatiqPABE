import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from ..utils import auth, dependencies
from ..schemas import (
    AdminBootstrapIn,
    Token,
    UserOut,
    UserInDB,
    EmailVerificationRequest,
    VerifyEmailIn,
    ForgotPasswordIn,
    ResetPasswordIn,
    SignupEmailRequest,
    SignupEmailVerify,
    SignupAvailabilityOut,
)
from ..utils.auth import create_access_token, get_password_hash
from ..utils.email import build_password_reset_email, build_signup_verification_email, send_email
from ..utils.notifications import send_onboarding_emails, send_verification_email
from ..utils.verification import (
    consume_email_verification,
    consume_password_reset,
    create_password_reset,
    create_signup_verification,
    consume_signup_verification,
    is_signup_email_verified,
)
from ..db import db
from ..utils.roles import normalize_role

EMAIL_VERIFICATION_REQUIRED = os.getenv("EMAIL_VERIFICATION_REQUIRED", "true").lower() in ("1", "true", "yes")


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap-admin", response_model=UserOut, status_code=201)
async def bootstrap_admin(payload: AdminBootstrapIn):
    existing_admin = await db.users.find_one({"role": "admin"})
    if existing_admin:
        raise HTTPException(
            status_code=403,
            detail="Bootstrap disabled. Admin already exists.",
        )

    existing_user = await auth.get_user(payload.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    try:
        hashed_password = get_password_hash(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    email_verified = False if payload.email else True
    user_doc = {
        "username": payload.username,
        "hashed_password": hashed_password,
        "role": "admin",
        "academy_id": None,
        "full_name": payload.full_name,
        "email": payload.email,
        "email_verified": email_verified,
        "email_verified_at": datetime.utcnow().timestamp() if email_verified else None,
    }

    await auth.create_user(user_doc)
    try:
        await send_onboarding_emails(user_doc)
    except Exception:
        pass
    return UserOut(**user_doc)

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if EMAIL_VERIFICATION_REQUIRED and user.email and not getattr(user, "email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email to continue.",
        )
    access_token = create_access_token(data={"sub": user.username, "role": normalize_role(user.role)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: UserInDB = Depends(dependencies.get_current_active_user)):
    return current_user


async def _resolve_user_by_identity(identity: str) -> UserInDB | None:
    value = (identity or "").strip()
    if not value:
        return None
    if "@" in value:
        user = await db.users.find_one({"email": value})
    else:
        user = await db.users.find_one({"username": value})
    if not user:
        return None
    return UserInDB(**user)


@router.post("/request-email-verification")
async def request_email_verification(payload: EmailVerificationRequest):
    user = await _resolve_user_by_identity(payload.identity)
    if not user or not user.email:
        return {"detail": "If an account exists, a verification code has been sent."}
    if getattr(user, "email_verified", False):
        return {"detail": "Email already verified."}
    try:
        await send_verification_email(user.dict())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send verification email: {exc}") from exc
    return {"detail": "Verification code sent."}


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailIn):
    user = await _resolve_user_by_identity(payload.identity)
    if not user or not user.email:
        raise HTTPException(status_code=404, detail="User not found.")
    verified = await consume_email_verification(user.username, user.email, payload.code)
    if not verified:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    now = datetime.utcnow().timestamp()
    await db.users.update_one(
        {"username": user.username},
        {"$set": {"email_verified": True, "email_verified_at": now}},
    )
    return {"detail": "Email verified successfully."}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn):
    user = await _resolve_user_by_identity(payload.identity)
    if not user or not user.email:
        return {"detail": "If an account exists, a reset code has been sent."}
    code = await create_password_reset(user.username, user.email)
    subject, html, text = build_password_reset_email(code, user.full_name or user.username)
    try:
        send_email(user.email, subject, html, text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send reset email: {exc}") from exc
    return {"detail": "Password reset code sent."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn):
    user = await _resolve_user_by_identity(payload.identity)
    if not user or not user.email:
        raise HTTPException(status_code=404, detail="User not found.")
    valid = await consume_password_reset(user.username, user.email, payload.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
    try:
        hashed = get_password_hash(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.users.update_one({"username": user.username}, {"$set": {"hashed_password": hashed}})
    return {"detail": "Password updated successfully."}


@router.post("/request-signup-verification")
async def request_signup_verification(payload: SignupEmailRequest):
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered.")
    if await is_signup_email_verified(email):
        return {"detail": "Email already verified for checkout."}
    code = await create_signup_verification(email)
    subject, html, text = build_signup_verification_email(code, email.split("@")[0] or "there")
    try:
        send_email(email, subject, html, text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send verification email: {exc}") from exc
    return {"detail": "Verification code sent."}


@router.post("/verify-signup-email")
async def verify_signup_email(payload: SignupEmailVerify):
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    verified = await consume_signup_verification(email, payload.code)
    if not verified:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    return {"detail": "Email verified for checkout."}


@router.get("/signup-availability", response_model=SignupAvailabilityOut)
async def signup_availability(username: str = "", email: str = ""):
    normalized_username = (username or "").strip()
    normalized_email = (email or "").strip().lower()
    username_available = True
    email_available = True
    if normalized_username:
      username_available = await db.users.find_one({"username": normalized_username}) is None
    if normalized_email:
      email_available = await db.users.find_one({"email": normalized_email}) is None
    return SignupAvailabilityOut(
        username_available=username_available,
        email_available=email_available,
    )
