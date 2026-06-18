import json
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext


# ============================================================
# CONFIGURATION
# ============================================================

class ParallelMode(str, Enum):
    """Parallel execution modes."""
    FAN_OUT = "fan_out"  # Split to multiple branches
    FAN_IN = "fan_in"    # Wait for all branches to complete
    RACE = "race"        # Return when first branch completes
    ALL_SETTLED = "all_settled"  # Wait for all, collect errors


class AggregationStrategy(str, Enum):
    """Result aggregation strategies."""
    LIST = "list"        # Collect all results in a list
    MERGE = "merge"      # Merge dictionaries
    FIRST = "first"      # Return first result only
    LAST = "last"        # Return last result only
    CONCAT = "concat"    # Concatenate strings/arrays


class FailureHandling(str, Enum):
    """How to handle branch failures."""
    FAIL_FAST = "fail_fast"      # Stop all on first failure
    FAIL_SLOW = "fail_slow"      # Continue, fail at end
    IGNORE = "ignore"            # Ignore failures
    COLLECT = "collect"          # Collect failures separately


@dataclass
class ParallelConfig:
    """Configuration for parallel execution."""
    default_concurrency: int = 10
    max_concurrency: int = 100
    default_timeout: int = 300  # seconds
    max_timeout: int = 3600     # 1 hour
    max_branches: int = 100


# ============================================================
# PARALLEL NODE
# ============================================================

class ParallelNode(BaseNode):
    """
    Parallel Execution Node.

    Features:
    - Fan-out to multiple downstream branches
    - Fan-in to collect results
    - Race mode (first to complete wins)
    - Configurable concurrency
    - Timeout per branch
    - Multiple aggregation strategies
    - Error handling modes

    Modes:
    - fan_out: Split execution to multiple branches
    - fan_in: Wait and collect results from parallel branches
    - race: Return as soon as one branch completes
    - all_settled: Wait for all, collect both results and errors

    The executor handles actual parallel execution - this node
    configures the behavior and aggregates results.
    """

    node_type = "parallelNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Parallel",
            "icon": "GitFork",
            "category": "Logic & Flow",
            "description": "Execute multiple branches in parallel with configurable concurrency.",
            "fields": [
                {
                    "name": "mode",
                    "label": "Execution Mode",
                    "type": "select",
                    "options": ["fan_out", "fan_in", "race", "all_settled"],
                    "default": "fan_out",
                    "helper": "fan_out: split, fan_in: collect, race: first wins"
                },
                {
                    "name": "max_concurrency",
                    "label": "Max Concurrency",
                    "type": "number",
                    "default": 10,
                    "min": 1,
                    "max": 100,
                    "helper": "Maximum simultaneous executions"
                },
                {
                    "name": "timeout_seconds",
                    "label": "Timeout (seconds)",
                    "type": "number",
                    "default": 300,
                    "helper": "Timeout per branch (0 = no timeout)"
                },
                {
                    "name": "aggregation",
                    "label": "Result Aggregation",
                    "type": "select",
                    "options": ["list", "merge", "first", "last", "concat"],
                    "default": "list",
                    "conditional": {"mode": ["fan_in", "all_settled"]},
                    "helper": "How to combine branch results"
                },
                {
                    "name": "failure_handling",
                    "label": "Failure Handling",
                    "type": "select",
                    "options": ["fail_fast", "fail_slow", "ignore", "collect"],
                    "default": "fail_fast",
                    "helper": "How to handle branch failures"
                },
                {
                    "name": "branch_data",
                    "label": "Branch Data",
                    "type": "json_editor",
                    "placeholder": '["branch1", "branch2"]',
                    "helper": "Data to pass to each branch (optional)"
                },
                {
                    "name": "wait_for_branches",
                    "label": "Branches to Wait For",
                    "type": "text",
                    "placeholder": "branch_1, branch_2",
                    "conditional": {"mode": ["fan_in", "all_settled"]},
                    "helper": "Comma-separated branch IDs to wait for"
                }
            ],
            "outputs": ["start", "completed", "error"]
        }

    def __init__(self):
        super().__init__()
        self.config = ParallelConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes parallel node configuration."""
        mode = input_data.get("mode", "fan_out")

        if mode == "fan_out":
            return await self._handle_fan_out(input_data, context)
        elif mode == "fan_in":
            return await self._handle_fan_in(input_data, context)
        elif mode == "race":
            return await self._handle_race(input_data, context)
        elif mode == "all_settled":
            return await self._handle_all_settled(input_data, context)
        else:
            return {
                "status": "error",
                "error": f"Unknown mode: {mode}",
                "selected_branch": "error"
            }

    async def _handle_fan_out(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Handles fan-out mode - splitting to multiple branches."""
        max_concurrency = min(
            int(input_data.get("max_concurrency", self.config.default_concurrency)),
            self.config.max_concurrency
        )

        timeout = min(
            int(input_data.get("timeout_seconds", self.config.default_timeout)),
            self.config.max_timeout
        )

        failure_handling = input_data.get("failure_handling", "fail_fast")

        # Parse branch data if provided
        branch_data = self._parse_branch_data(input_data.get("branch_data"))

        return {
            "status": "success",
            "mode": "fan_out",
            "max_concurrency": max_concurrency,
            "timeout_seconds": timeout,
            "failure_handling": failure_handling,
            "branch_data": branch_data,
            "branch_count": len(branch_data) if branch_data else 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "selected_branch": "start"
        }

    async def _handle_fan_in(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Handles fan-in mode - collecting results from branches."""
        aggregation = input_data.get("aggregation", "list")
        failure_handling = input_data.get("failure_handling", "fail_fast")

        # Get branches to wait for
        wait_for = input_data.get("wait_for_branches", "")
        branch_ids = [b.strip() for b in wait_for.split(",") if b.strip()]

        # Collect results from context
        results = []
        errors = []

        for branch_id in branch_ids:
            branch_output = context.node_outputs.get(branch_id)

            if branch_output is None:
                if failure_handling == "fail_fast":
                    return {
                        "status": "error",
                        "error": f"Branch '{branch_id}' not found or not completed",
                        "selected_branch": "error"
                    }
                errors.append({
                    "branch_id": branch_id,
                    "error": "Branch not found or not completed"
                })
            elif isinstance(branch_output, dict) and branch_output.get("status") == "error":
                if failure_handling == "fail_fast":
                    return {
                        "status": "error",
                        "error": f"Branch '{branch_id}' failed: {branch_output.get('error')}",
                        "selected_branch": "error"
                    }
                errors.append({
                    "branch_id": branch_id,
                    "error": branch_output.get("error")
                })
            else:
                results.append({
                    "branch_id": branch_id,
                    "output": branch_output
                })

        # Check for failures
        if errors and failure_handling == "fail_slow":
            return {
                "status": "error",
                "error": f"{len(errors)} branches failed",
                "errors": errors,
                "partial_results": results,
                "selected_branch": "error"
            }

        # Aggregate results
        aggregated = self._aggregate_results(results, aggregation)

        response = {
            "status": "success",
            "mode": "fan_in",
            "aggregation": aggregation,
            "results": aggregated,
            "branch_count": len(branch_ids),
            "success_count": len(results),
            "selected_branch": "completed"
        }

        if failure_handling == "collect" and errors:
            response["errors"] = errors

        return response

    async def _handle_race(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Handles race mode - first completion wins."""
        # Race mode configuration
        timeout = min(
            int(input_data.get("timeout_seconds", self.config.default_timeout)),
            self.config.max_timeout
        )

        return {
            "status": "success",
            "mode": "race",
            "timeout_seconds": timeout,
            "message": "Race mode: first branch to complete will provide the result",
            "selected_branch": "start"
        }

    async def _handle_all_settled(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Handles all_settled mode - wait for all, collect everything."""
        aggregation = input_data.get("aggregation", "list")

        # Get branches to wait for
        wait_for = input_data.get("wait_for_branches", "")
        branch_ids = [b.strip() for b in wait_for.split(",") if b.strip()]

        # Collect all results regardless of status
        fulfilled = []
        rejected = []

        for branch_id in branch_ids:
            branch_output = context.node_outputs.get(branch_id)

            if branch_output is None:
                rejected.append({
                    "branch_id": branch_id,
                    "status": "missing",
                    "reason": "Branch output not found"
                })
            elif isinstance(branch_output, dict) and branch_output.get("status") == "error":
                rejected.append({
                    "branch_id": branch_id,
                    "status": "rejected",
                    "reason": branch_output.get("error", "Unknown error")
                })
            else:
                fulfilled.append({
                    "branch_id": branch_id,
                    "status": "fulfilled",
                    "value": branch_output
                })

        # Aggregate successful results
        aggregated = self._aggregate_results(fulfilled, aggregation)

        return {
            "status": "success",
            "mode": "all_settled",
            "aggregation": aggregation,
            "results": aggregated,
            "fulfilled": fulfilled,
            "rejected": rejected,
            "fulfilled_count": len(fulfilled),
            "rejected_count": len(rejected),
            "total_branches": len(branch_ids),
            "selected_branch": "completed"
        }

    def _parse_branch_data(self, data: Any) -> Optional[List[Any]]:
        """Parses branch data configuration."""
        if data is None:
            return None

        if isinstance(data, list):
            return data

        if isinstance(data, str):
            data = data.strip()
            if not data:
                return None

            try:
                parsed = json.loads(data)
                if isinstance(parsed, list):
                    return parsed
                return [parsed]
            except json.JSONDecodeError:
                # Treat as comma-separated
                return [d.strip() for d in data.split(",") if d.strip()]

        return [data]

    def _aggregate_results(
            self,
            results: List[Dict[str, Any]],
            strategy: str
    ) -> Any:
        """Aggregates branch results using specified strategy."""
        if not results:
            return None

        # Extract output values
        values = [r.get("output") or r.get("value") for r in results]

        if strategy == "list":
            return values

        elif strategy == "first":
            return values[0] if values else None

        elif strategy == "last":
            return values[-1] if values else None

        elif strategy == "merge":
            # Merge dictionaries
            merged = {}
            for v in values:
                if isinstance(v, dict):
                    merged.update(v)
            return merged if merged else values

        elif strategy == "concat":
            # Concatenate strings or arrays
            if all(isinstance(v, str) for v in values if v is not None):
                return "".join(v for v in values if v)

            if all(isinstance(v, list) for v in values if v is not None):
                result = []
                for v in values:
                    if isinstance(v, list):
                        result.extend(v)
                return result

            return values

        # Default to list
        return values