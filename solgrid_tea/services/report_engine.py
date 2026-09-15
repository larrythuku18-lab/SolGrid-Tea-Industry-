"""report_snapshot building — architecture doc §6, and the pre-publish
completeness check from §10.

The completeness check is plain code on purpose (per the build brief: "no
model needed to find a gap in the ledger") — it's just "does this period
have the rows a report needs," not a judgment call.

The placeholder check here enforces a hard constraint from the same
brief: emission_factor and energy_content_factor rows seeded with
"PLACEHOLDER" in their methodology_note (see cli.py's seed-reference-data
command) must never feed a number into a stored report_snapshot — that
row is exactly what a future Conservation Passport bridge would read from,
so refusing has to happen here, at publish time, not at some later export
step. Unlike the completeness/plausibility checks, this one has no
override — see PlaceholderDataError.
"""

from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from solgrid_tea.models import EnergyReading
from solgrid_tea.schemas.report import (
    CompletenessCheckResult,
    ExternalReportPayload,
    PeriodSummary,
    PlaceholderDataError,
    ReportPayload,
)
from solgrid_tea.services.benchmark_engine import compute_benchmark
from solgrid_tea.services.reference_lookup import (
    latest_emission_factor,
    latest_energy_content_factor,
)

REPORT_METHODOLOGY_VERSION = "solgrid-tea-report-v1"

# Emissions are computed only for reading types that have a real physical
# combustion/consumption emission factor. fuelwood is deliberately excluded
# here the same way it's excluded from seed-reference-data: biogenic
# combustion emissions need a deliberate accounting-standard choice
# (biogenic vs. LULUCF-linked) that hasn't been made yet — see cli.py.
# solar_generation has no emissions by definition. When a fuelwood factor
# does get seeded later (e.g. for the thermal-efficiency scenario), this
# loop picks it up automatically; nothing here needs to change.


def _is_placeholder(methodology_note: str) -> bool:
    return "placeholder" in methodology_note.lower()


def check_completeness(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> CompletenessCheckResult:
    benchmark = compute_benchmark(session, facility_id, period_start, period_end)
    gaps = []
    if benchmark.total_made_tea_kg <= 0:
        gaps.append("no production_record fully within this period")
    if benchmark.total_energy_kwh <= 0:
        gaps.append(
            "no energy_reading fully within this period with a known energy-content factor"
        )
    if benchmark.missing_energy_content_factors:
        gaps.append(
            "energy readings present but no energy_content_factor on file for: "
            + ", ".join(benchmark.missing_energy_content_factors)
        )
    return CompletenessCheckResult(passed=len(gaps) == 0, gaps=gaps)


def period_summary(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> PeriodSummary:
    benchmark = compute_benchmark(session, facility_id, period_start, period_end)
    readings = session.scalars(
        select(EnergyReading).where(
            EnergyReading.facility_id == facility_id,
            EnergyReading.period_start >= period_start,
            EnergyReading.period_end <= period_end,
        )
    ).all()

    electricity_kwh = sum(
        float(r.quantity) for r in readings if r.reading_type == "grid_electricity"
    )
    electricity_cost_kes = sum(
        float(r.cost_kes or 0) for r in readings if r.reading_type == "grid_electricity"
    )
    fuelwood_volume_m3 = sum(float(r.quantity) for r in readings if r.reading_type == "fuelwood")
    fuelwood_cost_kes = sum(
        float(r.cost_kes or 0) for r in readings if r.reading_type == "fuelwood"
    )

    return PeriodSummary(
        period_start=period_start,
        period_end=period_end,
        made_tea_kg=benchmark.total_made_tea_kg,
        electricity_kwh=electricity_kwh,
        electricity_cost_kes=electricity_cost_kes,
        fuelwood_volume_m3=fuelwood_volume_m3,
        fuelwood_cost_kes=fuelwood_cost_kes,
        cost_per_kg_kes=benchmark.cost_per_kg_tea_kes,
    )


def trailing_period_summaries(
    session: Session, facility_id: UUID, period_start: date, period_end: date, count: int = 6
) -> list[PeriodSummary]:
    """The `count` periods immediately preceding [period_start, period_end],
    each the same length as it. Only periods with actual production data
    are returned — an empty trailing period tells the plausibility check
    nothing and would just be noise in its input."""
    period_length = (period_end - period_start).days + 1
    summaries = []
    cursor_end = period_start - timedelta(days=1)
    for _ in range(count):
        cursor_start = cursor_end - timedelta(days=period_length - 1)
        summary = period_summary(session, facility_id, cursor_start, cursor_end)
        if summary.made_tea_kg > 0:
            summaries.append(summary)
        cursor_end = cursor_start - timedelta(days=1)
    return summaries


def build_report_payload(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> tuple[ReportPayload, list[str]]:
    """Returns the full internal payload plus the list of PLACEHOLDER-
    flagged reference sources it drew from (empty if none). The caller
    decides what to do with a non-empty list — this function only detects,
    per the module docstring's separation: detection here, refusal in the
    blueprint, so the check is unit-testable without a publish flow around it.
    """
    benchmark = compute_benchmark(session, facility_id, period_start, period_end)
    readings = session.scalars(
        select(EnergyReading).where(
            EnergyReading.facility_id == facility_id,
            EnergyReading.period_start >= period_start,
            EnergyReading.period_end <= period_end,
        )
    ).all()

    emissions_by_type: dict[str, float] = defaultdict(float)
    placeholder_sources: set[str] = set()

    for reading in readings:
        factor = latest_emission_factor(session, reading.reading_type, reading.period_start)
        if factor is None:
            continue
        if _is_placeholder(factor.methodology_note):
            placeholder_sources.add(f"emission_factor:{reading.reading_type}")
        emissions_by_type[reading.reading_type] += (
            float(reading.quantity) * float(factor.kg_co2_per_unit) / 1000
        )

    for reading_type in benchmark.energy_mix_pct:
        factor = latest_energy_content_factor(session, reading_type, period_start)
        if factor is not None and _is_placeholder(factor.methodology_note):
            placeholder_sources.add(f"energy_content_factor:{reading_type}")

    payload = ReportPayload(
        facility_id=facility_id,
        period_start=period_start,
        period_end=period_end,
        total_made_tea_kg=benchmark.total_made_tea_kg,
        total_cost_kes=benchmark.total_cost_kes,
        total_energy_kwh=benchmark.total_energy_kwh,
        cost_per_kg_tea_kes=benchmark.cost_per_kg_tea_kes,
        kwh_per_kg_tea=benchmark.kwh_per_kg_tea,
        energy_mix_pct=benchmark.energy_mix_pct,
        total_emissions_tco2=sum(emissions_by_type.values()),
        emissions_by_type_tco2=dict(emissions_by_type),
    )
    return payload, sorted(placeholder_sources)


def assert_no_placeholder_sources(placeholder_sources: list[str]) -> None:
    if placeholder_sources:
        raise PlaceholderDataError(placeholder_sources)


def external_payload_view(
    internal: ReportPayload, methodology_version: str
) -> ExternalReportPayload:
    """architecture doc §6: no raw KES cost data goes to a brand or
    offtaker by default. Everything not explicitly listed here is dropped,
    not just cost_kes — a brand doesn't need factory-level total_energy_kwh
    or made_tea_kg either, only the mix and the emissions figures."""
    return ExternalReportPayload(
        facility_id=internal.facility_id,
        period_start=internal.period_start,
        period_end=internal.period_end,
        energy_mix_pct=internal.energy_mix_pct,
        total_emissions_tco2=internal.total_emissions_tco2,
        emissions_by_type_tco2=internal.emissions_by_type_tco2,
        methodology_version=methodology_version,
        verification_status=internal.verification_status,
    )


