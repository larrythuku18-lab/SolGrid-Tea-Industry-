from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator


class PublishReportRequest(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date
    # Required only if the completeness or plausibility check fails —
    # enforced in the blueprint, not here, since that depends on check
    # results this schema doesn't have.
    override_reason: str | None = None

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class CompletenessCheckResult(BaseModel):
    passed: bool
    gaps: list[str]


class PeriodSummary(BaseModel):
    period_start: date
    period_end: date
    made_tea_kg: float
    electricity_kwh: float
    electricity_cost_kes: float
    fuelwood_volume_m3: float
    fuelwood_cost_kes: float
    cost_per_kg_kes: float | None


class PlausibilityCheckResult(BaseModel):
    flagged: bool
    note: str | None
    # True when the check didn't run at all (e.g. no trailing history to
    # compare against yet) — flagged=False in that case means "not
    # evaluated," not "evaluated and clean." See report_engine's module
    # docstring: this system has no real multi-period history yet.
    skipped: bool = False


class ReportPayload(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date
    total_made_tea_kg: float
    total_cost_kes: float
    total_energy_kwh: float
    cost_per_kg_tea_kes: float | None
    kwh_per_kg_tea: float | None
    energy_mix_pct: dict[str, float]
    total_emissions_tco2: float
    emissions_by_type_tco2: dict[str, float]
    # Only value in use for now — there's no independent verification
    # workflow built yet. Present so the field exists where architecture
    # doc §6 says it must ("verification status"), without overclaiming a
    # review process that doesn't exist.
    verification_status: Literal["self_reported"] = "self_reported"


# architecture doc §6: external payload is a curated subset — no raw KES
# cost data. Everything here must already appear in ReportPayload; this
# type exists so the redaction is enforced by the type checker, not by
# convention at each call site that happens to remember to drop a field.
class ExternalReportPayload(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date
    energy_mix_pct: dict[str, float]
    total_emissions_tco2: float
    emissions_by_type_tco2: dict[str, float]
    methodology_version: str
    verification_status: Literal["self_reported"]


class PublishedReportSnapshot(BaseModel):
    id: UUID
    facility_id: UUID
    period_start: date
    period_end: date
    published_at: str
    methodology_version: str
    superseded_by: UUID | None
    completeness: CompletenessCheckResult
    plausibility: PlausibilityCheckResult
    override_reason: str | None
    report: ReportPayload | ExternalReportPayload
    tier: Literal["internal", "external"]


class PlaceholderDataError(Exception):
    """Raised when publishing would carry a PLACEHOLDER-flagged reference
    figure into a stored snapshot. Never overridable — see the hard
    constraint this enforces in SolGrid-Tea-Next-Build-Prompt."""

    def __init__(self, flagged_sources: list[str]):
        self.flagged_sources = flagged_sources
        super().__init__(
            "cannot publish: figures derived from PLACEHOLDER reference data "
            f"({', '.join(flagged_sources)}) — replace with sourced data first"
        )
