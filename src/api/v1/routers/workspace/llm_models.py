import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.core.globals import get_postgres_services
from src.models.auth_models.user_model import UserInDB
from src.schemas.llm import (
    LLMModelConfigCreate,
    LLMModelConfigResponse,
    LLMModelConfigUpdate,
)
from src.services.nosql.postgres_services import PostgresServices
from src.utils.upgrade_auth.app_error import AppError

router = APIRouter()

SUPPORTED_PROVIDERS = ["openai", "hugging_face", "groq", "anthropic", "localhost"]
SUPPORTED_FEATURES = ["chat", "agents", "workflow"]


def _get_authenticated_user(request: Request) -> UserInDB:
    if not getattr(request.state, "user", None):
        raise AppError(
            "Unauthorized: user must be authenticated.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return request.state.user


def _mask_api_key(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return "*" * (len(api_key) - 4) + api_key[-4:]


def _to_response(model_config: "LLMModelConfig") -> LLMModelConfigResponse:
    return LLMModelConfigResponse(
        id=str(model_config.id),
        name=model_config.name,
        provider=model_config.provider,
        model_id=model_config.model_id,
        masked_api_key=_mask_api_key(model_config.api_key),
        features=model_config.features or [],
        agent_ids=model_config.agent_ids or [],
        workflow_ids=model_config.workflow_ids or [],
        is_enabled=not model_config.is_deleted,
        created_at=model_config.created_at,
        updated_at=model_config.updated_at,
    )


@router.get("/providers", status_code=status.HTTP_200_OK)
async def list_supported_providers() -> dict:
    return {
        "providers": SUPPORTED_PROVIDERS,
        "features": SUPPORTED_FEATURES,
    }


@router.post("", response_model=LLMModelConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_model_config(
    input_data: LLMModelConfigCreate,
    request: Request,
    postgres_services: PostgresServices = Depends(get_postgres_services),
):
    current_user = _get_authenticated_user(request)

    if input_data.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{input_data.provider}'. Supported providers: {SUPPORTED_PROVIDERS}",
        )

    if any(feature not in SUPPORTED_FEATURES for feature in input_data.features or []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supported features are {SUPPORTED_FEATURES}.",
        )

    model_config = await postgres_services.create_llm_model_config(
        {
            "user_id": uuid.UUID(str(current_user.id)),
            "name": input_data.name,
            "provider": input_data.provider,
            "model_id": input_data.model_id,
            "api_key": input_data.api_key,
            "features": input_data.features or [],
            "agent_ids": input_data.agent_ids or [],
            "workflow_ids": input_data.workflow_ids or [],
            "is_deleted": False,
        }
    )

    return _to_response(model_config)


@router.get("", response_model=List[LLMModelConfigResponse], status_code=status.HTTP_200_OK)
async def list_llm_model_configs(
    request: Request,
    postgres_services: PostgresServices = Depends(get_postgres_services),
):
    current_user = _get_authenticated_user(request)
    model_configs = await postgres_services.get_llm_model_configs_by_user_id(uuid.UUID(str(current_user.id)))
    return [_to_response(config) for config in model_configs]


@router.get("/{model_id}", response_model=LLMModelConfigResponse, status_code=status.HTTP_200_OK)
async def get_llm_model_config(
    model_id: str,
    request: Request,
    postgres_services: PostgresServices = Depends(get_postgres_services),
):
    current_user = _get_authenticated_user(request)
    model_config = await postgres_services.get_llm_model_config_by_id(
        uuid.UUID(model_id), uuid.UUID(str(current_user.id))
    )
    if not model_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM model configuration not found.")
    return _to_response(model_config)


@router.patch("/{model_id}", response_model=LLMModelConfigResponse, status_code=status.HTTP_200_OK)
async def update_llm_model_config(
    model_id: str,
    input_data: LLMModelConfigUpdate,
    request: Request,
    postgres_services: PostgresServices = Depends(get_postgres_services),
):
    current_user = _get_authenticated_user(request)

    if input_data.provider and input_data.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{input_data.provider}'. Supported providers: {SUPPORTED_PROVIDERS}",
        )

    if input_data.features and any(feature not in SUPPORTED_FEATURES for feature in input_data.features):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supported features are {SUPPORTED_FEATURES}.",
        )

    update_data = input_data.model_dump(exclude_unset=True)
    model_config = await postgres_services.update_llm_model_config(
        uuid.UUID(model_id), uuid.UUID(str(current_user.id)), update_data
    )
    if not model_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM model configuration not found.")
    return _to_response(model_config)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_model_config(
    model_id: str,
    request: Request,
    postgres_services: PostgresServices = Depends(get_postgres_services),
):
    current_user = _get_authenticated_user(request)
    deleted = await postgres_services.soft_delete_llm_model_config(
        uuid.UUID(model_id), uuid.UUID(str(current_user.id))
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM model configuration not found.")
    return
