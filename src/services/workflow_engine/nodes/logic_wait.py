import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import BaseLoader
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext


# ============================================================
# CONFIGURATION
# ============================================================

class WaitMode(str, Enum):
    """Wait node modes."""
    MANUAL = "manual"           # Wait for manual approval
    TIMEOUT = "timeout"         # Wait for specified duration
    CONDITION = "condition"     # Wait until condition is true
    WEBHOOK = "webhook"         # Wait for webhook callback
    SCHEDULE = "schedule"       # Wait until specific time


class TimeoutAction(str, Enum):
    """Action to take on timeout."""
    APPROVE = "approve"   # Auto-approve on timeout
    REJECT = "reject"     # Auto-reject on timeout
    ERROR = "error"       # Raise error on timeout
    CONTINUE = "continue" # Continue with default


@dataclass
class WaitConfig:
    """Configuration for wait operations."""
    default_timeout_hours: int = 24
    max_timeout_hours: int = 168  # 1 week
    min_timeout_seconds: int = 60


# ============================================================
# WAIT NODE
# ============================================================

class WaitNode(BaseNode):
    """
    World-Class Wait/Human-in-the-Loop Node.

    Features:
    - Manual approval with custom messages
    - Configurable timeout with auto-action
    - Conditional waiting
    - Webhook callback support
    - Scheduled resume
    - Multiple approvers
    - Notification hooks

    Modes:
    - manual: Wait for human approval/rejection
    - timeout: Wait for specified duration then continue
    - condition: Poll until condition becomes true
    - webhook: Wait for external webhook callback
    - schedule: Wait until specific datetime

    The executor handles the actual pause/resume logic -
    this node configures the wait behavior.
    """

    node_type = "waitNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Wait",
            "icon": "Pause",
            "category": "Logic & Flow",
            "description": "Pause execution for approval, timeout, or external signal.",
            "fields": [
                {
                    "name": "mode",
                    "label": "Wait Mode",
                    "type": "select",
                    "options": ["manual", "timeout", "condition", "webhook"],
                    "default": "manual",
                    "helper": "How to determine when to continue"
                },
                {
                    "name": "message",
                    "label": "Display Message",
                    "type": "textarea",
                    "default": "Waiting for approval...",
                    "helper": "Message shown in the UI"
                },
                {
                    "name": "timeout_hours",
                    "label": "Timeout (hours)",
                    "type": "number",
                    "default": 24,
                    "min": 0,
                    "helper": "0 = no timeout"
                },
                {
                    "name": "timeout_action",
                    "label": "On Timeout",
                    "type": "select",
                    "options": ["approve", "reject", "error", "continue"],
                    "default": "error",
                    "helper": "Action to take when timeout is reached"
                },
                {
                    "name": "wait_condition",
                    "label": "Wait Condition",
                    "type": "textarea",
                    "placeholder": "{{ steps['external'].status == 'ready' }}",
                    "conditional": {"mode": "condition"},
                    "helper": "Continue when this becomes true"
                },
                {
                    "name": "poll_interval_seconds",
                    "label": "Poll Interval (seconds)",
                    "type": "number",
                    "default": 60,
                    "min": 10,
                    "conditional": {"mode": "condition"},
                    "helper": "How often to check condition"
                },
                {
                    "name": "require_comment",
                    "label": "Require Comment",
                    "type": "boolean",
                    "default": False,
                    "conditional": {"mode": "manual"},
                    "helper": "Require approver to provide a comment"
                },
                {
                    "name": "allowed_actions",
                    "label": "Allowed Actions",
                    "type": "text",
                    "default": "approve,reject",
                    "conditional": {"mode": "manual"},
                    "helper": "Comma-separated list of allowed actions"
                },
                {
                    "name": "notification_webhook",
                    "label": "Notification Webhook",
                    "type": "text",
                    "placeholder": "https://hooks.slack.com/...",
                    "helper": "URL to notify when wait starts"
                },
                {
                    "name": "notification_payload",
                    "label": "Notification Payload",
                    "type": "json_editor",
                    "placeholder": '{"text": "Approval needed: {{message}}"}',
                    "helper": "JSON payload for notification webhook"
                },
                {
                    "name": "data_to_pass",
                    "label": "Data to Display",
                    "type": "json_editor",
                    "placeholder": "{{ steps['processor'].summary }}",
                    "helper": "Data to show in approval UI"
                }
            ],
            "outputs": ["approved", "rejected", "timeout", "error"]
        }

    def __init__(self):
        super().__init__()
        self.config = WaitConfig()
        self.jinja = SandboxedEnvironment(loader=BaseLoader())

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes wait node configuration."""
        mode = input_data.get("mode", "manual")

        # Check if this is a resume call
        resume_action = input_data.get("_resume_action")
        if resume_action:
            return await self._handle_resume(resume_action, input_data, context)

        # Initial execution - configure the wait
        if mode == "manual":
            return await self._configure_manual_wait(input_data, context)
        elif mode == "timeout":
            return await self._configure_timeout_wait(input_data, context)
        elif mode == "condition":
            return await self._configure_condition_wait(input_data, context)
        elif mode == "webhook":
            return await self._configure_webhook_wait(input_data, context)
        else:
            return {
                "status": "error",
                "error": f"Unknown wait mode: {mode}",
                "selected_branch": "error"
            }

    async def _configure_manual_wait(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Configures manual approval wait."""
        message = input_data.get("message", "Waiting for approval...")

        # Resolve message template
        message = self._render_template(message, context)

        # Parse allowed actions
        allowed_actions = input_data.get("allowed_actions", "approve,reject")
        actions = [a.strip().lower() for a in allowed_actions.split(",") if a.strip()]

        if not actions:
            actions = ["approve", "reject"]

        # Calculate timeout
        timeout_hours = float(input_data.get("timeout_hours", self.config.default_timeout_hours))
        timeout_hours = min(timeout_hours, self.config.max_timeout_hours)

        timeout_at = None
        if timeout_hours > 0:
            timeout_at = datetime.now(timezone.utc) + timedelta(hours=timeout_hours)

        # Get data to display
        display_data = self._resolve_display_data(input_data, context)

        response = {
            "status": "waiting",
            "mode": "manual",
            "message": message,
            "allowed_actions": actions,
            "require_comment": input_data.get("require_comment", False),
            "display_data": display_data,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "selected_branch": "paused"  # Special signal for executor
        }

        if timeout_at:
            response["timeout_at"] = timeout_at.isoformat()
            response["timeout_action"] = input_data.get("timeout_action", "error")

        # Trigger notification if configured
        await self._send_notification(input_data, message, context)

        return response

    async def _configure_timeout_wait(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Configures simple timeout wait."""
        timeout_hours = float(input_data.get("timeout_hours", 1))
        timeout_hours = max(
            self.config.min_timeout_seconds / 3600,
            min(timeout_hours, self.config.max_timeout_hours)
        )

        resume_at = datetime.now(timezone.utc) + timedelta(hours=timeout_hours)
        message = input_data.get("message", f"Waiting for {timeout_hours} hours...")

        return {
            "status": "waiting",
            "mode": "timeout",
            "message": self._render_template(message, context),
            "timeout_hours": timeout_hours,
            "resume_at": resume_at.isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "selected_branch": "paused"
        }

    async def _configure_condition_wait(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Configures condition-based wait."""
        condition = input_data.get("wait_condition", "").strip()

        if not condition:
            return {
                "status": "error",
                "error": "Condition expression is required for condition mode",
                "selected_branch": "error"
            }

        poll_interval = max(10, int(input_data.get("poll_interval_seconds", 60)))

        # Check if condition is already true
        is_true = self._evaluate_condition(condition, context)

        if is_true:
            return {
                "status": "success",
                "mode": "condition",
                "message": "Condition already met",
                "condition_met": True,
                "selected_branch": "approved"
            }

        # Calculate timeout
        timeout_hours = float(input_data.get("timeout_hours", self.config.default_timeout_hours))
        timeout_at = None
        if timeout_hours > 0:
            timeout_at = datetime.now(timezone.utc) + timedelta(hours=timeout_hours)

        response = {
            "status": "waiting",
            "mode": "condition",
            "message": self._render_template(input_data.get("message", "Waiting for condition..."), context),
            "condition": condition,
            "poll_interval_seconds": poll_interval,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "selected_branch": "paused"
        }

        if timeout_at:
            response["timeout_at"] = timeout_at.isoformat()
            response["timeout_action"] = input_data.get("timeout_action", "error")

        return response

    async def _configure_webhook_wait(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Configures webhook callback wait."""
        # Generate unique callback ID
        import uuid
        callback_id = str(uuid.uuid4())

        timeout_hours = float(input_data.get("timeout_hours", self.config.default_timeout_hours))
        timeout_at = None
        if timeout_hours > 0:
            timeout_at = datetime.now(timezone.utc) + timedelta(hours=timeout_hours)

        response = {
            "status": "waiting",
            "mode": "webhook",
            "message": self._render_template(input_data.get("message", "Waiting for webhook callback..."), context),
            "callback_id": callback_id,
            "execution_id": context.execution_id,
            "workflow_id": context.workflow_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "selected_branch": "paused"
        }

        if timeout_at:
            response["timeout_at"] = timeout_at.isoformat()
            response["timeout_action"] = input_data.get("timeout_action", "error")

        # Trigger notification with callback info
        await self._send_notification(input_data, response["message"], context, callback_id=callback_id)

        return response

    async def _handle_resume(
            self,
            action: str,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Handles resume from wait state."""
        action = action.lower()

        # Map action to branch
        branch_map = {
            "approve": "approved",
            "approved": "approved",
            "accept": "approved",
            "continue": "approved",
            "yes": "approved",
            "reject": "rejected",
            "rejected": "rejected",
            "deny": "rejected",
            "no": "rejected",
            "cancel": "rejected",
            "timeout": "timeout",
            "error": "error"
        }

        selected_branch = branch_map.get(action, "approved")

        # Get comment if provided
        comment = input_data.get("_resume_comment")
        approver = input_data.get("_resume_by")

        return {
            "status": "resumed",
            "action": action,
            "selected_branch": selected_branch,
            "comment": comment,
            "resumed_by": approver,
            "resumed_at": datetime.now(timezone.utc).isoformat()
        }

    def _render_template(self, template: str, context: ExecutionContext) -> str:
        """Renders a Jinja2 template string."""
        if not template or "{{" not in template:
            return template

        try:
            t = self.jinja.from_string(template)
            return t.render(
                steps=context.node_outputs,
                execution_id=context.execution_id,
                workflow_id=context.workflow_id
            )
        except Exception as e:
            logger.warning(f"Template render error: {e}")
            return template

    def _evaluate_condition(self, condition: str, context: ExecutionContext) -> bool:
        """Evaluates a condition expression."""
        try:
            t = self.jinja.from_string(condition)
            result = t.render(steps=context.node_outputs).strip().lower()
            return result in ("true", "1", "yes", "y")
        except Exception:
            return False

    def _resolve_display_data(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Optional[Any]:
        """Resolves data to display in approval UI."""
        data_template = input_data.get("data_to_pass")

        if not data_template:
            return None

        if isinstance(data_template, str):
            rendered = self._render_template(data_template, context)
            try:
                return json.loads(rendered)
            except:
                return rendered

        return data_template

    async def _send_notification(
            self,
            input_data: Dict[str, Any],
            message: str,
            context: ExecutionContext,
            callback_id: str = None
    ) -> None:
        """Sends notification webhook if configured."""
        webhook_url = input_data.get("notification_webhook")

        if not webhook_url:
            return

        try:
            import httpx

            # Build payload
            payload_template = input_data.get("notification_payload", '{"text": "{{message}}"}')

            if isinstance(payload_template, str):
                # Simple template substitution
                payload_str = payload_template.replace("{{message}}", message)
                if callback_id:
                    payload_str = payload_str.replace("{{callback_id}}", callback_id)

                try:
                    payload = json.loads(payload_str)
                except:
                    payload = {"text": message}
            else:
                payload = payload_template

            # Add context
            payload["execution_id"] = context.execution_id
            payload["workflow_id"] = context.workflow_id

            if callback_id:
                payload["callback_id"] = callback_id

            # Send notification (fire and forget)
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook_url, json=payload)

        except Exception as e:
            logger.warning(f"Failed to send wait notification: {e}")