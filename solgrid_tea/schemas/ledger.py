from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ReadingType = Literal["grid_electricity", "diesel", "fuelwood", "solar_generation"]
SourceChannel = Literal["esp32", "modbus", "oem_api", "manual", "sms"]


class EnergyReadingCreate(BaseModel):
    facility_id: UUID
    reading_type: ReadingType
    period_start: date
    period_end: date
    quantity: float = Field(gt=0)
    unit: str
    cost_kes: float | None = Field(default=None, ge=0)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    source_plantation: str | None = None
    source_channel: SourceChannel = "manual"
    entered_by_phone: str | None = None

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self

    @model_validator(mode="after")
    def _check_fuelwood_only_fields(self):
        if self.reading_type != "fuelwood" and (
            self.moisture_pct is not None or self.source_plantation is not None
        ):
            raise ValueError(
                "moisture_pct and source_plantation only apply to fuelwood readings"
            )
        return self

    @model_validator(mode="after")
    def _check_solar_generation_has_no_cost(self):
        if self.reading_type == "solar_generation" and self.cost_kes is not None:
            raise ValueError("solar_generation readings cannot carry a cost_kes")
        return self


class ProductionRecordCreate(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date
    made_tea_kg: float = Field(gt=0)
    source: str = "manual"

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self
