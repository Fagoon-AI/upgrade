import asyncio
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode, ensure_string
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto
from src.services.workflow.cost_tracking import CostCalculator


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class PerplexityConfig:
    """Configuration for Perplexity operations."""
    timeout: float = 120.0
    max_retries: int = 3
    retry_delay: float = 2.0
    default_max_tokens: int = 4096


PERPLEXITY_MODELS = {
    "sonar": {
        "name": "sonar",
        "description": "Fast search model",
        "context_length": 127072
    },
    "sonar-pro": {
        "name": "sonar-pro",
        "description": "Advanced search with deeper analysis",
        "context_length": 127072
    },
    "sonar-reasoning": {
        "name": "sonar-reasoning",
        "description": "Extended reasoning for complex queries",
        "context_length": 127072
    }
}

RECENCY_OPTIONS = ["day", "week", "month", "year", None]


# ============================================================
# USAGE TRACKING
# ============================================================

@dataclass
class PerplexityUsage:
    """Token usage from Perplexity API response."""
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
# PERPLEXITY CLIENT
# ============================================================

class PerplexityClient:
    """Robust Perplexity API client with retry logic."""

    API_BASE = "https://api.perplexity.ai"

    def __init__(self, api_key: str, config: Optional[PerplexityConfig] = None):
        self.api_key = api_key
        self.config = config or PerplexityConfig()

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def chat_completion(
            self,
            messages: List[Dict[str, str]],
            model: str = "sonar",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            search_domain_filter: Optional[List[str]] = None,
            search_recency_filter: Optional[str] = None,
            return_citations: bool = True
    ) -> Dict[str, Any]:
        """Executes a chat completion with search."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "return_citations": return_citations
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter

        if search_recency_filter and search_recency_filter in RECENCY_OPTIONS:
            payload["search_recency_filter"] = search_recency_filter

        return await self._make_request(payload, model)

    async def _make_request(self, payload: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Makes API request with retry logic."""
        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    response = await client.post(
                        f"{self.API_BASE}/chat/completions",
                        headers=self.headers,
                        json=payload
                    )

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 10))
                        logger.warning(f"Perplexity rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status_code >= 500:
                        if attempt < self.config.max_retries:
                            logger.warning(f"Perplexity server error {response.status_code}. Retrying...")
                            await asyncio.sleep(self.config.retry_delay * attempt)
                            continue

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data, model)

                    try:
                        error_data = response.json()
                        error_msg = error_data.get("error", {}).get("message", response.text)
                    except:
                        error_msg = response.text

                    return {
                        "success": False,
                        "error": f"API Error ({response.status_code}): {error_msg}"
                    }

            except httpx.TimeoutException:
                last_error = "Request timed out. Search queries may take longer."
                logger.warning(f"Perplexity timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Perplexity connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Perplexity request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "Max retries exceeded"}

    def _parse_response(self, data: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Parses and enriches API response with normalized usage."""
        try:
            choice = data["choices"][0]
            message = choice["message"]

            content = message.get("content", "")
            citations = data.get("citations", [])

            formatted_citations = []
            for i, url in enumerate(citations):
                formatted_citations.append({
                    "index": i + 1,
                    "url": url
                })

            images = data.get("images", [])

            # Extract and normalize usage
            raw_usage = data.get("usage", {})
            input_tokens = raw_usage.get("prompt_tokens", 0)
            output_tokens = raw_usage.get("completion_tokens", 0)

            # Calculate cost
            cost = CostCalculator.calculate(
                provider="perplexity",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

            # Normalized usage format (matches executor expectations)
            usage = PerplexityUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cost_usd=str(cost)
            )

            logger.debug(
                f"Perplexity usage: {input_tokens} in, {output_tokens} out, ${cost}"
            )

            return {
                "success": True,
                "content": content,
                "citations": formatted_citations,
                "citation_urls": citations,
                "images": images,
                "model": data.get("model"),
                "usage": usage.to_dict(),  # Normalized format
                "finish_reason": choice.get("finish_reason")
            }

        except (KeyError, IndexError) as e:
            return {
                "success": False,
                "error": f"Failed to parse response: {e}",
                "raw_response": data
            }


# ============================================================
# PERPLEXITY NODE
# ============================================================

class PerplexityNode(BaseNode):
    """
    Perplexity AI Integration Node with Cost Tracking.

    Features:
    - Real-time web search with AI
    - Multiple model support
    - Citation extraction
    - Domain filtering
    - Recency filtering
    - Token usage tracking for billing
    """

    node_type = "perplexityNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Perplexity AI",
            "icon": "Search",
            "category": "AI & Search",
            "description": "AI-powered web search with citations and cost tracking.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Perplexity Connection",
                    "type": "connection_select",
                    "required": True,
                    "provider": "PERPLEXITY"
                },
                {
                    "name": "prompt",
                    "label": "Search Query",
                    "type": "textarea",
                    "placeholder": "What would you like to search for?",
                    "required": True
                },
                {
                    "name": "system_prompt",
                    "label": "System Prompt",
                    "type": "textarea",
                    "default": "Be a helpful search assistant. Provide accurate, well-sourced information.",
                    "helper": "Instructions for how the AI should respond"
                },
                {
                    "name": "model",
                    "label": "Model",
                    "type": "select",
                    "options": list(PERPLEXITY_MODELS.keys()),
                    "default": "sonar"
                },
                {
                    "name": "temperature",
                    "label": "Temperature",
                    "type": "slider",
                    "min": 0,
                    "max": 1,
                    "step": 0.1,
                    "default": 0.7
                },
                {
                    "name": "max_tokens",
                    "label": "Max Tokens",
                    "type": "number",
                    "default": 4096,
                    "helper": "Maximum response length"
                },
                {
                    "name": "search_recency",
                    "label": "Search Recency",
                    "type": "select",
                    "options": ["none", "day", "week", "month", "year"],
                    "default": "none",
                    "helper": "Filter results by time"
                },
                {
                    "name": "search_domains",
                    "label": "Domain Filter",
                    "type": "text",
                    "placeholder": "example.com, news.com",
                    "helper": "Comma-separated list of domains to search"
                },
                {
                    "name": "include_citations",
                    "label": "Include Citations",
                    "type": "boolean",
                    "default": True
                }
            ],
            "outputs": ["status", "answer", "citations", "usage", "model"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status"},
                "answer": {"type": "string", "description": "Search result"},
                "citations": {"type": "array", "description": "Source citations"},
                "usage": {"type": "object", "description": "Token usage and cost"},
                "model": {"type": "string", "description": "Model used"}
            }
        }

    def __init__(self):
        super().__init__()
        self.config = PerplexityConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            node_id: str = None
    ) -> Dict[str, Any]:
        """Executes Perplexity search with cost tracking."""
        # Get API key
        api_key = await self._get_api_key(db, input_data, context)

        if not api_key:
            return {"status": "error", "error": "API key is required"}

        # Get prompt
        prompt = ensure_string(input_data.get("prompt", "")).strip()
        if not prompt:
            return {"status": "error", "error": "Search query is required"}

        # Build messages
        system_prompt = input_data.get(
            "system_prompt",
            "Be a helpful search assistant. Provide accurate, well-sourced information."
        )
        if system_prompt is not None:
            system_prompt = ensure_string(system_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        # Get parameters
        model = input_data.get("model", "sonar")
        temperature = float(input_data.get("temperature", 0.7))
        max_tokens = input_data.get("max_tokens")

        recency = input_data.get("search_recency", "none")
        search_recency_filter = recency if recency != "none" else None

        domains_str = input_data.get("search_domains", "")
        search_domain_filter = None
        if domains_str:
            search_domain_filter = [d.strip() for d in domains_str.split(",") if d.strip()]

        include_citations = input_data.get("include_citations", True)

        # Create client and make request
        client = PerplexityClient(api_key, self.config)

        result = await client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            search_domain_filter=search_domain_filter,
            search_recency_filter=search_recency_filter,
            return_citations=include_citations
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Search failed")
            }

        # Format response with normalized usage
        response = {
            "status": "success",
            "answer": result.get("content"),
            "model": result.get("model"),
            "usage": result.get("usage", {})  # Already normalized by client
        }

        if include_citations:
            response["citations"] = result.get("citations", [])
            response["citation_urls"] = result.get("citation_urls", [])

        if result.get("images"):
            response["images"] = result.get("images")

        return response

    async def _get_api_key(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Optional[str]:
        """Gets API key from connection, direct input, or resolved fallback."""
        connection_id = input_data.get("connection_id")
        api_key = None

        if connection_id:
            import uuid
            try:
                # Try to parse as UUID to fetch from Connection table
                uid = uuid.UUID(connection_id)
                result = await db.execute(
                    select(Connection).where(Connection.id == str(uid))
                )
                conn = result.scalars().first()

                if conn:
                    try:
                        creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
                        api_key = creds.get("api_key")
                    except Exception as e:
                        logger.error(f"Failed to decrypt connection: {e}")
            except ValueError:
                # If connection_id is not a valid UUID, treat it as a raw API key
                api_key = connection_id

        if not api_key:
            api_key = input_data.get("api_key")

        if not api_key:
            from src.services.api_key_resolver import resolve_api_key
            try:
                api_key = await resolve_api_key(
                    user_id=context.user_id,
                    provider="perplexity",
                    feature="workflow"
                )
            except Exception as e:
                logger.error(f"Failed to resolve API key for provider 'perplexity': {e}")

        return api_key