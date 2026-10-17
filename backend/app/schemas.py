from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    n: int = Field(40, ge=5, le=300)
    seed: int = 42


class PlanParams(BaseModel):
    horizon_days: int = Field(14, ge=3, le=30)
    service_days: int = Field(2, ge=1, le=7)
    unplanned_days: int = Field(6, ge=1, le=21)
    bays: Optional[int] = Field(None, ge=0, le=20)
    tech_hours_per_day: Optional[int] = Field(None, ge=0, le=500)
    tech_hours_per_job_day: int = Field(8, ge=1, le=24)
    min_available: Optional[int] = Field(None, ge=0)
    risk_floor: float = Field(0.03, ge=0, le=1)
    shortfall_penalty: float = Field(3.0, ge=0)
    spares_multiplier: float = Field(1.0, ge=0, le=5)


class SimulateRequest(PlanParams):
    policy: Literal["reactive", "planned"] = "planned"
    n_runs: int = Field(200, ge=10, le=2000)
    seed: int = 0


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = ""
    actor: str = "maintenance_officer"
