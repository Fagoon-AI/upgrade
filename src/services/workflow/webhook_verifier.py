import hmac
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger


# VERIFICATION RESULT

@dataclass
class VerificationResult:
    """Result of webhook signature verification."""
    is_valid: bool
    provider: str
    error: Optional[str] = None
    timestamp: Optional[datetime] = None
    event_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "provider": self.provider,
            "error": self.error,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_id": self.event_id
        }


# ============================================================
# PROVIDER-SPECIFIC VERIFIERS
# ============================================================

class BaseWebhookVerifier(ABC):
    """Base class for provider-specific webhook verifiers."""

    provider_name: str = "base"

    # Timestamp tolerance (seconds) for replay protection
    timestamp_tolerance: int = 300  # 5 minutes

    @abstractmethod
    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """Verify webhook signature."""
        pass

    def _timing_safe_compare(self, a: str, b: str) -> bool:
        """Timing-safe string comparison."""
        return hmac.compare_digest(a, b)

    def _check_timestamp(self, timestamp: int) -> Tuple[bool, Optional[str]]:
        """
        Validates timestamp is within tolerance.

        Returns:
            Tuple of (is_valid, error_message)
        """
        now = int(time.time())
        age = abs(now - timestamp)

        if age > self.timestamp_tolerance:
            return False, f"Timestamp too old ({age}s > {self.timestamp_tolerance}s tolerance)"

        return True, None


class GenericHMACVerifier(BaseWebhookVerifier):
    """Generic HMAC-SHA256 verifier for custom webhooks."""

    provider_name = "generic"

    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Verifies generic HMAC-SHA256 signature.

        Expected signature format: hex-encoded HMAC-SHA256
        """
        try:
            expected = hmac.new(
                secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()

            # Handle common prefixes
            clean_signature = signature
            for prefix in ['sha256=', 'sha256:', 'hmac-sha256=']:
                if signature.lower().startswith(prefix):
                    clean_signature = signature[len(prefix):]
                    break

            is_valid = self._timing_safe_compare(expected, clean_signature.lower())

            return VerificationResult(
                is_valid=is_valid,
                provider=self.provider_name,
                error=None if is_valid else "Signature mismatch"
            )

        except Exception as e:
            return VerificationResult(
                is_valid=False,
                provider=self.provider_name,
                error=f"Verification error: {e}"
            )


class GitHubVerifier(BaseWebhookVerifier):
    """GitHub webhook signature verifier."""

    provider_name = "github"

    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Verifies GitHub webhook signature.

        GitHub format: sha256=<hex-signature>
        Header: X-Hub-Signature-256
        """
        try:
            # GitHub uses sha256= prefix
            if not signature.startswith('sha256='):
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Invalid signature format (expected sha256= prefix)"
                )

            received_sig = signature[7:]  # Remove 'sha256=' prefix

            expected = hmac.new(
                secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()

            is_valid = self._timing_safe_compare(expected, received_sig.lower())

            # Extract event ID from headers if available
            event_id = None
            if headers:
                event_id = headers.get('x-github-delivery') or headers.get('X-GitHub-Delivery')

            return VerificationResult(
                is_valid=is_valid,
                provider=self.provider_name,
                error=None if is_valid else "Signature mismatch",
                event_id=event_id
            )

        except Exception as e:
            return VerificationResult(
                is_valid=False,
                provider=self.provider_name,
                error=f"Verification error: {e}"
            )


class StripeVerifier(BaseWebhookVerifier):
    """
    Stripe webhook signature verifier.

    Stripe uses a complex signature format with timestamp and multiple signatures.
    """

    provider_name = "stripe"
    timestamp_tolerance = 300  # 5 minutes

    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Verifies Stripe webhook signature.

        Stripe format: t=<timestamp>,v1=<signature>,v1=<signature2>,...
        Header: Stripe-Signature

        The payload to sign is: <timestamp>.<payload>
        """
        try:
            # Parse the signature header
            elements = self._parse_signature_header(signature)

            if not elements:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Invalid signature format"
                )

            timestamp = elements.get('t')
            signatures = elements.get('v1', [])

            if not timestamp:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Missing timestamp in signature"
                )

            if not signatures:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Missing v1 signature"
                )

            # Validate timestamp (replay protection)
            try:
                ts_int = int(timestamp)
            except ValueError:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Invalid timestamp format"
                )

            ts_valid, ts_error = self._check_timestamp(ts_int)
            if not ts_valid:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error=ts_error
                )

            # Compute expected signature
            # Stripe signs: timestamp.payload
            payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else payload
            signed_payload = f"{timestamp}.{payload_str}"

            expected = hmac.new(
                secret.encode('utf-8'),
                signed_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Check against all provided v1 signatures (Stripe may send multiple)
            is_valid = any(
                self._timing_safe_compare(expected, sig)
                for sig in signatures
            )

            return VerificationResult(
                is_valid=is_valid,
                provider=self.provider_name,
                error=None if is_valid else "Signature mismatch",
                timestamp=datetime.fromtimestamp(ts_int, tz=timezone.utc)
            )

        except Exception as e:
            return VerificationResult(
                is_valid=False,
                provider=self.provider_name,
                error=f"Verification error: {e}"
            )

    def _parse_signature_header(self, header: str) -> Dict[str, Any]:
        """
        Parses Stripe signature header.

        Format: t=timestamp,v1=sig1,v1=sig2,v0=old_sig

        Returns dict with 't' as string and 'v1' as list of signatures.
        """
        result: Dict[str, Any] = {'v1': []}

        if not header:
            return result

        # Split by comma and parse key=value pairs
        for item in header.split(','):
            item = item.strip()
            if '=' not in item:
                continue

            # Handle the case where value might contain '='
            key, _, value = item.partition('=')
            key = key.strip()
            value = value.strip()

            if key == 't':
                result['t'] = value
            elif key == 'v1':
                result['v1'].append(value)
            elif key == 'v0':
                # Legacy signature, store but prefer v1
                result['v0'] = value

        return result


class SlackVerifier(BaseWebhookVerifier):
    """Slack webhook signature verifier."""

    provider_name = "slack"
    timestamp_tolerance = 300  # 5 minutes

    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Verifies Slack webhook signature.

        Slack format: v0=<signature>
        Headers: X-Slack-Signature, X-Slack-Request-Timestamp

        The payload to sign is: v0:<timestamp>:<payload>
        """
        try:
            # Get timestamp from headers
            timestamp = None
            if headers:
                timestamp = (
                        headers.get('x-slack-request-timestamp') or
                        headers.get('X-Slack-Request-Timestamp')
                )

            if not timestamp:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Missing X-Slack-Request-Timestamp header"
                )

            # Validate timestamp
            try:
                ts_int = int(timestamp)
            except ValueError:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error="Invalid timestamp format"
                )

            ts_valid, ts_error = self._check_timestamp(ts_int)
            if not ts_valid:
                return VerificationResult(
                    is_valid=False,
                    provider=self.provider_name,
                    error=ts_error
                )

            # Build signature base string
            payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else payload
            sig_basestring = f"v0:{timestamp}:{payload_str}"

            # Compute expected signature
            expected = 'v0=' + hmac.new(
                secret.encode('utf-8'),
                sig_basestring.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            is_valid = self._timing_safe_compare(expected, signature)

            return VerificationResult(
                is_valid=is_valid,
                provider=self.provider_name,
                error=None if is_valid else "Signature mismatch",
                timestamp=datetime.fromtimestamp(ts_int, tz=timezone.utc)
            )

        except Exception as e:
            return VerificationResult(
                is_valid=False,
                provider=self.provider_name,
                error=f"Verification error: {e}"
            )


class ShopifyVerifier(BaseWebhookVerifier):
    """Shopify webhook signature verifier."""

    provider_name = "shopify"

    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Verifies Shopify webhook signature.

        Shopify format: base64-encoded HMAC-SHA256
        Header: X-Shopify-Hmac-SHA256
        """
        try:
            import base64

            expected = base64.b64encode(
                hmac.new(
                    secret.encode('utf-8'),
                    payload,
                    hashlib.sha256
                ).digest()
            ).decode('utf-8')

            is_valid = self._timing_safe_compare(expected, signature)

            # Extract event ID
            event_id = None
            if headers:
                event_id = (
                        headers.get('x-shopify-webhook-id') or
                        headers.get('X-Shopify-Webhook-Id')
                )

            return VerificationResult(
                is_valid=is_valid,
                provider=self.provider_name,
                error=None if is_valid else "Signature mismatch",
                event_id=event_id
            )

        except Exception as e:
            return VerificationResult(
                is_valid=False,
                provider=self.provider_name,
                error=f"Verification error: {e}"
            )


class TwilioVerifier(BaseWebhookVerifier):
    """Twilio webhook signature verifier."""

    provider_name = "twilio"

    def verify(
            self,
            payload: bytes,
            signature: str,
            secret: str,
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Verifies Twilio webhook signature.

        Twilio signs the full URL + sorted POST parameters
        Header: X-Twilio-Signature
        """
        # Note: Twilio verification requires the full URL
        # For simplicity, this implementation handles the basic case
        try:
            import base64

            expected = base64.b64encode(
                hmac.new(
                    secret.encode('utf-8'),
                    payload,
                    hashlib.sha1  # Twilio uses SHA1
                ).digest()
            ).decode('utf-8')

            is_valid = self._timing_safe_compare(expected, signature)

            return VerificationResult(
                is_valid=is_valid,
                provider=self.provider_name,
                error=None if is_valid else "Signature mismatch"
            )

        except Exception as e:
            return VerificationResult(
                is_valid=False,
                provider=self.provider_name,
                error=f"Verification error: {e}"
            )


# ============================================================
# MAIN WEBHOOK VERIFIER
# ============================================================

class WebhookVerifier:
    """
    World-Class Webhook Signature Verifier.

    Supports multiple providers with automatic detection:
    - GitHub
    - Stripe
    - Slack
    - Shopify
    - Twilio
    - Generic HMAC-SHA256

    Usage:
        result = WebhookVerifier.verify_signature(
            payload=request_body,
            signature=request.headers.get('X-Hub-Signature-256'),
            secret=webhook_secret,
            provider_type="github"
        )

        if not result.is_valid:
            raise HTTPException(401, result.error)
    """

    # Provider verifier registry
    _verifiers: Dict[str, BaseWebhookVerifier] = {
        "generic": GenericHMACVerifier(),
        "github": GitHubVerifier(),
        "stripe": StripeVerifier(),
        "slack": SlackVerifier(),
        "shopify": ShopifyVerifier(),
        "twilio": TwilioVerifier(),
    }

    @classmethod
    def verify_signature(
            cls,
            payload: bytes,
            signature: str,
            secret: str,
            provider_type: str = "generic",
            headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Validates the integrity and authenticity of a webhook request.

        Returns:
            True if valid, False otherwise

        Note: For more details, use verify() instead.
        """
        result = cls.verify(payload, signature, secret, provider_type, headers)
        return result.is_valid

    @classmethod
    def verify(
            cls,
            payload: bytes,
            signature: str,
            secret: str,
            provider_type: str = "generic",
            headers: Optional[Dict[str, str]] = None
    ) -> VerificationResult:
        """
        Validates webhook signature with detailed result.

        Args:
            payload: Raw request body bytes
            signature: Signature from webhook header
            secret: Webhook secret key
            provider_type: Provider name (github, stripe, slack, etc.)
            headers: Optional dict of request headers (needed for some providers)

        Returns:
            VerificationResult with details
        """
        # Handle missing secret
        if not secret:
            logger.warning("⚠️ Webhook secret not configured")
            return VerificationResult(
                is_valid=False,
                provider=provider_type,
                error="Webhook secret not configured"
            )

        # Handle missing signature
        if not signature:
            return VerificationResult(
                is_valid=False,
                provider=provider_type,
                error="Missing signature"
            )

        # Find appropriate verifier
        provider_key = provider_type.lower().strip()

        # Auto-detect provider from known patterns
        if provider_key not in cls._verifiers:
            provider_key = cls._detect_provider(provider_type)

        verifier = cls._verifiers.get(provider_key, cls._verifiers["generic"])

        try:
            result = verifier.verify(payload, signature, secret, headers)

            if not result.is_valid:
                logger.warning(
                    f"Webhook verification failed for {provider_type}: {result.error}"
                )

            return result

        except Exception as e:
            logger.error(f"Webhook verification error: {e}")
            return VerificationResult(
                is_valid=False,
                provider=provider_type,
                error=f"Verification exception: {e}"
            )

    @classmethod
    def _detect_provider(cls, provider_hint: str) -> str:
        """Detects provider from hint string."""
        hint_lower = provider_hint.lower()

        for provider in cls._verifiers.keys():
            if provider in hint_lower:
                return provider

        return "generic"

    @classmethod
    def register_verifier(cls, name: str, verifier: BaseWebhookVerifier) -> None:
        """Registers a custom webhook verifier."""
        cls._verifiers[name.lower()] = verifier

    @classmethod
    def list_providers(cls) -> List[str]:
        """Returns list of supported providers."""
        return list(cls._verifiers.keys())