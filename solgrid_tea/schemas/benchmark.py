from datetime import date
from uuid import UUID

from pydantic import BaseModel, model_validator


class BenchmarkQuery(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class BenchmarkResult(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date
    total_made_tea_kg: float
    total_cost_kes: float
    total_energy_kwh: float
    cost_per_kg_tea_kes: float | None
    kwh_per_kg_tea: float | None
    energy_mix_pct: dict[str, float]
    missing_energy_content_factors: list[str]
