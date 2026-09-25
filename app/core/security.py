"""
Security utilities for ResQVision 2.0.

Provides:
  - Password hashing / verification  (bcrypt via passlib)
  - JWT access-token creation / decoding  (python-jose)
  - FastAPI dependencies for optional and required authentication
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return the bcrypt hash of *password*."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Payload to encode (e.g. {"sub": user_id, "role": "admin"}).
        expires_delta: Token lifetime.  Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.now(timezone.utc)
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT token.

    Raises:
        HTTPException 401 — if the token is invalid, expired, or tampered.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict[str, Any]]:
    """
    Optional auth dependency.

    Returns the decoded JWT payload if a valid Bearer token is present,
    or None if no Authorization header was sent.
    Use for endpoints that behave differently for authenticated vs anonymous
    users but do not *require* a login.
    """
    if not credentials:
        return None
    return decode_token(credentials.credentials)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict[str, Any]:
    """
    Required auth dependency.

    Returns the decoded JWT payload.
    Raises HTTP 401 if no token or an invalid token was supplied.
    Use for protected endpoints.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


def require_role(required_role: str):
    """
    Factory that returns a dependency enforcing a minimum role.

    Usage:
        @router.delete("/admin/resource")
        def delete_resource(user=Depends(require_role("admin"))):
            ...
    """
    def _check_role(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "viewer")
        role_hierarchy = {"viewer": 0, "analyst": 1, "admin": 2}
        if role_hierarchy.get(role, 0) < role_hierarchy.get(required_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required; you have '{role}'",
            )
        return user

    return _check_role
