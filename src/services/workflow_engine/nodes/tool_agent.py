import json
import asyncio
import uuid
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError, ConnectionError, ensure_string
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto
from src.services.workflow.cost_tracking import CostCalculator


# ============================================================
# TOKEN COUNTING & CONTEXT MANAGEMENT
# ============================================================

@dataclass(frozen=True)
class ModelConfig:
    """Configuration for different Gemini models."""
    name: str
    context_window: int
    output_limit: int
    input_limit: int
    chars_per_token: float = 4.0


MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "gemini-2.0-flash": ModelConfig(
        name="gemini-2.0-flash",
        context_window=1_000_000,
        output_limit=8_192,
        input_limit=900_000
    ),
    "gemini-2.0-flash-lite": ModelConfig(
        name="gemini-2.0-flash-lite",
        context_window=1_000_000,
        output_limit=8_192,
        input_limit=900_000
    ),
    "gemini-2.5-pro": ModelConfig(
        name="gemini-2.5-pro",
        context_window=1_000_000,
        output_limit=65_536,
        input_limit=850_000
    ),
    "gemini-2.5-flash": ModelConfig(
        name="gemini-2.5-flash",
        context_window=1_000_000,
        output_limit=65_536,
        input_limit=850_000
    ),
    "gemini-exp-1206": ModelConfig(
        name="gemini-exp-1206",
        context_window=2_000_000,
        output_limit=8_192,
        input_limit=1_900_000
    ),
    "default": ModelConfig(
        name="default",
        context_window=128_000,
        output_limit=8_192,
        input_limit=100_000
    )
}


class TokenCounter:
    """Estimates token counts for Gemini models."""

    def __init__(self, model_config: ModelConfig):
        self.config = model_config

    def estimate_tokens(self, text: str) -> int:
        """Estimates token count from text."""
        if not text:
            return 0
        return int(len(text) / self.config.chars_per_token)

    def will_fit(self, text: str, available_tokens: int) -> bool:
        """Checks if text will fit in available tokens."""
        return self.estimate_tokens(text) <= available_tokens


class ContextManager:
    """Manages context window for conversations."""

    def __init__(self, model_config: ModelConfig):
        self.config = model_config
        self.counter = TokenCounter(model_config)

    def prepare_context(
            self,
            system: str,
            prompt: str,
            history: str = ""
    ) -> Tuple[str, str, str, Dict[str, Any]]:
        """Prepares context with token management."""
        system_tokens = self.counter.estimate_tokens(system)
        prompt_tokens = self.counter.estimate_tokens(prompt)

        available_for_history = (
                self.config.input_limit - system_tokens - prompt_tokens - 1000
        )

        truncated_history = history
        history_truncated = False

        if history and available_for_history > 0:
            history_tokens = self.counter.estimate_tokens(history)
            if history_tokens > available_for_history:
                chars_allowed = int(available_for_history * self.config.chars_per_token)
                truncated_history = history[-chars_allowed:]
                if "\n" in truncated_history:
                    truncated_history = truncated_history[truncated_history.index("\n")+1:]
                history_truncated = True
        elif available_for_history <= 0:
            truncated_history = ""
            history_truncated = bool(history)

        final_history_tokens = self.counter.estimate_tokens(truncated_history)

        metadata = {
            "system_tokens": system_tokens,
            "prompt_tokens": prompt_tokens,
            "history_tokens": final_history_tokens,
            "total_tokens": system_tokens + prompt_tokens + final_history_tokens,
            "history_truncated": history_truncated,
            "model_limit": self.config.input_limit
        }

        return system, prompt, truncated_history, metadata


# ============================================================
# USAGE TRACKING
# ============================================================

@dataclass
class AgentUsage:
    """Token usage tracking for agent node."""
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
# AGENT NODE
# ============================================================

class AgentNode(BaseNode):
    """
    AI Agent Node with Cost Tracking.

    Features:
    - Token-aware context management
    - Automatic history truncation
    - Tool calling support
    - Usage tracking for billing
    """

    node_type = "agentNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "AI Agent",
            "icon": "Bot",
            "category": "AI & Data",
            "description": "Advanced reasoning agent with context management and cost tracking.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Google AI Connection",
                    "type": "connection_select",
                    "required": True,
                    "provider": "GOOGLE"
                },
                {
                    "name": "model",
                    "label": "Model",
                    "type": "select",
                    "options": list(MODEL_CONFIGS.keys())[:-1],  # Exclude 'default'
                    "default": "gemini-2.5-flash"
                },
                {
                    "name": "system_instruction",
                    "label": "System Instruction",
                    "type": "textarea",
                    "default": "You are a professional assistant.",
                    "helper": "Define the agent's behavior and role"
                },
                {
                    "name": "user_content",
                    "label": "User Input",
                    "type": "textarea",
                    "placeholder": "Enter your prompt or use {{variables}}...",
                    "required": True
                },
                {
                    "name": "history_text",
                    "label": "Conversation History",
                    "type": "textarea",
                    "helper": "Previous conversation context (auto-truncated if too long)"
                },
                {
                    "name": "temperature",
                    "label": "Creativity (Temp)",
                    "type": "slider",
                    "min": 0,
                    "max": 1,
                    "step": 0.1,
                    "default": 0.3
                },
                {
                    "name": "max_output_tokens",
                    "label": "Max Output Tokens",
                    "type": "number",
                    "default": 4096,
                    "helper": "Maximum tokens in response"
                }
            ],
            "outputs": ["content", "tool_calls", "usage", "status"],
            "outputs_schema": {
                "content": {"type": "string", "description": "Generated response"},
                "tool_calls": {"type": "array", "description": "Tool calls if any"},
                "usage": {"type": "object", "description": "Token usage and cost"},
                "status": {"type": "string", "description": "Execution status"}
            }
        }

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            node_id: str = None
    ) -> Dict[str, Any]:
        """Executes reasoning with token-aware context management and cost tracking."""
        # 1. Configuration Resolution
        model_name = input_data.get("model", "gemini-2.5-flash")
        system_instruction = (
                input_data.get("system_instruction") or
                input_data.get("messages") or
                "You are a professional assistant."
        )
        if system_instruction is not None:
            system_instruction = ensure_string(system_instruction)
        user_input = ensure_string(input_data.get("user_content", ""))
        temperature = float(input_data.get("temperature", 0.3))
        connection_id = input_data.get("connection_id")
        max_output_tokens = int(input_data.get("max_output_tokens", 4096))

        if not user_input:
            raise NodeExecutionError(
                message="Agent Node requires 'user_content' (prompt)",
                node_type=self.node_type,
                retryable=False
            )

        # 2. Get model configuration
        model_config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["default"])
        context_manager = ContextManager(model_config)

        # 3. Prepare context with token management
        history = input_data.get("history_text", "")

        system, prompt, truncated_history, token_metadata = context_manager.prepare_context(
            system=system_instruction,
            prompt=user_input,
            history=history
        )

        logger.info(
            f"Agent token usage: {token_metadata['total_tokens']} tokens "
            f"(system: {token_metadata['system_tokens']}, "
            f"prompt: {token_metadata['prompt_tokens']}, "
            f"history: {token_metadata['history_tokens']})"
        )

        if token_metadata.get("history_truncated"):
            logger.warning("History truncated to fit context window.")

        # 4. Build full prompt with history
        if truncated_history:
            full_prompt = f"{truncated_history}\n\nUser: {prompt}"
        else:
            full_prompt = prompt

        try:
            # 5. Call LLM with usage tracking
            result, usage = await self._call_gemini_with_usage(
                db=db,
                context=context,
                connection_id=connection_id,
                model=model_name,
                system=system,
                prompt=full_prompt,
                temperature=temperature,
                max_output_tokens=min(max_output_tokens, model_config.output_limit),
                tools=input_data.get("tools", []),
                response_format=input_data.get("response_format")
            )

            return {
                "status": "success",
                "model": model_name,
                "content": result.get("text"),
                "tool_calls": result.get("tool_calls"),
                "raw_thought": result.get("thought"),
                "usage": usage.to_dict(),  # Normalized format for executor
                "token_metadata": token_metadata  # Keep detailed metadata too
            }

        except ConnectionError:
            raise
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise NodeExecutionError(
                message=f"Agent execution failed: {str(e)}",
                node_type=self.node_type,
                retryable=True
            )

    async def _call_gemini_with_usage(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            connection_id: Optional[str],
            model: str,
            system: str,
            prompt: str,
            temperature: float,
            max_output_tokens: int,
            tools: List[Any],
            response_format: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], AgentUsage]:
        """Internal gateway to Gemini API with usage extraction."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise NodeExecutionError(
                message="google-genai package not installed",
                node_type=self.node_type,
                retryable=False
            )

        api_key = None
        if connection_id:
            import uuid
            try:
                # 1. Try to fetch connection credentials
                uid = uuid.UUID(connection_id)
                stmt = select(Connection).where(Connection.id == str(uid))
                result = await db.execute(stmt)
                conn = result.scalars().first()

                if conn:
                    try:
                        creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
                        api_key = creds.get("api_key")
                    except Exception as e:
                        logger.warning(f"Failed to decrypt connection credentials: {e}")
            except ValueError:
                # If connection_id is not a valid UUID, treat it as a raw API key
                api_key = connection_id

        if not api_key:
            from src.services.api_key_resolver import resolve_api_key
            try:
                api_key = await resolve_api_key(
                    user_id=context.user_id,
                    provider="gemini",
                    feature="workflow"
                )
            except Exception as e:
                logger.error(f"Failed to resolve API key for provider 'gemini': {e}")

        if not api_key:
            raise ConnectionError(
                message="Failed to resolve Agent API key from connection, custom model config, or system-wide .env setting.",
                node_type=self.node_type,
                provider="google"
            )

        # 2. Initialize client
        client = genai.Client(api_key=api_key)

        # 3. Build configuration
        config_kwargs = {
            "system_instruction": system,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }

        if response_format:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_format

        # 4. Execute API call (non-blocking)
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs)
            )
        except Exception as e:
            error_msg = str(e)
            if api_key and api_key in error_msg:
                error_msg = error_msg.replace(api_key, "[REDACTED]")
            raise NodeExecutionError(
                message=f"Gemini API error: {error_msg}",
                node_type=self.node_type,
                retryable="rate" in error_msg.lower() or "quota" in error_msg.lower()
            )

        # 5. Parse response
        text_content = ""
        tool_calls = []

        if response.candidates:
            candidate = response.candidates[0]

            if hasattr(candidate, 'content') and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_content += part.text

                    func_call = getattr(part, 'function_call', None)
                    if func_call is None:
                        func_call = getattr(part, 'call', None)

                    if func_call:
                        tool_calls.append({
                            "id": f"call_{str(uuid.uuid4())[:8]}",
                            "function": {
                                "name": getattr(func_call, 'name', 'unknown'),
                                "arguments": dict(func_call.args) if hasattr(func_call, 'args') else {}
                            }
                        })

        # 6. Extract usage metadata
        usage = AgentUsage()
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage.input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            usage.output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            usage.total_tokens = usage.input_tokens + usage.output_tokens

            # Calculate cost
            cost = CostCalculator.calculate(
                provider="gemini",
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens
            )
            usage.cost_usd = str(cost)

            logger.debug(
                f"Agent usage: {usage.input_tokens} in, {usage.output_tokens} out, ${usage.cost_usd}"
            )

        return {
            "text": text_content,
            "tool_calls": tool_calls if tool_calls else None,
            "thought": getattr(response, "thought", None)
        }, usage