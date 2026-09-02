import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_temporary_password(length: int = 10) -> str:
    """Human-typeable temporary password for worker invitations."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_secure_token() -> str:
    """A high-entropy, URL-safe token for one-time invitation links. Only
    its hash (see hash_token) is ever persisted."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Returns (encoded_jwt, jti)."""
    settings = get_settings()
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    to_encode: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": jti,
    }
    if extra_claims:
        to_encode.update(extra_claims)
    encoded = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded, jti


def create_access_token(user_id: uuid.UUID, extra_claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    token, _ = _create_token(
        subject=str(user_id),
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims=extra_claims,
    )
    return token


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at) — caller persists jti for revocation tracking."""
    settings = get_settings()
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    token, jti = _create_token(subject=str(user_id), token_type="refresh", expires_delta=expires_delta)
    expires_at = datetime.now(timezone.utc) + expires_delta
    return token, jti, expires_at


def decode_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
