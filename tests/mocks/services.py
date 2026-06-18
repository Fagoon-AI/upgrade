"""
Mock service implementations for testing.

Provides mock versions of external service dependencies:
- Auth service
- Storage service
- LLM providers
- External APIs
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from unittest.mock import AsyncMock, MagicMock

from faker import Faker

fake = Faker()


class MockAuthService:
    """
    Mock auth service for testing authentication flows.

    Provides controllable responses for:
    - User registration
    - Login
    - Token validation
    - Password operations
    """

    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}
        self.tokens: Dict[str, str] = {}  # token -> user_id
        self.reset_tokens: Dict[str, str] = {}  # token -> user_id

    async def register_user(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mock user registration."""
        if email in self.users:
            raise ValueError("Email already registered")

        user_id = str(uuid.uuid4())
        self.users[email] = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.users[email]

    async def authenticate(
        self,
        email: str,
        password: str,
    ) -> Optional[Dict[str, Any]]:
        """Mock authentication."""
        if email not in self.users:
            return None
        # In mock, any password works
        user = self.users[email]
        if not user.get("is_active", True):
            return None
        return {
            "user": user,
            "access_token": f"mock_access_{user['id']}",
            "refresh_token": f"mock_refresh_{user['id']}",
        }

    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Mock token validation."""
        if token.startswith("mock_access_"):
            user_id = token.replace("mock_access_", "")
            for email, user in self.users.items():
                if user["id"] == user_id:
                    return user
        return None

    async def refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Mock token refresh."""
        if refresh_token.startswith("mock_refresh_"):
            user_id = refresh_token.replace("mock_refresh_", "")
            for email, user in self.users.items():
                if user["id"] == user_id:
                    return {
                        "access_token": f"mock_access_{user_id}",
                        "refresh_token": f"mock_refresh_{user_id}",
                    }
        return None

    def add_test_user(
        self,
        email: str = None,
        user_id: str = None,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """Add a test user directly."""
        email = email or fake.email()
        user_id = user_id or str(uuid.uuid4())
        self.users[email] = {
            "id": user_id,
            "email": email,
            "full_name": fake.name(),
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.users[email]


class MockStorageService:
    """
    Mock storage service for testing file operations.

    Simulates cloud storage operations without actual API calls.
    """

    def __init__(self):
        self.files: Dict[str, bytes] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}

    async def upload_file(
        self,
        file_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Mock file upload."""
        self.files[file_path] = content
        self.metadata[file_path] = {
            "content_type": content_type,
            "size": len(content),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        return {
            "path": file_path,
            "url": f"https://storage.test.com/{file_path}",
            "size": len(content),
        }

    async def download_file(self, file_path: str) -> Optional[bytes]:
        """Mock file download."""
        return self.files.get(file_path)

    async def delete_file(self, file_path: str) -> bool:
        """Mock file deletion."""
        if file_path in self.files:
            del self.files[file_path]
            self.metadata.pop(file_path, None)
            return True
        return False

    async def get_signed_url(
        self,
        file_path: str,
        expiry_seconds: int = 3600,
    ) -> Optional[str]:
        """Mock signed URL generation."""
        if file_path in self.files:
            return f"https://storage.test.com/{file_path}?token=mock_signed_token"
        return None

    async def list_files(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Mock file listing."""
        files = []
        for path, meta in self.metadata.items():
            if path.startswith(prefix):
                files.append({
                    "path": path,
                    "size": meta["size"],
                    "content_type": meta["content_type"],
                    "uploaded_at": meta["uploaded_at"],
                })
                if len(files) >= limit:
                    break
        return files


class MockLLMProvider:
    """
    Mock LLM provider for testing AI operations.

    Simulates responses from OpenAI, Anthropic, etc.
    """

    def __init__(self, provider: str = "openai"):
        self.provider = provider
        self.responses: List[str] = []
        self.call_history: List[Dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Mock LLM error"

    def set_responses(self, responses: List[str]):
        """Set predetermined responses."""
        self.responses = responses

    def set_failure(self, should_fail: bool, message: str = "Mock LLM error"):
        """Configure failure mode."""
        self.should_fail = should_fail
        self.failure_message = message

    async def generate(
        self,
        prompt: str,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Mock text generation."""
        self.call_history.append({
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if self.should_fail:
            raise Exception(self.failure_message)

        if self.responses:
            response_text = self.responses.pop(0)
        else:
            response_text = f"Mock response to: {prompt[:50]}..."

        return {
            "text": response_text,
            "model": model,
            "provider": self.provider,
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(prompt.split()) + len(response_text.split()),
            },
            "finish_reason": "stop",
        }

    async def generate_embedding(
        self,
        text: str,
        model: str = "text-embedding-ada-002",
    ) -> Dict[str, Any]:
        """Mock embedding generation."""
        self.call_history.append({
            "type": "embedding",
            "text": text,
            "model": model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if self.should_fail:
            raise Exception(self.failure_message)

        # Return fake 768-dim embedding
        import random
        embedding = [random.uniform(-1, 1) for _ in range(768)]

        return {
            "embedding": embedding,
            "model": model,
            "usage": {"total_tokens": len(text.split())},
        }

    def get_call_count(self) -> int:
        """Get number of API calls made."""
        return len(self.call_history)

    def get_last_call(self) -> Optional[Dict[str, Any]]:
        """Get last API call details."""
        return self.call_history[-1] if self.call_history else None

    def clear_history(self):
        """Clear call history."""
        self.call_history.clear()


class MockWebhookClient:
    """
    Mock webhook client for testing webhook triggers.
    """

    def __init__(self):
        self.sent_webhooks: List[Dict[str, Any]] = []
        self.should_fail = False

    async def send(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Mock webhook send."""
        self.sent_webhooks.append({
            "url": url,
            "payload": payload,
            "headers": headers,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if self.should_fail:
            raise Exception("Webhook delivery failed")

        return {
            "status": "delivered",
            "status_code": 200,
            "response": {"success": True},
        }

    def get_sent_count(self) -> int:
        """Get number of webhooks sent."""
        return len(self.sent_webhooks)


def create_mock_celery_task() -> AsyncMock:
    """
    Create a mock Celery task.

    Returns:
        AsyncMock configured as a Celery task
    """
    task = AsyncMock()
    task.delay = MagicMock(return_value=MagicMock(id=str(uuid.uuid4())))
    task.apply_async = MagicMock(return_value=MagicMock(id=str(uuid.uuid4())))
    task.AsyncResult = MagicMock(return_value=MagicMock(
        status="SUCCESS",
        result={"success": True},
        ready=MagicMock(return_value=True),
    ))
    return task


def create_mock_httpx_client() -> AsyncMock:
    """
    Create a mock httpx AsyncClient.

    Returns:
        AsyncMock configured for HTTP operations
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"success": True})
    mock_response.text = "OK"
    mock_response.headers = {}

    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_response)
    client.post = AsyncMock(return_value=mock_response)
    client.put = AsyncMock(return_value=mock_response)
    client.patch = AsyncMock(return_value=mock_response)
    client.delete = AsyncMock(return_value=mock_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    return client
