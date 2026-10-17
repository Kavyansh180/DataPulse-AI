from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserRead,
    TokenResponse,
)
from app.services.audit_service import AuditService

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
    description="Create a new user account, hash the password using Argon2id, and return a signed JWT access token.",
)
def register(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    normalized_email = payload.email.lower().strip()

    # Check for existing user with same email
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{normalized_email}' already exists.",
        )

    # Hash password with Argon2id
    hashed_pw = hash_password(payload.password)

    user = User(
        email=normalized_email,
        hashed_password=hashed_pw,
        full_name=payload.full_name.strip() if payload.full_name else None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    AuditService.log_event(
        db=db,
        action="user_registered",
        entity_type="user",
        entity_id=str(user.id),
        details=f"User {user.email} successfully registered.",
    )

    access_token = create_access_token(user_id=user.id, email=user.email)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
        user=UserRead.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT token",
    description="Verify email and Argon2id password hash, and return a signed JWT access token.",
)
def login(
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    normalized_email = payload.email.lower().strip()

    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Please contact support.",
        )

    AuditService.log_event(
        db=db,
        action="user_logged_in",
        entity_type="user",
        entity_id=str(user.id),
        details=f"User {user.email} authenticated.",
    )

    access_token = create_access_token(user_id=user.id, email=user.email)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
        user=UserRead.model_validate(user),
    )


from app.api.deps import get_current_user


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Retrieve the profile of the currently authenticated user.",
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return UserRead.model_validate(current_user)
