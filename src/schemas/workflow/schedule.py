"""
Pydantic schemas for Workflow Schedule API.

Provides request/response validation for schedule management endpoints.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from croniter import croniter

from src.models.sql.workflow.schedule import ScheduleType, ScheduleStatus


# ============================================================
# CONFIGURATION
# ============================================================

MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 1000
MIN_INTERVAL_SECONDS = 60  # 1 minute minimum
MAX_INTERVAL_SECONDS = 31536000  # 1 year maximum


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class ScheduleCreate(BaseModel):
    """Schema for creating a schedule."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_NAME_LENGTH,
        description="Schedule name"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Schedule description"
    )
    workflow_id: UUID = Field(
        ...,
        description="ID of the workflow to schedule"
    )
    schedule_type: ScheduleType = Field(
        ...,
        description="Type of schedule: CRON, INTERVAL, or ONCE"
    )
    cron_expression: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Cron expression (required for CRON type)"
    )
    interval_seconds: Optional[int] = Field(
        default=None,
        ge=MIN_INTERVAL_SECONDS,
        le=MAX_INTERVAL_SECONDS,
        description="Interval in seconds (required for INTERVAL type)"
    )
    run_at: Optional[datetime] = Field(
        default=None,
        description="Specific run time in UTC (required for ONCE type)"
    )
    timezone: str = Field(
        default="UTC",
        max_length=50,
        description="Timezone for schedule (e.g., America/New_York)"
    )
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input data to pass to workflow on each run"
    )
    max_consecutive_errors: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Auto-pause after this many consecutive errors"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validates and sanitizes schedule name."""
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: Optional[str]) -> Optional[str]:
        """Validates cron expression syntax."""
        if v is None:
            return None
        v = v.strip()
        try:
            croniter(v)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid cron expression: {e}")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validates timezone string."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {v}")
        return v

    @model_validator(mode="after")
    def validate_schedule_config(self) -> "ScheduleCreate":
        """Validates schedule configuration based on type."""
        if self.schedule_type == ScheduleType.CRON:
            if not self.cron_expression:
                raise ValueError("cron_expression is required for CRON schedule type")
        elif self.schedule_type == ScheduleType.INTERVAL:
            if not self.interval_seconds:
                raise ValueError("interval_seconds is required for INTERVAL schedule type")
        elif self.schedule_type == ScheduleType.ONCE:
            if not self.run_at:
                raise ValueError("run_at is required for ONCE schedule type")
            if self.run_at <= datetime.utcnow():
                raise ValueError("run_at must be in the future")
        return self


class ScheduleUpdate(BaseModel):
    """Schema for updating a schedule."""
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=MAX_NAME_LENGTH,
        description="Schedule name"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Schedule description"
    )
    cron_expression: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Cron expression (for CRON type)"
    )
    interval_seconds: Optional[int] = Field(
        default=None,
        ge=MIN_INTERVAL_SECONDS,
        le=MAX_INTERVAL_SECONDS,
        description="Interval in seconds (for INTERVAL type)"
    )
    run_at: Optional[datetime] = Field(
        default=None,
        description="Specific run time in UTC (for ONCE type)"
    )
    timezone: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Timezone for schedule"
    )
    input_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Input data to pass to workflow"
    )
    max_consecutive_errors: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Auto-pause threshold"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validates and sanitizes schedule name."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        v = re.sub(r'[<>{}[\]\\]', '', v)
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: Optional[str]) -> Optional[str]:
        """Validates cron expression syntax."""
        if v is None:
            return None
        v = v.strip()
        try:
            croniter(v)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid cron expression: {e}")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        """Validates timezone string."""
        if v is None:
            return None
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {v}")
        return v


class SchedulePause(BaseModel):
    """Schema for pause/resume actions."""
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Reason for pausing/resuming"
    )


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class ScheduleResponse(BaseModel):
    """Schema for schedule API response."""
    id: UUID
    user_id: UUID
    workflow_id: UUID
    name: str
    description: Optional[str]
    schedule_type: ScheduleType
    cron_expression: Optional[str]
    interval_seconds: Optional[int]
    run_at: Optional[datetime]
    timezone: str
    status: ScheduleStatus
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    last_execution_id: Optional[UUID]
    run_count: int
    error_count: int
    consecutive_errors: int
    input_data: Dict[str, Any]
    max_consecutive_errors: int
    human_readable_schedule: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_schedule(cls, schedule) -> "ScheduleResponse":
        """Creates response from schedule model."""
        return cls(
            id=schedule.id,
            user_id=schedule.user_id,
            workflow_id=schedule.workflow_id,
            name=schedule.name,
            description=schedule.description,
            schedule_type=schedule.schedule_type,
            cron_expression=schedule.cron_expression,
            interval_seconds=schedule.interval_seconds,
            run_at=schedule.run_at,
            timezone=schedule.timezone,
            status=schedule.status,
            next_run_at=schedule.next_run_at,
            last_run_at=schedule.last_run_at,
            last_execution_id=schedule.last_execution_id,
            run_count=schedule.run_count,
            error_count=schedule.error_count,
            consecutive_errors=schedule.consecutive_errors,
            input_data=schedule.input_data or {},
            max_consecutive_errors=schedule.max_consecutive_errors,
            human_readable_schedule=schedule.get_human_readable_schedule(),
            created_at=schedule.created_at,
            updated_at=schedule.updated_at
        )


class ScheduleListResponse(BaseModel):
    """Schema for schedule list item (lighter response)."""
    id: UUID
    workflow_id: UUID
    name: str
    description: Optional[str]
    schedule_type: ScheduleType
    status: ScheduleStatus
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    run_count: int
    human_readable_schedule: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_schedule(cls, schedule) -> "ScheduleListResponse":
        """Creates list response from schedule model."""
        return cls(
            id=schedule.id,
            workflow_id=schedule.workflow_id,
            name=schedule.name,
            description=schedule.description,
            schedule_type=schedule.schedule_type,
            status=schedule.status,
            next_run_at=schedule.next_run_at,
            last_run_at=schedule.last_run_at,
            run_count=schedule.run_count,
            human_readable_schedule=schedule.get_human_readable_schedule(),
            created_at=schedule.created_at
        )


class ScheduleStatsResponse(BaseModel):
    """Schema for schedule statistics."""
    total_schedules: int
    active_schedules: int
    paused_schedules: int
    total_runs: int
    total_errors: int
    success_rate: float
