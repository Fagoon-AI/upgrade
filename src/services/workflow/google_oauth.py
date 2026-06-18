import json
import secrets
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from loguru import logger

from src.core.config import settings


# ============================================================
# CONFIGURATION
# ============================================================

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Default scopes
DEFAULT_SCOPES = [
    "openid",
    "email",
    "profile",
]

# Provider-specific scopes
PROVIDER_SCOPES = {
    "GMAIL_OAUTH": [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ],
    "GOOGLE_SHEETS": [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ],
    "GOOGLE_DRIVE": [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.readonly",
    ],
    "GOOGLE_CALENDAR": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
}

# State storage (use Redis in production)
_state_storage: Dict[str, Dict[str, Any]] = {}


# ============================================================
# EXCEPTIONS
# ============================================================

class OAuthError(Exception):
    """Base OAuth error."""
    pass


class InvalidStateError(OAuthError):
    """Invalid or expired state parameter."""
    pass


class TokenError(OAuthError):
    """Token exchange or refresh error."""
    pass


class ScopeError(OAuthError):
    """Insufficient or invalid scopes."""
    pass


# ============================================================
# GOOGLE OAUTH SERVICE
# ============================================================

class GoogleOAuthService:
    """
    World-Class Google OAuth Service.

    Features:
    - PKCE support
    - State validation
    - Automatic token refresh
    - Scope management
    - Incremental authorization
    - Error handling

    Usage:
        oauth = GoogleOAuthService()
        url = oauth.get_authorization_url(provider="GMAIL_OAUTH")
        # User visits URL and authorizes
        tokens = oauth.exchange_code_for_token(code, state)
    """

    def __init__(
            self,
            client_id: Optional[str] = None,
            client_secret: Optional[str] = None,
            redirect_uri: Optional[str] = None
    ):
        self.client_id = client_id or settings.GOOGLE_CLIENT_ID
        self.client_secret = client_secret or settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI

        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

    # ============================================================
    # AUTHORIZATION
    # ============================================================

    def get_authorization_url(
            self,
            provider: str = "GOOGLE",
            additional_scopes: List[str] = None,
            user_id: Optional[str] = None,
            include_pkce: bool = True
    ) -> Tuple[str, str]:
        """
        Generates authorization URL.

        Args:
            provider: Provider type (GMAIL_OAUTH, GOOGLE_SHEETS, etc.)
            additional_scopes: Additional scopes to request
            user_id: User ID to associate with state
            include_pkce: Include PKCE challenge

        Returns:
            Tuple of (authorization_url, state)
        """
        # Build scopes
        scopes = DEFAULT_SCOPES.copy()
        scopes.extend(PROVIDER_SCOPES.get(provider, []))

        if additional_scopes:
            scopes.extend(additional_scopes)

        # Remove duplicates while preserving order
        scopes = list(dict.fromkeys(scopes))

        # Generate state
        state = secrets.token_urlsafe(32)

        # Generate PKCE if enabled
        code_verifier = None
        code_challenge = None

        if include_pkce:
            code_verifier = secrets.token_urlsafe(64)
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).decode().rstrip("=")

        # Store state
        _state_storage[state] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "scopes": scopes,
            "user_id": user_id,
            "code_verifier": code_verifier,
        }

        # Build URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }

        if include_pkce:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

        logger.info(
            f"Generated OAuth URL for provider: {provider}",
            extra={"provider": provider, "scopes": scopes}
        )

        return url, state

    def exchange_code_for_token(
            self,
            code: str,
            state: str
    ) -> Dict[str, Any]:
        """
        Exchanges authorization code for tokens.

        Args:
            code: Authorization code from callback
            state: State parameter from callback

        Returns:
            Token data dictionary

        Raises:
            InvalidStateError: If state is invalid or expired
            TokenError: If token exchange fails
        """
        # Validate state
        state_data = self._validate_state(state)

        try:
            # Build token request
            token_data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }

            # Add PKCE verifier if present
            if state_data.get("code_verifier"):
                token_data["code_verifier"] = state_data["code_verifier"]

            # Exchange code for tokens
            import httpx

            response = httpx.post(
                GOOGLE_TOKEN_URL,
                data=token_data,
                timeout=30.0
            )

            if response.status_code != 200:
                error_data = response.json()
                raise TokenError(
                    f"Token exchange failed: {error_data.get('error_description', error_data.get('error'))}"
                )

            tokens = response.json()

            # Build result
            result = {
                "token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "token_uri": GOOGLE_TOKEN_URL,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scopes": state_data.get("scopes", []),
                "expiry": self._calculate_expiry(tokens.get("expires_in", 3600)),
            }

            # Clean up state
            del _state_storage[state]

            logger.info(
                f"Token exchange successful for provider: {state_data.get('provider')}",
                extra={"provider": state_data.get("provider")}
            )

            return result

        except TokenError:
            raise
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            raise TokenError(f"Token exchange failed: {str(e)}")

    def _validate_state(self, state: str) -> Dict[str, Any]:
        """Validates state parameter."""
        if state not in _state_storage:
            raise InvalidStateError("Invalid or expired state parameter")

        state_data = _state_storage[state]

        # Check expiration (10 minutes)
        created_at = datetime.fromisoformat(state_data["created_at"])
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=10):
            del _state_storage[state]
            raise InvalidStateError("State parameter expired")

        return state_data

    def _calculate_expiry(self, expires_in: int) -> str:
        """Calculates token expiry time."""
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return expiry.isoformat()

    # ============================================================
    # TOKEN REFRESH
    # ============================================================

    def refresh_token(
            self,
            credentials_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Refreshes an access token.

        Args:
            credentials_data: Stored credentials dictionary

        Returns:
            Updated credentials dictionary

        Raises:
            TokenError: If refresh fails
        """
        refresh_token = credentials_data.get("refresh_token")

        if not refresh_token:
            raise TokenError("No refresh token available")

        try:
            credentials = Credentials(
                token=credentials_data.get("token"),
                refresh_token=refresh_token,
                token_uri=credentials_data.get("token_uri", GOOGLE_TOKEN_URL),
                client_id=credentials_data.get("client_id", self.client_id),
                client_secret=credentials_data.get("client_secret", self.client_secret),
                scopes=credentials_data.get("scopes", [])
            )

            # Refresh if expired or about to expire
            if credentials.expired or not credentials.valid:
                credentials.refresh(Request())

            # Build result
            return {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token or refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": list(credentials.scopes) if credentials.scopes else credentials_data.get("scopes", []),
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            }

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            raise TokenError(f"Token refresh failed: {str(e)}")

    def is_token_expired(
            self,
            credentials_data: Dict[str, Any],
            buffer_minutes: int = 5
    ) -> bool:
        """
        Checks if token is expired or about to expire.

        Args:
            credentials_data: Stored credentials
            buffer_minutes: Minutes before expiry to consider expired

        Returns:
            True if expired or about to expire
        """
        expiry = credentials_data.get("expiry")

        if not expiry:
            return True

        try:
            expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            buffer = timedelta(minutes=buffer_minutes)

            return datetime.now(timezone.utc) >= (expiry_dt - buffer)
        except Exception:
            return True

    # ============================================================
    # CREDENTIAL HELPERS
    # ============================================================

    def build_credentials(
            self,
            credentials_data: Dict[str, Any]
    ) -> Credentials:
        """
        Builds Google Credentials object from stored data.

        Args:
            credentials_data: Stored credentials dictionary

        Returns:
            Google Credentials object
        """
        return Credentials(
            token=credentials_data.get("token"),
            refresh_token=credentials_data.get("refresh_token"),
            token_uri=credentials_data.get("token_uri", GOOGLE_TOKEN_URL),
            client_id=credentials_data.get("client_id", self.client_id),
            client_secret=credentials_data.get("client_secret", self.client_secret),
            scopes=credentials_data.get("scopes")
        )

    def get_user_info(
            self,
            credentials_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Gets user info from Google.

        Args:
            credentials_data: Stored credentials

        Returns:
            User info dictionary
        """
        import httpx

        token = credentials_data.get("token")

        if not token:
            raise TokenError("No access token available")

        response = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        )

        if response.status_code != 200:
            raise TokenError("Failed to get user info")

        return response.json()

    # ============================================================
    # SCOPE MANAGEMENT
    # ============================================================

    def get_scopes_for_provider(self, provider: str) -> List[str]:
        """Gets required scopes for a provider."""
        scopes = DEFAULT_SCOPES.copy()
        scopes.extend(PROVIDER_SCOPES.get(provider, []))
        return list(dict.fromkeys(scopes))

    def has_required_scopes(
            self,
            credentials_data: Dict[str, Any],
            required_scopes: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Checks if credentials have required scopes.

        Args:
            credentials_data: Stored credentials
            required_scopes: Scopes to check

        Returns:
            Tuple of (has_all_scopes, missing_scopes)
        """
        granted_scopes = set(credentials_data.get("scopes", []))
        required = set(required_scopes)

        missing = required - granted_scopes

        return len(missing) == 0, list(missing)


# Global instance
google_auth = GoogleOAuthService()