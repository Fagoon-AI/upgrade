import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict, Any, List
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from loguru import logger

from src.dao.user_dao import UserDAO
from src.models.sql.workflow.user import User
from src.schemas.workflow.auth import UserCreate, LoginRequest
from src.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token
)
from src.core.config import settings


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class AuthConfig:
    """Authentication configuration."""
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    password_min_length: int = 8
    password_max_length: int = 128
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    refresh_token_rotation: bool = True
    session_absolute_timeout_hours: int = 24 * 7  # 7 days


# Common weak passwords to block
WEAK_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "monkey", "1234567", "letmein", "trustno1", "dragon",
    "baseball", "iloveyou", "master", "sunshine", "ashley",
    "bailey", "shadow", "123123", "654321", "superman",
    "qazwsx", "michael", "football", "password1", "password123"
}


# ============================================================
# PASSWORD VALIDATOR
# ============================================================

class PasswordValidator:
    """Validates password strength and policies."""

    def __init__(self, config: Optional[AuthConfig] = None):
        self.config = config or AuthConfig()

    def validate(self, password: str, email: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Validates password against security policies.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Length check
        if len(password) < self.config.password_min_length:
            errors.append(f"Password must be at least {self.config.password_min_length} characters")

        if len(password) > self.config.password_max_length:
            errors.append(f"Password must be at most {self.config.password_max_length} characters")

        # Complexity checks
        if self.config.password_require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")

        if self.config.password_require_lowercase and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")

        if self.config.password_require_digit and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")

        if self.config.password_require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")

        # Check for common weak passwords
        if password.lower() in WEAK_PASSWORDS:
            errors.append("Password is too common. Please choose a stronger password")

        # Check if password contains email
        if email:
            email_local = email.split('@')[0].lower()
            if len(email_local) > 3 and email_local in password.lower():
                errors.append("Password should not contain your email address")

        # Check for repeated characters
        if re.search(r'(.)\1{3,}', password):
            errors.append("Password should not contain more than 3 repeated characters")

        return len(errors) == 0, errors

    def get_strength(self, password: str) -> Dict[str, Any]:
        """
        Calculates password strength score.

        Returns:
            Dict with score (0-100) and strength level
        """
        score = 0

        # Length score (up to 25 points)
        score += min(len(password) * 2, 25)

        # Complexity score (up to 40 points)
        if re.search(r'[a-z]', password):
            score += 10
        if re.search(r'[A-Z]', password):
            score += 10
        if re.search(r'\d', password):
            score += 10
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            score += 10

        # Variety score (up to 35 points)
        unique_chars = len(set(password))
        score += min(unique_chars * 2, 35)

        # Determine strength level
        if score < 30:
            level = "weak"
        elif score < 50:
            level = "fair"
        elif score < 70:
            level = "good"
        elif score < 90:
            level = "strong"
        else:
            level = "excellent"

        return {
            "score": min(score, 100),
            "level": level
        }


# ============================================================
# RATE LIMITER
# ============================================================

class LoginRateLimiter:
    """
    Rate limiter for login attempts.

    Note: For production at scale, use Redis-based rate limiting.
    """

    def __init__(self, config: Optional[AuthConfig] = None):
        self.config = config or AuthConfig()
        self._attempts: Dict[str, List[datetime]] = {}
        self._lockouts: Dict[str, datetime] = {}

    def is_locked(self, identifier: str) -> Tuple[bool, Optional[int]]:
        """
        Checks if identifier is locked out.

        Returns:
            Tuple of (is_locked, seconds_remaining)
        """
        lockout_until = self._lockouts.get(identifier)
        if lockout_until:
            now = datetime.now(timezone.utc)
            if now < lockout_until:
                remaining = int((lockout_until - now).total_seconds())
                return True, remaining
            else:
                del self._lockouts[identifier]

        return False, None

    def record_attempt(self, identifier: str, success: bool) -> None:
        """Records a login attempt."""
        now = datetime.now(timezone.utc)

        if success:
            self._attempts.pop(identifier, None)
            self._lockouts.pop(identifier, None)
            return

        if identifier not in self._attempts:
            self._attempts[identifier] = []

        self._attempts[identifier].append(now)

        # Clean old attempts (keep last 15 minutes)
        cutoff = now - timedelta(minutes=15)
        self._attempts[identifier] = [
            t for t in self._attempts[identifier] if t > cutoff
        ]

        # Check if should lock out
        if len(self._attempts[identifier]) >= self.config.max_login_attempts:
            self._lockouts[identifier] = now + timedelta(
                minutes=self.config.lockout_duration_minutes
            )
            logger.warning(f"Account locked due to too many failed attempts: {identifier}")

    def get_remaining_attempts(self, identifier: str) -> int:
        """Gets remaining login attempts."""
        attempts = len(self._attempts.get(identifier, []))
        return max(0, self.config.max_login_attempts - attempts)


# ============================================================
# AUDIT LOGGER
# ============================================================

class AuthAuditLogger:
    """Logs authentication events for security auditing."""

    @staticmethod
    def log_login_success(user_id: UUID, email: str, ip_address: Optional[str] = None):
        logger.info(f"AUTH_LOGIN_SUCCESS | user_id={user_id} | email={email} | ip={ip_address}")

    @staticmethod
    def log_login_failure(email: str, reason: str, ip_address: Optional[str] = None):
        logger.warning(f"AUTH_LOGIN_FAILURE | email={email} | reason={reason} | ip={ip_address}")

    @staticmethod
    def log_registration(user_id: UUID, email: str, ip_address: Optional[str] = None):
        logger.info(f"AUTH_REGISTRATION | user_id={user_id} | email={email} | ip={ip_address}")

    @staticmethod
    def log_password_change(user_id: UUID, ip_address: Optional[str] = None):
        logger.info(f"AUTH_PASSWORD_CHANGE | user_id={user_id} | ip={ip_address}")

    @staticmethod
    def log_token_refresh(user_id: UUID, ip_address: Optional[str] = None):
        logger.debug(f"AUTH_TOKEN_REFRESH | user_id={user_id} | ip={ip_address}")

    @staticmethod
    def log_lockout(email: str, duration_minutes: int, ip_address: Optional[str] = None):
        logger.warning(f"AUTH_LOCKOUT | email={email} | duration={duration_minutes}m | ip={ip_address}")


# ============================================================
# AUTH SERVICE
# ============================================================

# Global rate limiter instance (consider Redis for distributed systems)
_rate_limiter = LoginRateLimiter()


class AuthService:
    """
    Authentication Service.

    Features:
    - Password strength validation
    - Rate limiting and lockout protection
    - Audit logging
    - Refresh token rotation
    - Session management
    """

    def __init__(
            self,
            user_dao: UserDAO,
            config: Optional[AuthConfig] = None
    ):
        self.user_dao = user_dao
        self.config = config or AuthConfig()
        self.password_validator = PasswordValidator(self.config)
        self.rate_limiter = _rate_limiter
        self.audit = AuthAuditLogger()

    async def register_user(
            self,
            user_in: UserCreate,
            ip_address: Optional[str] = None
    ) -> User:
        """
        Registers a new user with validation.

        Raises:
            HTTPException: If validation fails
        """
        # Normalize email
        email = user_in.email.lower().strip()

        # Check if email already exists
        existing = await self.user_dao.get_by_email(email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Validate password strength
        is_valid, errors = self.password_validator.validate(
            user_in.password,
            email
        )

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Password does not meet requirements",
                    "errors": errors
                }
            )

        # Create user
        now = datetime.now(timezone.utc)
        new_user = User(
            email=email,
            hashed_password=get_password_hash(user_in.password),
            full_name=user_in.full_name.strip() if user_in.full_name else None,
            is_active=True,
            is_superuser=False,
            created_at=now,
            updated_at=now
        )

        created_user = await self.user_dao.create(new_user)

        # Audit log
        self.audit.log_registration(created_user.id, email, ip_address)

        return created_user

    async def authenticate_user(
            self,
            login_data: LoginRequest,
            ip_address: Optional[str] = None
    ) -> Tuple[User, str, str]:
        """
        Authenticates user and returns tokens.

        Returns:
            Tuple of (user, access_token, refresh_token)

        Raises:
            HTTPException: If authentication fails
        """
        email = login_data.email.lower().strip()

        # Check for lockout
        is_locked, remaining = self.rate_limiter.is_locked(email)
        if is_locked:
            self.audit.log_login_failure(email, "account_locked", ip_address)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Account temporarily locked due to too many failed attempts",
                    "retry_after_seconds": remaining
                }
            )

        # Get user
        user = await self.user_dao.get_by_email(email)

        # Verify credentials
        if not user or not verify_password(login_data.password, user.hashed_password):
            self.rate_limiter.record_attempt(email, success=False)
            remaining_attempts = self.rate_limiter.get_remaining_attempts(email)

            self.audit.log_login_failure(email, "invalid_credentials", ip_address)

            detail = "Invalid email or password"
            if remaining_attempts <= 2 and remaining_attempts > 0:
                detail = f"Invalid email or password. {remaining_attempts} attempts remaining"

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail
            )

        # Check if user is active
        if not user.is_active:
            self.audit.log_login_failure(email, "account_inactive", ip_address)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive. Please contact support."
            )

        # Success - clear rate limit
        self.rate_limiter.record_attempt(email, success=True)

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await self.user_dao.update(user)

        # Generate tokens
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        # Audit log
        self.audit.log_login_success(user.id, email, ip_address)

        return user, access_token, refresh_token

    async def refresh_tokens(
            self,
            user_id: UUID,
            ip_address: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Refreshes access and refresh tokens.

        Returns:
            Tuple of (new_access_token, new_refresh_token)
        """
        user = await self.user_dao.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )

        # Generate new tokens
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        # Audit log
        self.audit.log_token_refresh(user.id, ip_address)

        return access_token, refresh_token

    async def change_password(
            self,
            user_id: UUID,
            current_password: str,
            new_password: str,
            ip_address: Optional[str] = None
    ) -> bool:
        """
        Changes user password.

        Returns:
            True if successful
        """
        user = await self.user_dao.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verify current password
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )

        # Validate new password
        is_valid, errors = self.password_validator.validate(new_password, user.email)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "New password does not meet requirements",
                    "errors": errors
                }
            )

        # Check new password is different
        if verify_password(new_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password"
            )

        # Update password
        user.hashed_password = get_password_hash(new_password)
        user.updated_at = datetime.now(timezone.utc)
        await self.user_dao.update(user)

        # Audit log
        self.audit.log_password_change(user.id, ip_address)

        return True

    async def validate_password_strength(
            self,
            password: str,
            email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates password and returns strength info.

        Returns:
            Dict with validation result and strength score
        """
        is_valid, errors = self.password_validator.validate(password, email)
        strength = self.password_validator.get_strength(password)

        return {
            "is_valid": is_valid,
            "errors": errors,
            "strength": strength
        }