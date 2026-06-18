import json
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto
from src.schemas.workflow.response import APIResponse
from src.core.config import settings


router = APIRouter()


# ============================================================
# SCHEMAS
# ============================================================

class ConnectionCreate(BaseModel):
    """Schema for creating a connection."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Connection name"
    )
    provider: str = Field(
        ...,
        description="Provider type (e.g., GOOGLE, OPENAI, SUPABASE)"
    )
    credentials: Dict[str, Any] = Field(
        ...,
        description="Provider-specific credentials"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)
        return v

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v: str) -> str:
        return v.upper().strip()


class ConnectionUpdate(BaseModel):
    """Schema for updating a connection."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    credentials: Optional[Dict[str, Any]] = None


class ConnectionResponse(BaseModel):
    """Schema for connection response (no secrets)."""
    id: UUID
    name: str
    provider: str
    created_at: datetime
    updated_at: datetime
    is_valid: Optional[bool] = None
    last_used: Optional[datetime] = None


class ConnectionDetailResponse(ConnectionResponse):
    """Detailed connection response with masked credentials."""
    masked_credentials: Dict[str, str] = Field(
        default_factory=dict,
        description="Credentials with values masked"
    )


# ============================================================
# PROVIDER CONFIGURATION
# ============================================================

# Supported providers and their required credentials
PROVIDER_CONFIG = {
    "GOOGLE": {
        "display_name": "Google",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": True
    },
    "GMAIL_OAUTH": {
        "display_name": "Gmail (OAuth)",
        "required_fields": ["token", "refresh_token"],
        "optional_fields": ["client_id", "client_secret"],
        "oauth_supported": True
    },
    "OPENAI": {
        "display_name": "OpenAI",
        "required_fields": ["api_key"],
        "optional_fields": ["organization_id"],
        "oauth_supported": False
    },
    "ANTHROPIC": {
        "display_name": "Anthropic",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "MISTRAL": {
        "display_name": "Mistral AI",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "PERPLEXITY": {
        "display_name": "Perplexity AI",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "SUPABASE": {
        "display_name": "Supabase",
        "required_fields": ["project_url", "service_role_key"],
        "optional_fields": ["anon_key"],
        "oauth_supported": False
    },
    "SLACK": {
        "display_name": "Slack",
        "required_fields": ["bot_token"],
        "optional_fields": ["webhook_url", "signing_secret"],
        "oauth_supported": True
    },
    "GITHUB": {
        "display_name": "GitHub",
        "required_fields": ["access_token"],
        "optional_fields": [],
        "oauth_supported": True
    },
    "STRIPE": {
        "display_name": "Stripe",
        "required_fields": ["secret_key"],
        "optional_fields": ["webhook_secret"],
        "oauth_supported": False
    }
}


# ============================================================
# HELPERS
# ============================================================

def validate_credentials(provider: str, credentials: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validates credentials for a provider."""
    config = PROVIDER_CONFIG.get(provider)

    if not config:
        # Unknown provider - accept any credentials
        return True, None

    # Check required fields
    for field in config["required_fields"]:
        if field not in credentials or not credentials[field]:
            return False, f"Missing required field: {field}"

    return True, None


def mask_credentials(credentials: Dict[str, Any]) -> Dict[str, str]:
    """Masks credential values for safe display."""
    masked = {}

    for key, value in credentials.items():
        if value is None:
            masked[key] = "(not set)"
        elif isinstance(value, str):
            if len(value) <= 8:
                masked[key] = "****"
            else:
                # Show first 4 and last 4 characters
                masked[key] = f"{value[:4]}...{value[-4:]}"
        else:
            masked[key] = "(set)"

    return masked


async def get_connection_or_404(
        connection_id: UUID,
        current_user: User,
        db: AsyncSession
) -> Connection:
    """Gets connection or raises 404."""
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id)
    )
    connection = result.scalars().first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found"
        )

    if connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this connection"
        )

    return connection


# ============================================================
# CRUD ENDPOINTS
# ============================================================

@router.post(
    "/",
    response_model=APIResponse[ConnectionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create connection",
    description="Create a new provider connection"
)
async def create_connection(
        request: Request,
        conn_in: ConnectionCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Creates a new connection."""
    # Validate credentials
    is_valid, error = validate_credentials(conn_in.provider, conn_in.credentials)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )

    # Encrypt credentials
    encrypted = crypto.encrypt(json.dumps(conn_in.credentials))

    # Create connection
    now = datetime.now(timezone.utc)
    new_conn = Connection(
        name=conn_in.name,
        provider=conn_in.provider,
        user_id=current_user.id,
        encrypted_credentials=encrypted,
        created_at=now,
        updated_at=now
    )

    db.add(new_conn)
    await db.commit()
    await db.refresh(new_conn)

    logger.info(
        f"Connection created: {new_conn.id}",
        extra={
            "user_id": str(current_user.id),
            "provider": conn_in.provider,
            "connection_id": str(new_conn.id)
        }
    )

    return APIResponse(
        success=True,
        message="Connection created securely",
        data=ConnectionResponse(
            id=new_conn.id,
            name=new_conn.name,
            provider=new_conn.provider,
            created_at=new_conn.created_at,
            updated_at=new_conn.updated_at
        )
    )


@router.get(
    "/",
    response_model=APIResponse[List[ConnectionResponse]],
    summary="List connections",
    description="List all connections for current user"
)
async def list_connections(
        provider: Optional[str] = Query(None, description="Filter by provider"),
        search: Optional[str] = Query(None, description="Search by name"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Lists all connections."""
    query = select(Connection).where(Connection.user_id == current_user.id)

    if provider:
        query = query.where(Connection.provider == provider.upper())

    if search:
        query = query.where(Connection.name.ilike(f"%{search}%"))

    query = query.order_by(Connection.created_at.desc())

    result = await db.execute(query)
    connections = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {len(connections)} connections",
        data=[
            ConnectionResponse(
                id=c.id,
                name=c.name,
                provider=c.provider,
                created_at=c.created_at,
                updated_at=c.updated_at
            )
            for c in connections
        ]
    )


@router.get(
    "/{connection_id}",
    response_model=APIResponse[ConnectionDetailResponse],
    summary="Get connection",
    description="Get connection details with masked credentials"
)
async def get_connection(
        connection_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Gets connection details."""
    connection = await get_connection_or_404(connection_id, current_user, db)

    # Decrypt and mask credentials
    try:
        creds = json.loads(crypto.decrypt(connection.encrypted_credentials))
        masked = mask_credentials(creds)
    except Exception:
        masked = {"error": "Could not decrypt credentials"}

    return APIResponse(
        success=True,
        message="Connection retrieved",
        data=ConnectionDetailResponse(
            id=connection.id,
            name=connection.name,
            provider=connection.provider,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
            masked_credentials=masked
        )
    )


@router.put(
    "/{connection_id}",
    response_model=APIResponse[ConnectionResponse],
    summary="Update connection",
    description="Update connection name or credentials"
)
async def update_connection(
        connection_id: UUID,
        conn_in: ConnectionUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Updates a connection."""
    connection = await get_connection_or_404(connection_id, current_user, db)

    # Update name
    if conn_in.name:
        connection.name = conn_in.name.strip()

    # Update credentials
    if conn_in.credentials:
        is_valid, error = validate_credentials(connection.provider, conn_in.credentials)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        connection.encrypted_credentials = crypto.encrypt(json.dumps(conn_in.credentials))

    connection.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(connection)

    logger.info(
        f"Connection updated: {connection_id}",
        extra={"user_id": str(current_user.id)}
    )

    return APIResponse(
        success=True,
        message="Connection updated",
        data=ConnectionResponse(
            id=connection.id,
            name=connection.name,
            provider=connection.provider,
            created_at=connection.created_at,
            updated_at=connection.updated_at
        )
    )


@router.delete(
    "/{connection_id}",
    response_model=APIResponse,
    summary="Delete connection",
    description="Delete a connection"
)
async def delete_connection(
        connection_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Deletes a connection."""
    connection = await get_connection_or_404(connection_id, current_user, db)

    await db.delete(connection)
    await db.commit()

    logger.info(
        f"Connection deleted: {connection_id}",
        extra={"user_id": str(current_user.id), "provider": connection.provider}
    )

    return APIResponse(
        success=True,
        message="Connection deleted"
    )


# ============================================================
# PROVIDER INFO
# ============================================================

@router.get(
    "/providers/list",
    response_model=APIResponse[List[dict]],
    summary="List providers",
    description="Get list of supported providers"
)
async def list_providers(
        current_user: User = Depends(get_current_user)
):
    """Lists supported providers."""
    providers = [
        {
            "id": provider_id,
            "name": config["display_name"],
            "required_fields": config["required_fields"],
            "optional_fields": config["optional_fields"],
            "oauth_supported": config["oauth_supported"]
        }
        for provider_id, config in PROVIDER_CONFIG.items()
    ]

    return APIResponse(
        success=True,
        message=f"Found {len(providers)} providers",
        data=providers
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@router.post(
    "/{connection_id}/test",
    response_model=APIResponse,
    summary="Test connection",
    description="Test if connection credentials are valid"
)
async def test_connection(
        connection_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Tests connection health."""
    connection = await get_connection_or_404(connection_id, current_user, db)

    try:
        creds = json.loads(crypto.decrypt(connection.encrypted_credentials))
    except Exception:
        return APIResponse(
            success=False,
            message="Could not decrypt credentials"
        )

    # Provider-specific tests
    provider = connection.provider

    try:
        if provider == "OPENAI":
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {creds.get('api_key')}"},
                    timeout=10.0
                )
                is_valid = response.status_code == 200

        elif provider == "ANTHROPIC":
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": creds.get("api_key"),
                        "anthropic-version": "2023-06-01"
                    },
                    timeout=10.0
                )
                # 400 is expected without proper request body
                is_valid = response.status_code in [200, 400]

        elif provider == "SUPABASE":
            import httpx
            async with httpx.AsyncClient() as client:
                url = creds.get("project_url", "").rstrip("/")
                response = await client.get(
                    f"{url}/rest/v1/",
                    headers={"apikey": creds.get("service_role_key")},
                    timeout=10.0
                )
                is_valid = response.status_code in [200, 404]

        else:
            # Generic - just verify we have credentials
            is_valid = bool(creds)

        return APIResponse(
            success=is_valid,
            message="Connection is valid" if is_valid else "Connection test failed",
            data={"is_valid": is_valid}
        )

    except Exception as e:
        logger.warning(f"Connection test failed: {e}")
        return APIResponse(
            success=False,
            message=f"Connection test failed: {str(e)}",
            data={"is_valid": False, "error": str(e)}
        )


# ============================================================
# OAUTH FLOWS
# ============================================================

@router.get(
    "/google/auth-url",
    response_model=APIResponse[str],
    summary="Get Google OAuth URL",
    description="Get URL to start Google OAuth flow"
)
async def get_google_auth_url(
        scopes: Optional[str] = Query(
            None,
            description="Comma-separated scopes to request"
        ),
        current_user: User = Depends(get_current_user)
):
    """Gets Google OAuth authorization URL."""
    try:
        from src.services.workflow.google_oauth import google_auth

        # Parse scopes
        scope_list = None
        if scopes:
            scope_list = [s.strip() for s in scopes.split(",")]

        url = google_auth.get_authorization_url(scopes=scope_list)

        return APIResponse(
            success=True,
            message="OAuth URL generated",
            data=url
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate OAuth URL: {str(e)}"
        )


@router.get(
    "/google/callback",
    response_model=APIResponse[ConnectionResponse],
    summary="Google OAuth callback",
    description="Handle Google OAuth callback and create connection"
)
async def google_oauth_callback(
        code: str,
        state: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Handles Google OAuth callback."""
    try:
        from src.services.workflow.google_oauth import google_auth

        # Exchange code for tokens
        token_data = google_auth.exchange_code_for_token(code)

        # Create connection
        encrypted = crypto.encrypt(json.dumps(token_data))

        now = datetime.now(timezone.utc)
        new_conn = Connection(
            name="Google Workspace (OAuth)",
            provider="GMAIL_OAUTH",
            user_id=current_user.id,
            encrypted_credentials=encrypted,
            created_at=now,
            updated_at=now
        )

        db.add(new_conn)
        await db.commit()
        await db.refresh(new_conn)

        logger.info(
            f"Google OAuth connection created: {new_conn.id}",
            extra={"user_id": str(current_user.id)}
        )

        return APIResponse(
            success=True,
            message="Google account connected successfully",
            data=ConnectionResponse(
                id=new_conn.id,
                name=new_conn.name,
                provider=new_conn.provider,
                created_at=new_conn.created_at,
                updated_at=new_conn.updated_at
            )
        )

    except Exception as e:
        logger.error(f"Google OAuth failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth failed: {str(e)}"
        )


@router.post(
    "/{connection_id}/refresh-token",
    response_model=APIResponse,
    summary="Refresh OAuth token",
    description="Refresh OAuth token for a connection"
)
async def refresh_oauth_token(
        connection_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Refreshes OAuth token."""
    connection = await get_connection_or_404(connection_id, current_user, db)

    if connection.provider not in ["GMAIL_OAUTH", "GOOGLE"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token refresh only supported for OAuth connections"
        )

    try:
        creds = json.loads(crypto.decrypt(connection.encrypted_credentials))

        if "refresh_token" not in creds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No refresh token available"
            )

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        credentials = Credentials(
            token=creds.get("token"),
            refresh_token=creds.get("refresh_token"),
            token_uri=creds.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds.get("client_id") or settings.GOOGLE_CLIENT_ID,
            client_secret=creds.get("client_secret") or settings.GOOGLE_CLIENT_SECRET.get_secret_value()
        )

        credentials.refresh(Request())

        # Update stored credentials
        creds["token"] = credentials.token
        connection.encrypted_credentials = crypto.encrypt(json.dumps(creds))
        connection.updated_at = datetime.now(timezone.utc)

        await db.commit()

        return APIResponse(
            success=True,
            message="Token refreshed successfully"
        )

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token refresh failed: {str(e)}"
        )