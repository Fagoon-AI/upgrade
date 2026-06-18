"""
Workflow Schedule Model.

Stores schedule configurations for automated workflow execution.
Supports cron expressions, interval-based schedules, and one-time triggers.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import DateTime, String, Index, Integer, text, Boolean, Enum as SAEnum
from croniter import croniter

if TYPE_CHECKING:
    from src.models.sql.workflow.user import User
    from src.models.sql.workflow.workflow import Workflow


class ScheduleType(str, Enum):
    """Type of schedule."""
    CRON = "CRON"           # Cron expression (e.g., "0 9 * * *")
    INTERVAL = "INTERVAL"   # Interval in seconds (e.g., every 300 seconds)
    ONCE = "ONCE"           # One-time execution at specific time


class ScheduleStatus(str, Enum):
    """Schedule lifecycle status."""
    ACTIVE = "ACTIVE"       # Schedule is active and will trigger
    PAUSED = "PAUSED"       # Temporarily paused
    DISABLED = "DISABLED"   # Permanently disabled
    COMPLETED = "COMPLETED" # One-time schedule that has executed


class WorkflowSchedule(SQLModel, table=True):
    """
    Workflow Schedule Model.

    Features:
    - UUID primary key
    - Cron, interval, or one-time scheduling
    - Timezone support
    - Execution tracking
    - Input data for scheduled runs
    - Status management

    Indexes:
    - Primary key on id
    - Foreign key indexes on user_id and workflow_id
    - Index on next_run_at for efficient scheduler queries
    - Index on status for filtering
    """

    __tablename__ = "workflow_schedule"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique schedule identifier"
    )

    # Ownership
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        index=True,
        description="Owner user ID"
    )

    workflow_id: uuid.UUID = Field(
        foreign_key="workflow.id",
        index=True,
        description="Workflow to execute"
    )

    # Schedule configuration
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Schedule name"
    )

    description: Optional[str] = Field(
        default=None,
        sa_column=Column(String(1000)),
        description="Schedule description"
    )

    schedule_type: ScheduleType = Field(
        sa_column=Column(
            SAEnum(ScheduleType, name="scheduletype", create_type=False),
            nullable=False,
            default=ScheduleType.CRON
        ),
        description="Type of schedule (CRON, INTERVAL, ONCE)"
    )

    # Cron configuration
    cron_expression: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
        description="Cron expression (for CRON type)"
    )

    # Interval configuration
    interval_seconds: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer),
        description="Interval in seconds (for INTERVAL type)"
    )

    # One-time configuration
    run_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Specific run time (for ONCE type)"
    )

    # Timezone
    timezone: str = Field(
        default="UTC",
        sa_column=Column(String(50), nullable=False, default="UTC"),
        description="Timezone for schedule (e.g., America/New_York)"
    )

    # Status
    status: ScheduleStatus = Field(
        default=ScheduleStatus.ACTIVE,
        sa_column=Column(
            SAEnum(ScheduleStatus, name="schedulestatus", create_type=False),
            nullable=False,
            default=ScheduleStatus.ACTIVE,
            index=True
        ),
        description="Schedule status"
    )

    # Execution tracking
    next_run_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), index=True),
        description="Next scheduled execution time"
    )

    last_run_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last execution time"
    )

    last_execution_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Last execution ID"
    )

    run_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
        description="Total number of executions"
    )

    error_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
        description="Number of failed executions"
    )

    consecutive_errors: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
        description="Consecutive error count (resets on success)"
    )

    # Input data for scheduled runs
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Input data passed to workflow on each run"
    )

    # Limits
    max_consecutive_errors: int = Field(
        default=5,
        sa_column=Column(Integer, nullable=False, default=5),
        description="Auto-pause after this many consecutive errors"
    )

    # Audit timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Creation timestamp"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=lambda: datetime.now(timezone.utc)
        ),
        description="Last update timestamp"
    )

    # Relationships
    user: "User" = Relationship(back_populates="schedules")
    workflow: "Workflow" = Relationship(back_populates="schedules")

    # Table configuration
    __table_args__ = (
        Index("ix_schedule_user_status", "user_id", "status"),
        Index("ix_schedule_workflow_status", "workflow_id", "status"),
        Index("ix_schedule_next_run_active", "next_run_at", "status"),
    )

    # ============================================================
    # METHODS
    # ============================================================

    def calculate_next_run(self) -> Optional[datetime]:
        """
        Calculates the next run time based on schedule configuration.

        Returns:
            Next run datetime in UTC, or None if no next run
        """
        now = datetime.now(timezone.utc)

        if self.schedule_type == ScheduleType.CRON:
            if not self.cron_expression:
                return None
            try:
                cron = croniter(self.cron_expression, now)
                return cron.get_next(datetime)
            except Exception:
                return None

        elif self.schedule_type == ScheduleType.INTERVAL:
            if not self.interval_seconds:
                return None
            base = self.last_run_at or now
            return base + timedelta(seconds=self.interval_seconds)

        elif self.schedule_type == ScheduleType.ONCE:
            if self.run_count > 0:
                return None  # Already executed
            return self.run_at

        return None

    def update_next_run(self) -> None:
        """Updates the next_run_at field based on schedule configuration."""
        self.next_run_at = self.calculate_next_run()
        self.updated_at = datetime.now(timezone.utc)

    def record_execution(
            self,
            execution_id: uuid.UUID,
            success: bool = True
    ) -> None:
        """
        Records an execution result.

        Args:
            execution_id: The execution UUID
            success: Whether execution was successful
        """
        now = datetime.now(timezone.utc)

        self.last_run_at = now
        self.last_execution_id = execution_id
        self.run_count += 1
        self.updated_at = now

        if success:
            self.consecutive_errors = 0
        else:
            self.error_count += 1
            self.consecutive_errors += 1

            # Auto-pause on too many consecutive errors
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.status = ScheduleStatus.PAUSED

        # Mark one-time schedules as completed
        if self.schedule_type == ScheduleType.ONCE:
            self.status = ScheduleStatus.COMPLETED

        # Calculate next run
        self.update_next_run()

    def is_due(self) -> bool:
        """Checks if schedule is due for execution."""
        if self.status != ScheduleStatus.ACTIVE:
            return False

        if not self.next_run_at:
            return False

        return datetime.now(timezone.utc) >= self.next_run_at

    def pause(self) -> None:
        """Pauses the schedule."""
        self.status = ScheduleStatus.PAUSED
        self.updated_at = datetime.now(timezone.utc)

    def resume(self) -> None:
        """Resumes a paused schedule."""
        if self.status == ScheduleStatus.PAUSED:
            self.status = ScheduleStatus.ACTIVE
            self.consecutive_errors = 0
            self.update_next_run()
            self.updated_at = datetime.now(timezone.utc)

    def disable(self) -> None:
        """Permanently disables the schedule."""
        self.status = ScheduleStatus.DISABLED
        self.next_run_at = None
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Converts schedule to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "workflow_id": str(self.workflow_id),
            "name": self.name,
            "description": self.description,
            "schedule_type": self.schedule_type.value,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "timezone": self.timezone,
            "status": self.status.value,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_execution_id": str(self.last_execution_id) if self.last_execution_id else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "consecutive_errors": self.consecutive_errors,
            "input_data": self.input_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def validate_cron_expression(cls, expression: str) -> bool:
        """Validates a cron expression."""
        try:
            croniter(expression)
            return True
        except Exception:
            return False

    def get_human_readable_schedule(self) -> str:
        """Returns a human-readable description of the schedule."""
        if self.schedule_type == ScheduleType.CRON:
            return f"Cron: {self.cron_expression}"
        elif self.schedule_type == ScheduleType.INTERVAL:
            if self.interval_seconds < 60:
                return f"Every {self.interval_seconds} seconds"
            elif self.interval_seconds < 3600:
                minutes = self.interval_seconds // 60
                return f"Every {minutes} minute{'s' if minutes > 1 else ''}"
            else:
                hours = self.interval_seconds // 3600
                return f"Every {hours} hour{'s' if hours > 1 else ''}"
        elif self.schedule_type == ScheduleType.ONCE:
            if self.run_at:
                return f"Once at {self.run_at.isoformat()}"
            return "One-time (not scheduled)"
        return "Unknown schedule"

    def __repr__(self) -> str:
        return f"<WorkflowSchedule {self.name} ({self.status.value})>"

    def __str__(self) -> str:
        return f"{self.name} - {self.get_human_readable_schedule()}"
