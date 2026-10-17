import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRegisterRequest(BaseModel):
    """Payload for new user account registration."""

    email: str = Field(..., max_length=255, description="Unique user email address")
    password: str = Field(..., min_length=8, max_length=128, description="Account password (min 8 characters)")
    full_name: Optional[str] = Field(default=None, max_length=255, description="User full display name")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        # Ensure at least 1 digit or special character or mixed case
        if not any(c.isdigit() for c in v) and not any(not c.isalnum() for c in v):
            raise ValueError("Password must contain at least one number or special character.")
        return v


class UserLoginRequest(BaseModel):
    """Payload for user authentication / login."""

    email: str = Field(..., max_length=255, description="Registered email address")
    password: str = Field(..., min_length=1, description="Account password")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserRead(BaseModel):
    """Public user identity profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT bearer token response on successful authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=1800, description="Token validity duration in seconds (30 minutes)")
    user: UserRead
