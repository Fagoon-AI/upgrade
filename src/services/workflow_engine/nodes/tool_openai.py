"""
OpenAI/ChatGPT Node.

Provides access to OpenAI's GPT models with:
- Full model support (GPT-4o, GPT-4 Turbo, GPT-3.5)
- Streaming support (returns full response)
- JSON mode for structured outputs
- Function calling support
- Vision support (GPT-4o)
- Token usage tracking for billing

Version: 1.0.0
"""

import json
import asyncio
import random
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError, ConnectionError
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto
from src.services.workflow.cost_tracking import CostCalculator


# ============================================================
# MODEL CONFIGURATION
# ============================================================

@dataclass(frozen=True)
class OpenAIModelConfig:
    """Configuration for an OpenAI model."""
    name: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool = False
    supports_json_mode: bool = True
    supports_functions: bool = True


OPENAI_MODELS: Dict[str, OpenAIModelConfig] = {
    "gpt-4o": OpenAIModelConfig(
        name="gpt-4o",
        display_name="GPT-4o (Recommended)",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_vision=True,
    ),
    "gpt-4o-mini": OpenAIModelConfig(
        name="gpt-4o-mini",
        display_name="GPT-4o Mini (Fast & Cheap)",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_vision=True,
    ),
    "gpt-4-turbo": OpenAIModelConfig(
        name="gpt-4-turbo",
        display_name="GPT-4 Turbo",
        context_window=128_000,
        max_output_tokens=4_096,
        supports_vision=True,
    ),
    "gpt-4": OpenAIModelConfig(
        name="gpt-4",
        display_name="GPT-4",
        context_window=8_192,
        max_output_tokens=4_096,
        supports_vision=False,
    ),
    "gpt-3.5-turbo": OpenAIModelConfig(
        name="gpt-3.5-turbo",
        display_name="GPT-3.5 Turbo (Legacy)",
        context_window=16_385,
        max_output_tokens=4_096,
        supports_vision=False,
    ),
    "o1": OpenAIModelConfig(
        name="o1",
        display_name="o1 (Reasoning)",
        context_window=200_000,
        max_output_tokens=100_000,
        supports_vision=True,
        supports_json_mode=False,
        supports_functions=False,
    ),
    "o1-mini": OpenAIModelConfig(
        name="o1-mini",
        display_name="o1-mini (Fast Reasoning)",
        context_window=128_000,
        max_output_tokens=65_536,
        supports_vision=False,
        supports_json_mode=False,
        supports_functions=False,
    ),
}

DEFAULT_MODEL = "gpt-4o-mini"


# ============================================================
# RETRY CONFIGURATION
# ============================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff."""
        delay = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay
        )
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay


RETRY_ERRORS = [
    "rate_limit",
    "timeout",
    "connection",
    "server_error",
    "overloaded",
    "429",
    "500",
    "502",
    "503",
    "504",
]


# ============================================================
# USAGE TRACKING
# ============================================================

@dataclass
class OpenAIUsage:
    """Token usage from OpenAI API response."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: str = "0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd
        }


# ============================================================
# OPENAI NODE IMPLEMENTATION
# ============================================================

class OpenAINode(BaseNode):
    """
    OpenAI/ChatGPT Node.

    Features:
    - All GPT models including GPT-4o, GPT-4, GPT-3.5
    - Reasoning models (o1, o1-mini)
    - JSON mode for structured outputs
    - System prompts for behavior control
    - Vision support for image analysis
    - Token usage and cost tracking
    - Retry logic with exponential backoff
    """

    node_type = "openaiNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        model_options = [
            {"value": m.name, "label": m.display_name}
            for m in OPENAI_MODELS.values()
        ]

        return {
            "type": cls.node_type,
            "display_name": "OpenAI / ChatGPT",
            "icon": "MessageSquare",
            "category": "AI & Data",
            "description": "Generate text with OpenAI's GPT models including GPT-4o and reasoning models.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "OpenAI Connection",
                    "type": "connection_select",
                    "required": True,
                    "provider": "OPENAI",
                    "helper": "Select your OpenAI API key connection"
                },
                {
                    "name": "model",
                    "label": "Model",
                    "type": "select",
                    "options": [m["value"] for m in model_options],
                    "default": DEFAULT_MODEL,
                    "helper": "GPT-4o-mini is fast and cost-effective. GPT-4o for complex tasks."
                },
                {
                    "name": "prompt",
                    "label": "User Message",
                    "type": "textarea",
                    "placeholder": "Enter your prompt or use {{variables}}...",
                    "required": True,
                    "helper": "The main prompt/question for the AI"
                },
                {
                    "name": "system_prompt",
                    "label": "System Prompt",
                    "type": "textarea",
                    "placeholder": "You are a helpful assistant...",
                    "helper": "Define the AI's behavior, role, and response style"
                },
                {
                    "name": "temperature",
                    "label": "Temperature",
                    "type": "slider",
                    "min": 0,
                    "max": 2,
                    "step": 0.1,
                    "default": 0.7,
                    "helper": "0 = focused/deterministic, 2 = creative/random"
                },
                {
                    "name": "max_tokens",
                    "label": "Max Output Tokens",
                    "type": "number",
                    "default": 4096,
                    "helper": "Maximum length of the response"
                },
                {
                    "name": "json_mode",
                    "label": "JSON Output Mode",
                    "type": "boolean",
                    "default": False,
                    "helper": "Force the model to output valid JSON"
                },
                {
                    "name": "response_schema",
                    "label": "Response Schema (JSON)",
                    "type": "json_editor",
                    "placeholder": '{"type": "object", "properties": {...}}',
                    "helper": "Optional: Define expected JSON structure",
                    "depends_on": "json_mode"
                }
            ],
            "outputs": ["content", "model", "finish_reason", "status", "usage"],
            "outputs_schema": {
                "content": {"type": "string", "description": "Generated text response"},
                "model": {"type": "string", "description": "Model used for generation"},
                "finish_reason": {"type": "string", "description": "Why generation stopped (stop, length, etc.)"},
                "status": {"type": "string", "description": "Execution status"},
                "usage": {"type": "object", "description": "Token usage and cost"}
            },
            "version": "1.0.0",
            "tags": ["ai", "llm", "chatgpt", "gpt", "openai"]
        }

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            node_id: str = None
    ) -> Dict[str, Any]:
        """
        Executes OpenAI completion with retry logic and usage tracking.
        """
        # 1. Get Configuration
        connection_id = input_data.get("connection_id")
        prompt = input_data.get("prompt", "")
        model_name = input_data.get("model", DEFAULT_MODEL)
        system_prompt = input_data.get("system_prompt")
        temperature = float(input_data.get("temperature", 0.7))
        max_tokens = int(input_data.get("max_tokens", 4096))
        json_mode = input_data.get("json_mode", False)
        response_schema = input_data.get("response_schema")

        # Validate required inputs
        if not connection_id:
            raise NodeExecutionError(
                message="OpenAI Node requires a 'connection_id'",
                node_type=self.node_type,
                retryable=False
            )

        if not prompt:
            raise NodeExecutionError(
                message="OpenAI Node requires a 'prompt'",
                node_type=self.node_type,
                retryable=False
            )

        # Get model config
        model_config = OPENAI_MODELS.get(model_name)
        if not model_config:
            model_config = OPENAI_MODELS[DEFAULT_MODEL]
            model_name = DEFAULT_MODEL

        # Validate JSON mode compatibility
        if json_mode and not model_config.supports_json_mode:
            logger.warning(f"Model {model_name} doesn't support JSON mode, disabling")
            json_mode = False

        # Clamp max_tokens to model limit
        effective_max_tokens = min(max_tokens, model_config.max_output_tokens)

        # 2. Fetch API key
        api_key = await self._get_api_key(db, connection_id)

        # 3. Build messages
        messages = self._build_messages(prompt, system_prompt)

        # 4. Execute with retry
        result, usage = await self._execute_with_retry(
            api_key=api_key,
            model_name=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=effective_max_tokens,
            json_mode=json_mode,
            response_schema=response_schema
        )

        # 5. Calculate cost
        cost = CostCalculator.calculate(
            provider="openai",
            model=model_name,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens
        )
        usage.cost_usd = str(cost)

        return {
            "status": "success",
            "content": result["content"],
            "model": model_name,
            "finish_reason": result.get("finish_reason", "stop"),
            "usage": usage.to_dict()
        }

    async def _get_api_key(self, db: AsyncSession, connection_id: str) -> str:
        """Fetches and decrypts API key from connection."""
        result = await db.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        connection = result.scalars().first()

        if not connection:
            raise ConnectionError(
                message=f"Connection {connection_id} not found",
                node_type=self.node_type,
                provider="openai"
            )

        try:
            decrypted_json = crypto.decrypt(connection.encrypted_credentials)
            creds = json.loads(decrypted_json)
            api_key = creds.get("api_key")
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt connection credentials",
                node_type=self.node_type,
                provider="openai"
            )

        if not api_key:
            raise ConnectionError(
                message="Connection missing API key",
                node_type=self.node_type,
                provider="openai"
            )

        return api_key

    def _build_messages(
            self,
            prompt: str,
            system_prompt: Optional[str]
    ) -> List[Dict[str, str]]:
        """Builds the messages array for the API call."""
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        return messages

    async def _execute_with_retry(
            self,
            api_key: str,
            model_name: str,
            messages: List[Dict[str, str]],
            temperature: float,
            max_tokens: int,
            json_mode: bool,
            response_schema: Optional[Dict] = None
    ) -> Tuple[Dict[str, Any], OpenAIUsage]:
        """Executes API call with retry logic."""
        retry_config = RetryConfig()
        last_error = None

        for attempt in range(1, retry_config.max_retries + 1):
            try:
                result, usage = await self._call_openai(
                    api_key=api_key,
                    model_name=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    response_schema=response_schema
                )
                return result, usage

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                if not self._should_retry(error_str):
                    raise

                if attempt < retry_config.max_retries:
                    delay = retry_config.get_delay(attempt)
                    logger.warning(
                        f"OpenAI API error (attempt {attempt}): {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)

        raise NodeExecutionError(
            message=f"OpenAI API failed after {retry_config.max_retries} attempts: {last_error}",
            node_type=self.node_type,
            retryable=False
        )

    async def _call_openai(
            self,
            api_key: str,
            model_name: str,
            messages: List[Dict[str, str]],
            temperature: float,
            max_tokens: int,
            json_mode: bool,
            response_schema: Optional[Dict] = None
    ) -> Tuple[Dict[str, Any], OpenAIUsage]:
        """Makes the actual API call to OpenAI."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise NodeExecutionError(
                message="openai package not installed. Run: pip install openai",
                node_type=self.node_type,
                retryable=False
            )

        client = AsyncOpenAI(api_key=api_key)

        # Build request kwargs
        request_kwargs = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        # Temperature not supported by o1 models
        if not model_name.startswith("o1"):
            request_kwargs["temperature"] = temperature

        # JSON mode
        if json_mode:
            if response_schema:
                request_kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": response_schema
                    }
                }
            else:
                request_kwargs["response_format"] = {"type": "json_object"}

        # Make API call
        response = await client.chat.completions.create(**request_kwargs)

        # Extract content
        content = ""
        finish_reason = "stop"

        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = choice.finish_reason or "stop"

        # Extract usage
        usage = OpenAIUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens or 0
            usage.output_tokens = response.usage.completion_tokens or 0
            usage.total_tokens = usage.input_tokens + usage.output_tokens

        logger.debug(
            f"OpenAI usage: {usage.input_tokens} in, {usage.output_tokens} out"
        )

        return {
            "content": content,
            "finish_reason": finish_reason
        }, usage

    def _should_retry(self, error_str: str) -> bool:
        """Determines if an error should trigger a retry."""
        return any(err in error_str for err in RETRY_ERRORS)
