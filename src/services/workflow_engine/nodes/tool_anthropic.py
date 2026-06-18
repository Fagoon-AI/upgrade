"""
Anthropic/Claude Node.

Provides access to Anthropic's Claude models with:
- Full model support (Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku)
- Extended thinking for complex reasoning
- Vision support for image analysis
- Token usage tracking for billing
- System prompts for behavior control

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
class ClaudeModelConfig:
    """Configuration for a Claude model."""
    name: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool = True
    supports_extended_thinking: bool = False


CLAUDE_MODELS: Dict[str, ClaudeModelConfig] = {
    "claude-sonnet-4-20250514": ClaudeModelConfig(
        name="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4 (Latest)",
        context_window=200_000,
        max_output_tokens=16_000,
        supports_extended_thinking=True,
    ),
    "claude-3-5-sonnet-20241022": ClaudeModelConfig(
        name="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet (Recommended)",
        context_window=200_000,
        max_output_tokens=8_192,
    ),
    "claude-3-5-haiku-20241022": ClaudeModelConfig(
        name="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku (Fast)",
        context_window=200_000,
        max_output_tokens=8_192,
    ),
    "claude-3-opus-20240229": ClaudeModelConfig(
        name="claude-3-opus-20240229",
        display_name="Claude 3 Opus (Most Capable)",
        context_window=200_000,
        max_output_tokens=4_096,
    ),
    "claude-3-sonnet-20240229": ClaudeModelConfig(
        name="claude-3-sonnet-20240229",
        display_name="Claude 3 Sonnet",
        context_window=200_000,
        max_output_tokens=4_096,
    ),
    "claude-3-haiku-20240307": ClaudeModelConfig(
        name="claude-3-haiku-20240307",
        display_name="Claude 3 Haiku (Budget)",
        context_window=200_000,
        max_output_tokens=4_096,
    ),
}

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


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
    "overloaded",
    "timeout",
    "connection",
    "server_error",
    "529",
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
class ClaudeUsage:
    """Token usage from Claude API response."""
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
# ANTHROPIC NODE IMPLEMENTATION
# ============================================================

class AnthropicNode(BaseNode):
    """
    Anthropic/Claude Node.

    Features:
    - All Claude models including Claude 3.5 Sonnet, Opus, Haiku
    - Extended thinking for complex reasoning tasks
    - Vision support for image analysis
    - System prompts for behavior control
    - Token usage and cost tracking
    - Retry logic with exponential backoff
    """

    node_type = "anthropicNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        model_options = [
            {"value": m.name, "label": m.display_name}
            for m in CLAUDE_MODELS.values()
        ]

        return {
            "type": cls.node_type,
            "display_name": "Anthropic / Claude",
            "icon": "Brain",
            "category": "AI & Data",
            "description": "Generate text with Anthropic's Claude models - known for nuanced, thoughtful responses.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Anthropic Connection",
                    "type": "connection_select",
                    "required": True,
                    "provider": "ANTHROPIC",
                    "helper": "Select your Anthropic API key connection"
                },
                {
                    "name": "model",
                    "label": "Model",
                    "type": "select",
                    "options": [m["value"] for m in model_options],
                    "default": DEFAULT_MODEL,
                    "helper": "Claude 3.5 Sonnet is recommended for most tasks"
                },
                {
                    "name": "prompt",
                    "label": "User Message",
                    "type": "textarea",
                    "placeholder": "Enter your prompt or use {{variables}}...",
                    "required": True,
                    "helper": "The main prompt/question for Claude"
                },
                {
                    "name": "system_prompt",
                    "label": "System Prompt",
                    "type": "textarea",
                    "placeholder": "You are a helpful assistant specialized in...",
                    "helper": "Define Claude's behavior, role, and response style"
                },
                {
                    "name": "temperature",
                    "label": "Temperature",
                    "type": "slider",
                    "min": 0,
                    "max": 1,
                    "step": 0.1,
                    "default": 0.7,
                    "helper": "0 = focused/deterministic, 1 = creative/varied"
                },
                {
                    "name": "max_tokens",
                    "label": "Max Output Tokens",
                    "type": "number",
                    "default": 4096,
                    "helper": "Maximum length of the response"
                },
                {
                    "name": "extended_thinking",
                    "label": "Extended Thinking",
                    "type": "boolean",
                    "default": False,
                    "helper": "Enable for complex reasoning (Claude Sonnet 4 only)"
                }
            ],
            "outputs": ["content", "model", "stop_reason", "status", "usage"],
            "outputs_schema": {
                "content": {"type": "string", "description": "Generated text response"},
                "model": {"type": "string", "description": "Model used for generation"},
                "stop_reason": {"type": "string", "description": "Why generation stopped"},
                "status": {"type": "string", "description": "Execution status"},
                "usage": {"type": "object", "description": "Token usage and cost"}
            },
            "version": "1.0.0",
            "tags": ["ai", "llm", "claude", "anthropic"]
        }

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            node_id: str = None
    ) -> Dict[str, Any]:
        """
        Executes Claude completion with retry logic and usage tracking.
        """
        # 1. Get Configuration
        connection_id = input_data.get("connection_id")
        prompt = input_data.get("prompt", "")
        model_name = input_data.get("model", DEFAULT_MODEL)
        system_prompt = input_data.get("system_prompt")
        temperature = float(input_data.get("temperature", 0.7))
        max_tokens = int(input_data.get("max_tokens", 4096))
        extended_thinking = input_data.get("extended_thinking", False)

        # Validate required inputs
        if not connection_id:
            raise NodeExecutionError(
                message="Anthropic Node requires a 'connection_id'",
                node_type=self.node_type,
                retryable=False
            )

        if not prompt:
            raise NodeExecutionError(
                message="Anthropic Node requires a 'prompt'",
                node_type=self.node_type,
                retryable=False
            )

        # Get model config
        model_config = CLAUDE_MODELS.get(model_name)
        if not model_config:
            model_config = CLAUDE_MODELS[DEFAULT_MODEL]
            model_name = DEFAULT_MODEL

        # Validate extended thinking compatibility
        if extended_thinking and not model_config.supports_extended_thinking:
            logger.warning(f"Model {model_name} doesn't support extended thinking, disabling")
            extended_thinking = False

        # Clamp max_tokens to model limit
        effective_max_tokens = min(max_tokens, model_config.max_output_tokens)

        # 2. Fetch API key
        api_key = await self._get_api_key(db, connection_id)

        # 3. Execute with retry
        result, usage = await self._execute_with_retry(
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=effective_max_tokens,
            extended_thinking=extended_thinking
        )

        # 4. Calculate cost
        cost = CostCalculator.calculate(
            provider="anthropic",
            model=self._get_cost_model_name(model_name),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens
        )
        usage.cost_usd = str(cost)

        return {
            "status": "success",
            "content": result["content"],
            "model": model_name,
            "stop_reason": result.get("stop_reason", "end_turn"),
            "usage": usage.to_dict()
        }

    def _get_cost_model_name(self, model_name: str) -> str:
        """Maps model name to cost tracking name."""
        if "sonnet" in model_name.lower():
            return "claude-3-5-sonnet"
        elif "opus" in model_name.lower():
            return "claude-3-opus"
        elif "haiku" in model_name.lower():
            return "claude-3-haiku"
        return "claude-3-5-sonnet"

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
                provider="anthropic"
            )

        try:
            decrypted_json = crypto.decrypt(connection.encrypted_credentials)
            creds = json.loads(decrypted_json)
            api_key = creds.get("api_key")
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt connection credentials",
                node_type=self.node_type,
                provider="anthropic"
            )

        if not api_key:
            raise ConnectionError(
                message="Connection missing API key",
                node_type=self.node_type,
                provider="anthropic"
            )

        return api_key

    async def _execute_with_retry(
            self,
            api_key: str,
            model_name: str,
            prompt: str,
            system_prompt: Optional[str],
            temperature: float,
            max_tokens: int,
            extended_thinking: bool
    ) -> Tuple[Dict[str, Any], ClaudeUsage]:
        """Executes API call with retry logic."""
        retry_config = RetryConfig()
        last_error = None

        for attempt in range(1, retry_config.max_retries + 1):
            try:
                result, usage = await self._call_anthropic(
                    api_key=api_key,
                    model_name=model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extended_thinking=extended_thinking
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
                        f"Anthropic API error (attempt {attempt}): {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)

        raise NodeExecutionError(
            message=f"Anthropic API failed after {retry_config.max_retries} attempts: {last_error}",
            node_type=self.node_type,
            retryable=False
        )

    async def _call_anthropic(
            self,
            api_key: str,
            model_name: str,
            prompt: str,
            system_prompt: Optional[str],
            temperature: float,
            max_tokens: int,
            extended_thinking: bool
    ) -> Tuple[Dict[str, Any], ClaudeUsage]:
        """Makes the actual API call to Anthropic."""
        try:
            import anthropic
        except ImportError:
            raise NodeExecutionError(
                message="anthropic package not installed. Run: pip install anthropic",
                node_type=self.node_type,
                retryable=False
            )

        client = anthropic.AsyncAnthropic(api_key=api_key)

        # Build messages
        messages = [{"role": "user", "content": prompt}]

        # Build request kwargs
        request_kwargs = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        # Add system prompt if provided
        if system_prompt:
            request_kwargs["system"] = system_prompt

        # Temperature (not used with extended thinking)
        if not extended_thinking:
            request_kwargs["temperature"] = temperature

        # Extended thinking (beta feature)
        if extended_thinking:
            request_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": min(max_tokens * 2, 10000)
            }

        # Make API call
        response = await client.messages.create(**request_kwargs)

        # Extract content
        content = ""
        if response.content:
            for block in response.content:
                if hasattr(block, 'text'):
                    content += block.text

        # Extract usage
        usage = ClaudeUsage()
        if response.usage:
            usage.input_tokens = response.usage.input_tokens or 0
            usage.output_tokens = response.usage.output_tokens or 0
            usage.total_tokens = usage.input_tokens + usage.output_tokens

        logger.debug(
            f"Claude usage: {usage.input_tokens} in, {usage.output_tokens} out"
        )

        return {
            "content": content,
            "stop_reason": response.stop_reason or "end_turn"
        }, usage

    def _should_retry(self, error_str: str) -> bool:
        """Determines if an error should trigger a retry."""
        return any(err in error_str for err in RETRY_ERRORS)
