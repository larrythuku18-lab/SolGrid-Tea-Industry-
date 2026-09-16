from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

PanelStatus = Literal["normal", "underperforming", "fault"]
BatteryStatus = Literal["normal", "degraded", "fault"]
InsightSeverity = Literal["info", "warn", "critical"]


class SolarQuery(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class SolarHealthQuery(BaseModel):
    facility_id: UUID
    as_of: date | None = None


class GenerationVsConsumptionPoint(BaseModel):
    period_start: date
    period_end: date
    generation_kwh: float
    consumption_kwh: float  # grid + diesel(kWh-equiv) + solar_generation — total electrical load
    self_consumption_pct: float | None  # share of consumption covered by solar, None if consumption is 0


class GenerationVsConsumptionSeries(BaseModel):
    facility_id: UUID
    install_capacity_kw: float | None
    points: list[GenerationVsConsumptionPoint]


class SolarHealthLatest(BaseModel):
    ts: date
    battery_soc_pct: float | None
    battery_soh_pct: float | None
    panel_status: PanelStatus
    battery_status: BatteryStatus
    panel_temp_c: float | None
    note: str | None


class SolarInsight(BaseModel):
    severity: InsightSeverity
    message: str


class SolarHealthSummary(BaseModel):
    facility_id: UUID
    latest: SolarHealthLatest | None
    battery_soh_trend_pct: float | None  # change over the trailing window, negative = degrading
    insights: list[SolarInsight]
