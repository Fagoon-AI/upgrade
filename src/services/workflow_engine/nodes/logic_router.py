import json
import asyncio
import re
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


# ============================================================
# ROUTING CONFIGURATION
# ============================================================

@dataclass
class RouterConfig:
    """Configuration for router behavior."""
    ai_timeout: float = 30.0           # AI API timeout in seconds
    max_retries: int = 2               # Max AI retry attempts
    retry_delay: float = 1.0           # Delay between retries
    enable_rule_fallback: bool = True  # Use rules if AI fails
    default_branch: str = "default"    # Ultimate fallback branch
    confidence_threshold: float = 0.7  # Min confidence for AI decision


@dataclass
class RoutingRule:
    """A rule-based routing condition."""
    branch: str
    keywords: List[str]
    patterns: List[str]  # Regex patterns
    priority: int = 0    # Higher = checked first


class RuleBasedRouter:
    """
    Rule-based router for fallback when AI is unavailable.

    Uses keyword matching and regex patterns to route requests.
    """

    def __init__(self, rules: List[RoutingRule]):
        self.rules = sorted(rules, key=lambda r: -r.priority)
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}

        # Pre-compile regex patterns
        for rule in self.rules:
            self._compiled_patterns[rule.branch] = [
                re.compile(p, re.IGNORECASE) for p in rule.patterns
            ]

    def route(self, input_text: str, branches: List[str]) -> Tuple[str, str]:
        """
        Routes based on rules.

        Returns:
            Tuple of (selected_branch, reasoning)
        """
        input_lower = input_text.lower()

        for rule in self.rules:
            if rule.branch not in branches:
                continue

            # Check keywords
            for keyword in rule.keywords:
                if keyword.lower() in input_lower:
                    return rule.branch, f"Matched keyword: '{keyword}'"

            # Check regex patterns
            for pattern in self._compiled_patterns.get(rule.branch, []):
                if pattern.search(input_text):
                    return rule.branch, f"Matched pattern: '{pattern.pattern}'"

        # No match - return first branch as default
        return branches[0] if branches else "default", "No rule matched, using default"

    @classmethod
    def from_branch_config(cls, branch_config: List[Dict[str, Any]]) -> 'RuleBasedRouter':
        """
        Creates router from branch configuration.

        Expected format:
        [
            {"branch": "support", "keywords": ["help", "issue"], "patterns": ["bug\\s*report"]},
            {"branch": "sales", "keywords": ["buy", "price"], "patterns": ["how\\s*much"]}
        ]
        """
        rules = []
        for idx, config in enumerate(branch_config):
            rules.append(RoutingRule(
                branch=config.get("branch", f"branch_{idx}"),
                keywords=config.get("keywords", []),
                patterns=config.get("patterns", []),
                priority=config.get("priority", 0)
            ))
        return cls(rules)


# ============================================================
# DEFAULT ROUTING RULES
# ============================================================

DEFAULT_ROUTING_RULES = [
    RoutingRule(
        branch="support",
        keywords=["help", "issue", "problem", "error", "bug", "broken", "not working", "fix"],
        patterns=[r"can'?t\s+\w+", r"doesn'?t\s+work", r"having\s+trouble"],
        priority=10
    ),
    RoutingRule(
        branch="sales",
        keywords=["buy", "purchase", "price", "cost", "pricing", "quote", "demo", "trial"],
        patterns=[r"how\s+much", r"want\s+to\s+buy", r"interested\s+in"],
        priority=10
    ),
    RoutingRule(
        branch="billing",
        keywords=["invoice", "payment", "charge", "refund", "subscription", "cancel"],
        patterns=[r"billing\s+issue", r"charged\s+\w+"],
        priority=10
    ),
    RoutingRule(
        branch="technical",
        keywords=["api", "integration", "code", "developer", "sdk", "documentation"],
        patterns=[r"api\s+\w+", r"how\s+to\s+integrate"],
        priority=5
    ),
]


# ROUTER NODE IMPLEMENTATION

class RouterNode(BaseNode):
    """
    AI Router with Fallback Strategies.

    Features:
    - AI-powered intent classification
    - Rule-based fallback when AI fails
    - Configurable routing rules
    - Retry logic with timeout
    - Confidence scoring

    Routing Strategy:
    1. Try AI classification (primary)
    2. If AI fails, use rule-based routing (fallback)
    3. If no rules match, use default branch
    """

    node_type = "routerNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "AI Router",
            "icon": "Split",
            "category": "Logic & Flow",
            "description": "Intelligent branching with AI and rule-based fallback.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "AI Connection",
                    "type": "connection_select",
                    "required": False,  # Not required if using rules only
                    "provider": "GOOGLE",
                    "helper": "Optional: Leave empty for rule-based routing only"
                },
                {
                    "name": "prompt",
                    "label": "Input to Analyze",
                    "type": "textarea",
                    "placeholder": "{{steps['start-1'].user_message}}",
                    "required": True
                },
                {
                    "name": "routing_instruction",
                    "label": "Routing Instructions",
                    "type": "textarea",
                    "placeholder": "Classify the user intent: support request, sales inquiry, or general question",
                    "helper": "Instructions for AI classification"
                },
                {
                    "name": "branches",
                    "label": "Available Branches",
                    "type": "list",
                    "default": ["support", "sales", "other"]
                },
                {
                    "name": "branch_rules",
                    "label": "Routing Rules (JSON)",
                    "type": "json_editor",
                    "placeholder": '[{"branch": "support", "keywords": ["help", "issue"]}]',
                    "helper": "Fallback rules when AI unavailable"
                },
                {
                    "name": "default_branch",
                    "label": "Default Branch",
                    "type": "text",
                    "default": "other",
                    "helper": "Used when no match found"
                },
                {
                    "name": "ai_only",
                    "label": "AI Only Mode",
                    "type": "boolean",
                    "default": False,
                    "helper": "Disable rule-based fallback"
                },
                {
                    "name": "model",
                    "label": "AI Model",
                    "type": "select",
                    "options": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"],
                    "default": "gemini-2.0-flash"
                }
            ],
            "outputs": ["selected_branch", "reasoning", "method", "confidence"]
        }

    def __init__(self):
        super().__init__()
        self.config = RouterConfig()
        self._default_rule_router = RuleBasedRouter(DEFAULT_ROUTING_RULES)

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes intelligent routing with fallback.
        """
        # 1. Extract configuration
        connection_id = input_data.get("connection_id")
        prompt = input_data.get("prompt", "")
        routing_instruction = input_data.get("routing_instruction", "")
        branches = input_data.get("branches", ["default"])
        default_branch = input_data.get("default_branch", "other")
        ai_only = input_data.get("ai_only", False)
        model = input_data.get("model", "gemini-2.0-flash")

        # Ensure branches is a list
        if isinstance(branches, str):
            branches = [b.strip() for b in branches.split(",")]

        # Ensure default branch is in branches
        if default_branch not in branches:
            branches.append(default_branch)

        if not prompt:
            raise NodeExecutionError(
                message="Router requires 'prompt' input to analyze",
                node_type=self.node_type,
                retryable=False
            )

        # 2. Build rule-based router
        rule_router = self._build_rule_router(input_data.get("branch_rules"))

        # 3. Try AI routing first (if connection provided)
        if connection_id:
            try:
                result = await self._route_with_ai(
                    db=db,
                    connection_id=connection_id,
                    prompt=prompt,
                    routing_instruction=routing_instruction,
                    branches=branches,
                    model=model
                )

                if result:
                    selected, reasoning, confidence = result

                    # Validate AI selected a valid branch
                    if selected in branches:
                        return {
                            "status": "success",
                            "selected_branch": selected,
                            "reasoning": reasoning,
                            "method": "ai",
                            "confidence": confidence
                        }
                    else:
                        logger.warning(f"AI selected invalid branch '{selected}', using fallback")

            except Exception as e:
                logger.warning(f"AI routing failed: {e}")

                if ai_only:
                    # AI-only mode, no fallback allowed
                    raise NodeExecutionError(
                        message=f"AI routing failed and fallback disabled: {e}",
                        node_type=self.node_type,
                        retryable=True
                    )

        # 4. Fallback to rule-based routing
        if not ai_only:
            selected, reasoning = rule_router.route(prompt, branches)

            return {
                "status": "success",
                "selected_branch": selected,
                "reasoning": reasoning,
                "method": "rules",
                "confidence": 0.8 if "Matched" in reasoning else 0.5
            }

        # 5. Ultimate fallback
        return {
            "status": "success",
            "selected_branch": default_branch,
            "reasoning": "No routing method succeeded, using default",
            "method": "default",
            "confidence": 0.0
        }

    def _build_rule_router(self, rules_config: Any) -> RuleBasedRouter:
        """Builds rule router from config or uses defaults."""
        if not rules_config:
            return self._default_rule_router

        try:
            if isinstance(rules_config, str):
                rules_config = json.loads(rules_config)

            if isinstance(rules_config, list) and rules_config:
                return RuleBasedRouter.from_branch_config(rules_config)
        except Exception as e:
            logger.warning(f"Failed to parse routing rules: {e}")

        return self._default_rule_router

    async def _route_with_ai(
            self,
            db: AsyncSession,
            connection_id: str,
            prompt: str,
            routing_instruction: str,
            branches: List[str],
            model: str
    ) -> Optional[Tuple[str, str, float]]:
        """
        Routes using AI classification.

        Returns:
            Tuple of (branch, reasoning, confidence) or None if failed
        """
        # Import here to handle missing dependency gracefully
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.error("google-genai package not installed")
            return None

        # 1. Get API credentials
        result = await db.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        conn = result.scalars().first()

        if not conn:
            raise ConnectionError(
                message=f"Connection {connection_id} not found",
                node_type=self.node_type,
                provider="google"
            )

        try:
            creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
            api_key = creds.get("api_key")
        except Exception:
            raise ConnectionError(
                message="Failed to decrypt credentials",
                node_type=self.node_type,
                provider="google"
            )

        if not api_key:
            raise ConnectionError(
                message="Connection missing API key",
                node_type=self.node_type,
                provider="google"
            )

        # 2. Build AI prompt
        branches_str = ", ".join(branches)
        system_prompt = f"""You are a routing classifier. Analyze the input and select exactly ONE branch from this list: [{branches_str}]

{routing_instruction if routing_instruction else "Classify the user's intent based on the content."}

IMPORTANT: Respond with ONLY the branch name, nothing else. No explanation, no punctuation, just the exact branch name from the list."""

        # 3. Call AI with retry
        client = genai.Client(api_key=api_key)
        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents=f"{system_prompt}\n\nInput to classify:\n{prompt}",
                        config=types.GenerateContentConfig(
                            temperature=0.1,  # Low temperature for consistent classification
                            max_output_tokens=50
                        )
                    ),
                    timeout=self.config.ai_timeout
                )

                # Parse response
                if response.candidates and response.candidates[0].content:
                    text = response.candidates[0].content.parts[0].text.strip()

                    # Clean up response (remove quotes, punctuation)
                    selected = text.strip().strip('"\'').strip().lower()

                    # Find matching branch (case-insensitive)
                    for branch in branches:
                        if branch.lower() == selected or selected in branch.lower():
                            return branch, f"AI classified as: {branch}", 0.9

                    # Try fuzzy match
                    for branch in branches:
                        if branch.lower() in selected or selected in branch.lower():
                            return branch, f"AI fuzzy matched: {branch}", 0.7

                    # AI returned something not in branches
                    logger.warning(f"AI returned '{text}' which doesn't match branches: {branches}")
                    return None

            except asyncio.TimeoutError:
                last_error = "API timeout"
                logger.warning(f"AI routing timeout (attempt {attempt})")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"AI routing error (attempt {attempt}): {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        logger.error(f"AI routing failed after {self.config.max_retries} attempts: {last_error}")
        return None