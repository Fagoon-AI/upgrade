import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional, Dict, Tuple
from uuid import UUID, uuid4
from dataclasses import dataclass

from jose import jwt, JWTError, ExpiredSignatureError
from passlib.context import CryptContext
from loguru import logger

from src.core.config import settings


# CONSTANTS
ALGORITHM = "HS256"

def _get_secret_key() -> str:
    """Helper to extract raw string from SECRET_KEY (handles both SecretStr and plain str)."""
    key = settings.SECRET_KEY
    if hasattr(key, "get_secret_value"):
        return key.get_secret_value()
    return key

class TokenType:
    """Token type constants."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verify"


# PASSWORD HASHING
# Use Argon2 as primary, with bcrypt as fallback for migration
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="argon2",
    deprecated="auto",
    argon2__memory_cost=65536,  # 64MB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def get_password_hash(password: str) -> str:
    """
    Hash a password using Argon2.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Uses timing-safe comparison to prevent timing attacks.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.warning(f"Password verification error: {e}")
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if password hash needs to be upgraded.

    Useful for migrating from bcrypt to Argon2.

    Args:
        hashed_password: Stored hash

    Returns:
        True if hash should be regenerated
    """
    return pwd_context.needs_update(hashed_password)


# ============================================================
# TOKEN GENERATION
# ============================================================

@dataclass
class TokenPayload:
    """Decoded token payload."""
    sub: str  # Subject (user_id)
    type: str  # Token type
    exp: datetime  # Expiration
    iat: datetime  # Issued at
    jti: str  # JWT ID (for revocation)

    @property
    def user_id(self) -> UUID:
        """Get user ID as UUID."""
        return UUID(self.sub)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(timezone.utc) > self.exp


def create_access_token(
        subject: Union[str, UUID],
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: User ID or identifier
        expires_delta: Custom expiration time
        additional_claims: Extra claims to include

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(subject),
        "type": TokenType.ACCESS,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),  # Unique token ID for revocation
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        _get_secret_key(),
        algorithm=ALGORITHM
    )


def create_refresh_token(
        subject: Union[str, UUID],
        expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token.

    Refresh tokens have longer expiration and are used to get new access tokens.

    Args:
        subject: User ID or identifier
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(subject),
        "type": TokenType.REFRESH,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        _get_secret_key(),
        algorithm=ALGORITHM
    )


def create_password_reset_token(
        subject: Union[str, UUID],
        expires_minutes: int = 30
) -> str:
    """
    Create a password reset token.

    Short-lived token for password reset flows.

    Args:
        subject: User ID
        expires_minutes: Expiration in minutes

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)

    payload = {
        "sub": str(subject),
        "type": TokenType.PASSWORD_RESET,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        _get_secret_key(),
        algorithm=ALGORITHM
    )


def create_email_verification_token(
        subject: Union[str, UUID],
        email: str,
        expires_hours: int = 24
) -> str:
    """
    Create an email verification token.

    Args:
        subject: User ID
        email: Email address to verify
        expires_hours: Expiration in hours

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_hours)

    payload = {
        "sub": str(subject),
        "type": TokenType.EMAIL_VERIFICATION,
        "email": email,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        _get_secret_key(),
        algorithm=ALGORITHM
    )


# ============================================================
# TOKEN VALIDATION
# ============================================================

def decode_token(
        token: str,
        expected_type: Optional[str] = None,
        verify_exp: bool = True
) -> Tuple[Optional[TokenPayload], Optional[str]]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT string
        expected_type: Expected token type (access, refresh, etc.)
        verify_exp: Whether to verify expiration

    Returns:
        Tuple of (TokenPayload or None, error_message or None)
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=[ALGORITHM],
            options={"verify_exp": verify_exp}
        )

        # Validate token type
        token_type = payload.get("type", TokenType.ACCESS)
        if expected_type and token_type != expected_type:
            return None, f"Invalid token type. Expected {expected_type}, got {token_type}"

        # Parse timestamps
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload.get("iat", 0), tz=timezone.utc)

        token_payload = TokenPayload(
            sub=payload["sub"],
            type=token_type,
            exp=exp,
            iat=iat,
            jti=payload.get("jti", "")
        )

        return token_payload, None

    except ExpiredSignatureError:
        return None, "Token has expired"
    except JWTError as e:
        return None, f"Invalid token: {e}"
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        return None, "Token validation failed"


def validate_access_token(token: str) -> Tuple[Optional[TokenPayload], Optional[str]]:
    """
    Validate an access token.

    Args:
        token: JWT string

    Returns:
        Tuple of (TokenPayload or None, error_message or None)
    """
    return decode_token(token, expected_type=TokenType.ACCESS)


def validate_refresh_token(token: str) -> Tuple[Optional[TokenPayload], Optional[str]]:
    """
    Validate a refresh token.

    Args:
        token: JWT string

    Returns:
        Tuple of (TokenPayload or None, error_message or None)
    """
    return decode_token(token, expected_type=TokenType.REFRESH)


def get_token_jti(token: str) -> Optional[str]:
    """
    Extract JTI (JWT ID) from token without full validation.

    Useful for token revocation checks.

    Args:
        token: JWT string

    Returns:
        JTI string or None
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=[ALGORITHM],
            options={"verify_exp": False}
        )
        return payload.get("jti")
    except Exception:
        return None


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def generate_api_key(prefix: str = "wf") -> str:
    """
    Generate a secure API key.

    Format: prefix_randomstring

    Args:
        prefix: Key prefix for identification

    Returns:
        API key string
    """
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.

    Uses SHA-256 for fast lookup (API keys are high-entropy).

    Args:
        api_key: Plain API key

    Returns:
        Hashed API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.

    Args:
        length: Number of bytes (output will be longer due to encoding)

    Returns:
        URL-safe base64 encoded token
    """
    return secrets.token_urlsafe(length)


def constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time.

    Prevents timing attacks.

    Args:
        a: First string
        b: Second string

    Returns:
        True if equal, False otherwise
    """
    return secrets.compare_digest(a, b)

# Re-export for workflow compatibility
from src.core.encryption import decrypt_credentials  # noqa: F401

