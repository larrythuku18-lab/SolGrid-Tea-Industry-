from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ScenarioInput(BaseModel):
    facility_id: UUID
    financing_mode: Literal["ppa", "capex"]
    target_solar_kw: float = Field(gt=0)
    grid_tariff_kes_per_kwh: float = Field(gt=0)
    ppa_rate_kes_per_kwh: float | None = Field(default=None, gt=0)
    capex_kes: float | None = Field(default=None, gt=0)
    daytime_coincidence_factor: float = Field(default=0.50, ge=0, le=1)

    # Not in the original architecture doc's ScenarioInput, but the seven
    # formulas in §5 can't be computed without them, and principle §0.2
    # ("deterministic, not ML... trace every number to an input") rules out
    # burying a regional assumption as a hardcoded constant in the engine.
    # Required, no silent default, so a caller can't get a number back
    # without knowing exactly what assumption produced it.
    solar_capacity_factor: float = Field(
        gt=0, le=0.35, description="Fraction of nameplate kW realized as average output over a year"
    )
    baseline_annual_grid_kwh: float = Field(gt=0)
    baseline_annual_electrical_kwh: float = Field(
        gt=0, description="All electrical demand, grid + any electrical diesel backup"
    )
    baseline_annual_total_energy_kwh: float = Field(
        gt=0, description="Electrical + thermal (fuelwood etc.), kWh-equivalent"
    )

    @model_validator(mode="after")
    def _check_financing_fields(self):
        if self.financing_mode == "ppa" and self.ppa_rate_kes_per_kwh is None:
            raise ValueError("ppa_rate_kes_per_kwh is required when financing_mode is 'ppa'")
        if self.financing_mode == "capex" and self.capex_kes is None:
            raise ValueError("capex_kes is required when financing_mode is 'capex'")
        return self

    @model_validator(mode="after")
    def _check_energy_hierarchy(self):
        if self.baseline_annual_electrical_kwh < self.baseline_annual_grid_kwh:
            raise ValueError(
                "baseline_annual_electrical_kwh cannot be less than baseline_annual_grid_kwh"
            )
        if self.baseline_annual_total_energy_kwh < self.baseline_annual_electrical_kwh:
            raise ValueError(
                "baseline_annual_total_energy_kwh cannot be less than "
                "baseline_annual_electrical_kwh"
            )
        return self


class ScenarioResult(BaseModel):
    solar_annual_generation_kwh: float
    addressable_kwh: float
    addressable_electrical_share_pct: float
    addressable_of_total_energy_pct: float
    annual_savings_kes: float
    payback_years: float | None
    emissions_avoided_grid_tco2: float
    emissions_avoided_fuelwood_tco2: float
    fuelwood_reduction_m3: float
    # The exact emission_factor row used, not a free-text version tag — a
    # UUID is the only fully unambiguous pointer back to the reference data
    # that produced emissions_avoided_grid_tco2 (rows are immutable; a
    # correction is a new row with a later effective_from, never an update).
    grid_emission_factor_id: UUID
    grid_emission_factor_methodology_note: str
