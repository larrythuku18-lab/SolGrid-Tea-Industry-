"""Solar generation vs. consumption reconciliation, and panel/battery
health insights — built ahead of real hardware per migrations/0002's
docstring, so seeded/demo data has a real read path to land on.

Insight rules are plain code, not a model — deliberately, matching the
rest of this system's "deterministic only" stance (see calculation_engine
and report_engine). They also avoid assuming a capacity factor: the
scenario engine already treats solar_capacity_factor as something with
"no safe platform default — verify for this site" and takes it as a
required operator input rather than guessing. An underperformance insight
here follows the same discipline — it compares a site against its own
trailing history, not against an assumed expected yield nobody has
verified for either factory.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from solgrid_tea.models import EnergyReading, Facility, SolarHealthReading
from solgrid_tea.schemas.solar import (
    GenerationVsConsumptionPoint,
    GenerationVsConsumptionSeries,
    SolarHealthLatest,
    SolarHealthPoint,
    SolarHealthSummary,
    SolarInsight,
)
from solgrid_tea.services.reference_lookup import latest_energy_content_factor

# Below this share of its own trailing-average generation, a period is
# flagged as underperforming — a relative check against the site's own
# history, not an assumed capacity factor (see module docstring).
_UNDERPERFORMANCE_THRESHOLD_PCT = 80.0
_LOW_SOC_WARN_THRESHOLD_PCT = 25.0
_SOH_CRITICAL_THRESHOLD_PCT = 70.0
_SOH_WARN_THRESHOLD_PCT = 85.0
_SOH_FAST_DEGRADATION_DROP_PCT = 3.0
# How far back "recent" means for the low-state-of-charge check — short on
# purpose. Readings arrive roughly daily; averaging that over the whole
# trailing_days window (months) would blur past a real short-term problem.
_RECENT_SOC_WINDOW_DAYS = 14


def generation_vs_consumption_series(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> GenerationVsConsumptionSeries:
    readings = session.scalars(
        select(EnergyReading).where(
            EnergyReading.facility_id == facility_id,
            EnergyReading.period_start >= period_start,
            EnergyReading.period_end <= period_end,
            EnergyReading.reading_type.in_(("solar_generation", "grid_electricity", "diesel")),
        )
    ).all()

    by_period: dict[tuple[date, date], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for reading in readings:
        by_period[(reading.period_start, reading.period_end)][reading.reading_type] += float(
            reading.quantity
        )

    points = []
    for (p_start, p_end), quantities in sorted(by_period.items()):
        generation_kwh = quantities.get("solar_generation", 0.0)
        grid_kwh = quantities.get("grid_electricity", 0.0)
        diesel_litres = quantities.get("diesel", 0.0)

        diesel_factor = latest_energy_content_factor(session, "diesel", p_start)
        diesel_kwh = diesel_litres * float(diesel_factor.kwh_per_unit) if diesel_factor else 0.0

        consumption_kwh = grid_kwh + diesel_kwh + generation_kwh
        self_consumption_pct = (
            generation_kwh / consumption_kwh * 100 if consumption_kwh > 0 else None
        )
        points.append(
            GenerationVsConsumptionPoint(
                period_start=p_start,
                period_end=p_end,
                generation_kwh=generation_kwh,
                consumption_kwh=consumption_kwh,
                self_consumption_pct=self_consumption_pct,
            )
        )

    facility = session.get(Facility, facility_id)
    install_capacity_kw = (
        float(facility.install_capacity_kw)
        if facility is not None and facility.install_capacity_kw is not None
        else None
    )
    return GenerationVsConsumptionSeries(
        facility_id=facility_id, install_capacity_kw=install_capacity_kw, points=points
    )


def _generation_insight(points: list[GenerationVsConsumptionPoint]) -> SolarInsight | None:
    generating_points = [p for p in points if p.generation_kwh > 0]
    if len(generating_points) < 2:
        return None
    *history, latest = generating_points
    trailing_avg = sum(p.generation_kwh for p in history) / len(history)
    if trailing_avg <= 0:
        return None
    pct_of_average = latest.generation_kwh / trailing_avg * 100
    if pct_of_average < _UNDERPERFORMANCE_THRESHOLD_PCT:
        month_label = latest.period_start.strftime("%B %Y")
        return SolarInsight(
            severity="warn",
            message=(
                f"Generation in {month_label} was {pct_of_average:.0f}% of this site's "
                "trailing average — check for shading, panel soiling, or an inverter fault."
            ),
        )
    return None


def _health_insights(
    latest: SolarHealthReading,
    trend_pct: float | None,
    recent_readings: list[SolarHealthReading],
) -> list[SolarInsight]:
    insights: list[SolarInsight] = []

    if latest.battery_status == "fault":
        insights.append(SolarInsight(severity="critical", message="Battery is reporting a fault."))
    elif latest.battery_status == "degraded":
        insights.append(
            SolarInsight(severity="warn", message="Battery health is degraded — inspect soon.")
        )

    if latest.panel_status == "fault":
        insights.append(SolarInsight(severity="critical", message="Panel array is reporting a fault."))
    elif latest.panel_status == "underperforming":
        insights.append(
            SolarInsight(severity="warn", message="Panel array is flagged as underperforming.")
        )

    if latest.battery_soh_pct is not None:
        soh = float(latest.battery_soh_pct)
        if soh < _SOH_CRITICAL_THRESHOLD_PCT:
            insights.append(
                SolarInsight(
                    severity="critical",
                    message=(
                        f"Battery state of health is {soh:.0f}% — capacity is significantly "
                        "degraded; plan for replacement."
                    ),
                )
            )
        elif soh < _SOH_WARN_THRESHOLD_PCT:
            insights.append(
                SolarInsight(
                    severity="warn",
                    message=(
                        f"Battery state of health is {soh:.0f}% — degrading; budget for "
                        "replacement within the next year."
                    ),
                )
            )

    if trend_pct is not None and trend_pct <= -_SOH_FAST_DEGRADATION_DROP_PCT:
        insights.append(
            SolarInsight(
                severity="warn",
                message=(
                    f"Battery state of health dropped {abs(trend_pct):.1f} points over the "
                    "last readings on file — faster than typical degradation, worth inspecting."
                ),
            )
        )

    soc_readings = [
        float(r.battery_soc_pct) for r in recent_readings if r.battery_soc_pct is not None
    ]
    if soc_readings:
        avg_soc = sum(soc_readings) / len(soc_readings)
        if avg_soc < _LOW_SOC_WARN_THRESHOLD_PCT:
            insights.append(
                SolarInsight(
                    severity="warn",
                    message=(
                        f"Battery state of charge has averaged {avg_soc:.0f}% recently — load "
                        "may be exceeding storage capacity."
                    ),
                )
            )

    return insights


def solar_health_summary(
    session: Session,
    facility_id: UUID,
    as_of: date,
    trailing_days: int = 180,
) -> SolarHealthSummary:
    """`trailing_days` is a time window, not a row count — readings arrive
    roughly daily (see seed-solar-demo), so a fixed row LIMIT would silently
    shrink the window whenever the seeding cadence changes. A date range
    keeps the SoH trend meaningful (real months of history) regardless."""
    window_start_ts = datetime.combine(as_of - timedelta(days=trailing_days), time.min, tzinfo=timezone.utc)
    next_day_ts = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)
    readings = list(
        session.scalars(
            select(SolarHealthReading)
            .where(
                SolarHealthReading.facility_id == facility_id,
                SolarHealthReading.ts >= window_start_ts,
                # ts is a timestamptz reading, as_of is a plain date — compare
                # against the start of the *next* day so a same-day reading
                # taken later than midnight (e.g. a noon snapshot) isn't
                # excluded by an implicit midnight cast of as_of.
                SolarHealthReading.ts < next_day_ts,
            )
            .order_by(SolarHealthReading.ts.desc())
        ).all()
    )

    if not readings:
        return SolarHealthSummary(
            facility_id=facility_id, latest=None, battery_soh_trend_pct=None, insights=[]
        )

    latest = readings[0]
    oldest = readings[-1]
    trend_pct = None
    if latest.battery_soh_pct is not None and oldest.battery_soh_pct is not None:
        trend_pct = float(latest.battery_soh_pct) - float(oldest.battery_soh_pct)

    recent_cutoff = latest.ts - timedelta(days=_RECENT_SOC_WINDOW_DAYS)
    recent_readings = [r for r in readings if r.ts >= recent_cutoff]
    insights = _health_insights(latest, trend_pct, recent_readings)

    # Generation-trend insight draws on a wider window than the health
    # readings — a year of monthly ledger periods, not just the last few
    # health pings — so it has enough history to compute a trailing average.
    lookback_start = date(as_of.year - 1, as_of.month, 1)
    series = generation_vs_consumption_series(session, facility_id, lookback_start, as_of)
    generation_insight = _generation_insight(series.points)
    if generation_insight is not None:
        insights.append(generation_insight)

    if not insights:
        insights.append(
            SolarInsight(
                severity="info",
                message=(
                    "Solar system operating normally — generation and battery health are "
                    "within expected ranges based on recent history."
                ),
            )
        )

    return SolarHealthSummary(
        facility_id=facility_id,
        latest=SolarHealthLatest(
            # Kept as the full timestamp, not truncated to a date: the Solar
            # page plots this as the newest point on a chart that a live feed
            # appends to, and a date would collapse a day of readings.
            ts=latest.ts,
            battery_soc_pct=float(latest.battery_soc_pct) if latest.battery_soc_pct is not None else None,
            battery_soh_pct=float(latest.battery_soh_pct) if latest.battery_soh_pct is not None else None,
            panel_status=latest.panel_status,
            battery_status=latest.battery_status,
            panel_temp_c=float(latest.panel_temp_c) if latest.panel_temp_c is not None else None,
            note=latest.note,
        ),
        battery_soh_trend_pct=trend_pct,
        insights=insights,
    )


def solar_health_history(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> list[SolarHealthPoint]:
    """The raw SoC/SoH time series for a chart — as many readings as exist
    in the window (daily, per seed-solar-demo), not reduced to one number
    per month like the ledger-backed generation series."""
    window_start_ts = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    window_end_ts = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    readings = session.scalars(
        select(SolarHealthReading)
        .where(
            SolarHealthReading.facility_id == facility_id,
            SolarHealthReading.ts >= window_start_ts,
            SolarHealthReading.ts < window_end_ts,
        )
        .order_by(SolarHealthReading.ts.asc())
    ).all()
    return [
        SolarHealthPoint(
            ts=r.ts,
            battery_soc_pct=float(r.battery_soc_pct) if r.battery_soc_pct is not None else None,
            battery_soh_pct=float(r.battery_soh_pct) if r.battery_soh_pct is not None else None,
        )
        for r in readings
    ]
