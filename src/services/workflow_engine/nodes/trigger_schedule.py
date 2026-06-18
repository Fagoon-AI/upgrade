"""
Schedule Trigger Node.

Entry point for scheduled/automated workflow execution.
Supports cron expressions, intervals, and one-time triggers.

Version: 1.0.0
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext


# Common cron presets for UI
CRON_PRESETS = {
    "every_minute": {"label": "Every Minute", "cron": "* * * * *"},
    "every_5_minutes": {"label": "Every 5 Minutes", "cron": "*/5 * * * *"},
    "every_15_minutes": {"label": "Every 15 Minutes", "cron": "*/15 * * * *"},
    "every_30_minutes": {"label": "Every 30 Minutes", "cron": "*/30 * * * *"},
    "hourly": {"label": "Every Hour", "cron": "0 * * * *"},
    "daily_9am": {"label": "Daily at 9:00 AM", "cron": "0 9 * * *"},
    "daily_midnight": {"label": "Daily at Midnight", "cron": "0 0 * * *"},
    "weekly_monday_9am": {"label": "Weekly on Monday at 9:00 AM", "cron": "0 9 * * 1"},
    "monthly_first_9am": {"label": "Monthly on 1st at 9:00 AM", "cron": "0 9 1 * *"},
}

# Common intervals for UI
INTERVAL_PRESETS = {
    "1_minute": {"label": "Every 1 Minute", "seconds": 60},
    "5_minutes": {"label": "Every 5 Minutes", "seconds": 300},
    "15_minutes": {"label": "Every 15 Minutes", "seconds": 900},
    "30_minutes": {"label": "Every 30 Minutes", "seconds": 1800},
    "1_hour": {"label": "Every 1 Hour", "seconds": 3600},
    "6_hours": {"label": "Every 6 Hours", "seconds": 21600},
    "12_hours": {"label": "Every 12 Hours", "seconds": 43200},
    "24_hours": {"label": "Every 24 Hours", "seconds": 86400},
}


class ScheduleTriggerNode(BaseNode):
    """
    Schedule Trigger Node.

    Entry point for automated workflow execution. Workflows starting with this
    node can be triggered on a schedule (cron, interval, or one-time).

    Features:
    - Cron expression support (e.g., "0 9 * * *" for 9am daily)
    - Interval-based scheduling (e.g., every 5 minutes)
    - One-time scheduling (run at specific datetime)
    - Timezone support
    - Passes schedule context to downstream nodes

    Usage:
    1. Add this node as the first node in your workflow
    2. Configure the schedule type and expression
    3. Save and publish the workflow
    4. The system will automatically create a schedule for this workflow

    The node outputs:
    - trigger_type: "scheduled"
    - schedule_type: "cron", "interval", or "once"
    - scheduled_time: When this execution was scheduled
    - actual_time: When this execution actually started
    - run_number: Sequential run number
    - input_data: Any data passed to the scheduled run
    """

    node_type = "scheduleTriggerNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        # Build preset options
        cron_options = [
            {"value": k, "label": v["label"]}
            for k, v in CRON_PRESETS.items()
        ]
        cron_options.append({"value": "custom", "label": "Custom Expression"})

        interval_options = [
            {"value": k, "label": v["label"]}
            for k, v in INTERVAL_PRESETS.items()
        ]
        interval_options.append({"value": "custom", "label": "Custom Interval"})

        return {
            "type": cls.node_type,
            "display_name": "Schedule Trigger",
            "icon": "Clock",
            "category": "Triggers",
            "description": "Automatically trigger this workflow on a schedule - cron, interval, or one-time.",
            "fields": [
                {
                    "name": "schedule_type",
                    "label": "Schedule Type",
                    "type": "select",
                    "options": ["cron", "interval", "once"],
                    "default": "cron",
                    "helper": "How should this workflow be triggered?"
                },
                {
                    "name": "cron_preset",
                    "label": "Schedule Preset",
                    "type": "select",
                    "options": [o["value"] for o in cron_options],
                    "default": "daily_9am",
                    "helper": "Choose a common schedule or select 'Custom Expression'",
                    "depends_on": {"field": "schedule_type", "value": "cron"}
                },
                {
                    "name": "cron_expression",
                    "label": "Cron Expression",
                    "type": "text",
                    "placeholder": "0 9 * * *",
                    "helper": "Standard cron format: minute hour day month weekday (e.g., '0 9 * * 1-5' for 9am weekdays)",
                    "depends_on": {"field": "cron_preset", "value": "custom"}
                },
                {
                    "name": "interval_preset",
                    "label": "Interval Preset",
                    "type": "select",
                    "options": [o["value"] for o in interval_options],
                    "default": "1_hour",
                    "helper": "Choose a common interval or select 'Custom Interval'",
                    "depends_on": {"field": "schedule_type", "value": "interval"}
                },
                {
                    "name": "interval_seconds",
                    "label": "Interval (seconds)",
                    "type": "number",
                    "placeholder": "3600",
                    "helper": "Run every X seconds (minimum 60)",
                    "depends_on": {"field": "interval_preset", "value": "custom"}
                },
                {
                    "name": "run_at",
                    "label": "Run At",
                    "type": "datetime",
                    "helper": "Specific date and time to run (for one-time schedules)",
                    "depends_on": {"field": "schedule_type", "value": "once"}
                },
                {
                    "name": "timezone",
                    "label": "Timezone",
                    "type": "select",
                    "options": [
                        "UTC",
                        "America/New_York",
                        "America/Chicago",
                        "America/Denver",
                        "America/Los_Angeles",
                        "Europe/London",
                        "Europe/Paris",
                        "Europe/Berlin",
                        "Asia/Tokyo",
                        "Asia/Shanghai",
                        "Asia/Kolkata",
                        "Australia/Sydney"
                    ],
                    "default": "UTC",
                    "helper": "Timezone for schedule interpretation"
                },
                {
                    "name": "enabled",
                    "label": "Schedule Enabled",
                    "type": "boolean",
                    "default": True,
                    "helper": "Toggle to enable/disable this schedule"
                }
            ],
            "outputs": [
                "trigger_type",
                "schedule_type",
                "scheduled_time",
                "actual_time",
                "run_number",
                "input_data",
                "status"
            ],
            "outputs_schema": {
                "trigger_type": {"type": "string", "description": "Always 'scheduled'"},
                "schedule_type": {"type": "string", "description": "Type of schedule (cron, interval, once)"},
                "scheduled_time": {"type": "string", "description": "ISO timestamp when run was scheduled"},
                "actual_time": {"type": "string", "description": "ISO timestamp when run actually started"},
                "run_number": {"type": "integer", "description": "Sequential run number for this schedule"},
                "input_data": {"type": "object", "description": "Any data passed to the scheduled run"},
                "status": {"type": "string", "description": "Execution status ('started')"}
            },
            "version": "1.0.0",
            "tags": ["trigger", "schedule", "cron", "automation"],
            "is_trigger": True,
            "presets": {
                "cron": CRON_PRESETS,
                "interval": INTERVAL_PRESETS
            }
        }

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            node_id: str = None
    ) -> Dict[str, Any]:
        """
        Executes the schedule trigger node.

        This node is typically called by the scheduler when a schedule is due.
        It receives context about the scheduled execution and passes it downstream.

        Args:
            db: Database session
            context: Execution context
            input_data: Input data including schedule metadata

        Returns:
            Schedule trigger output with metadata
        """
        now = datetime.now(timezone.utc)

        # Extract schedule metadata from input
        schedule_type = input_data.get("schedule_type", "cron")
        scheduled_time = input_data.get("scheduled_time", now.isoformat())
        run_number = input_data.get("run_number", 1)
        schedule_input = input_data.get("input_data", {})
        schedule_id = input_data.get("schedule_id")

        # Get configuration from node config (for display purposes)
        cron_expression = input_data.get("cron_expression")
        cron_preset = input_data.get("cron_preset")
        interval_seconds = input_data.get("interval_seconds")
        interval_preset = input_data.get("interval_preset")
        timezone_str = input_data.get("timezone", "UTC")

        # Resolve preset to actual value if needed
        if schedule_type == "cron" and cron_preset and cron_preset != "custom":
            preset = CRON_PRESETS.get(cron_preset, {})
            cron_expression = preset.get("cron", cron_expression)

        if schedule_type == "interval" and interval_preset and interval_preset != "custom":
            preset = INTERVAL_PRESETS.get(interval_preset, {})
            interval_seconds = preset.get("seconds", interval_seconds)

        return {
            "status": "started",
            "trigger_type": "scheduled",
            "schedule_type": schedule_type,
            "scheduled_time": scheduled_time if isinstance(scheduled_time, str) else scheduled_time.isoformat(),
            "actual_time": now.isoformat(),
            "run_number": run_number,
            "input_data": schedule_input,
            "schedule_id": str(schedule_id) if schedule_id else None,
            "schedule_config": {
                "cron_expression": cron_expression,
                "interval_seconds": interval_seconds,
                "timezone": timezone_str
            }
        }

    @classmethod
    def get_effective_cron(cls, config: Dict[str, Any]) -> Optional[str]:
        """
        Resolves the effective cron expression from node configuration.

        Args:
            config: Node configuration

        Returns:
            Cron expression string or None
        """
        if config.get("schedule_type") != "cron":
            return None

        preset = config.get("cron_preset", "custom")
        if preset != "custom" and preset in CRON_PRESETS:
            return CRON_PRESETS[preset]["cron"]

        return config.get("cron_expression")

    @classmethod
    def get_effective_interval(cls, config: Dict[str, Any]) -> Optional[int]:
        """
        Resolves the effective interval from node configuration.

        Args:
            config: Node configuration

        Returns:
            Interval in seconds or None
        """
        if config.get("schedule_type") != "interval":
            return None

        preset = config.get("interval_preset", "custom")
        if preset != "custom" and preset in INTERVAL_PRESETS:
            return INTERVAL_PRESETS[preset]["seconds"]

        interval = config.get("interval_seconds")
        if interval:
            return max(60, int(interval))  # Minimum 60 seconds

        return None
