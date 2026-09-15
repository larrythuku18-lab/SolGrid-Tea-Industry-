"""Cost/kg and energy-mix benchmarking — architecture doc §9 step 2, the
layer meant to be sellable and demoable before any scenario modeling exists.

Only energy_reading and production_record rows fully contained within the
requested [period_start, period_end] window are counted. A reading that
partially overlaps the window is excluded rather than pro-rated — pro-rating
would silently blend data from outside the requested period into the
answer, which is exactly the kind of unauditable number principle §0.2
rules out. Callers who want a full year should ask for a full year.
"""

from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from solgrid_tea.models import EnergyReading, ProductionRecord
from solgrid_tea.schemas.benchmark import BenchmarkResult
from solgrid_tea.services.reference_lookup import latest_energy_content_factor


def compute_benchmark(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> BenchmarkResult:
    readings = session.scalars(
        select(EnergyReading).where(
            EnergyReading.facility_id == facility_id,
            EnergyReading.period_start >= period_start,
            EnergyReading.period_end <= period_end,
        )
    ).all()

    production = session.scalars(
        select(ProductionRecord).where(
            ProductionRecord.facility_id == facility_id,
            ProductionRecord.period_start >= period_start,
            ProductionRecord.period_end <= period_end,
        )
    ).all()

    total_made_tea_kg = float(sum(p.made_tea_kg for p in production))
    total_cost_kes = float(sum(r.cost_kes for r in readings if r.cost_kes is not None))

    kwh_by_type: dict[str, float] = defaultdict(float)
    missing_factor_types: set[str] = set()

    for reading in readings:
        factor = latest_energy_content_factor(session, reading.reading_type, reading.period_start)
        if factor is None:
            missing_factor_types.add(reading.reading_type)
            continue
        kwh_by_type[reading.reading_type] += float(reading.quantity) * float(factor.kwh_per_unit)

    total_energy_kwh = sum(kwh_by_type.values())

    energy_mix_pct = (
        {rtype: kwh / total_energy_kwh * 100 for rtype, kwh in kwh_by_type.items()}
        if total_energy_kwh > 0
        else {}
    )

    return BenchmarkResult(
        facility_id=facility_id,
        period_start=period_start,
        period_end=period_end,
        total_made_tea_kg=total_made_tea_kg,
        total_cost_kes=total_cost_kes,
        total_energy_kwh=total_energy_kwh,
        cost_per_kg_tea_kes=(total_cost_kes / total_made_tea_kg) if total_made_tea_kg > 0 else None,
        kwh_per_kg_tea=(total_energy_kwh / total_made_tea_kg) if total_made_tea_kg > 0 else None,
        energy_mix_pct=energy_mix_pct,
        missing_energy_content_factors=sorted(missing_factor_types),
    )
