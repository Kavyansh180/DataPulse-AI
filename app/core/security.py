from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from app.core.config import get_settings

# Argon2id password hasher (OWASP recommended defaults)
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash plaintext password using Argon2id with cryptographically random salt."""
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string.")
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against an Argon2id hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


def create_access_token(
    user_id: Optional[Any] = None,
    email: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
    claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Issue cryptographically signed JWT access token with strictly pinned algorithm."""
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)

    if expires_delta is not None:
        expire_time = now_utc + expires_delta
    else:
        expire_time = now_utc + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    if isinstance(user_id, dict):
        sub = str(user_id.get("sub", ""))
        user_email = user_id.get("email", "")
    elif claims:
        sub = str(claims.get("sub", ""))
        user_email = claims.get("email", "")
    else:
        sub = str(user_id) if user_id is not None else ""
        user_email = email or ""

    payload: Dict[str, Any] = {
        "sub": sub,
        "email": user_email,
        "iss": "datapulse-ai",
        "iat": int(now_utc.timestamp()),
        "exp": int(expire_time.timestamp()),
    }

    # Explicitly pin the algorithm; never trust incoming or arbitrary algorithms
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """Validate and decode JWT access token with pinned algorithm and issuer verification."""
    settings = get_settings()

    # Reject empty or non-string tokens immediately
    if not token or not isinstance(token, str):
        raise jwt.InvalidTokenError("Token is empty or invalid.")

    # Strictly enforce algorithms list and issuer
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer="datapulse-ai",
        options={
            "require": ["sub", "exp", "iat", "iss"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_iss": True,
        },
    )
