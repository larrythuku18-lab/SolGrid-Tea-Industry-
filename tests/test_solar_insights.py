"""Integration tests for solar_insights — same fixture pattern as
test_report_engine.py. Needs a live database."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from solgrid_tea.services.solar_insights import (
    generation_vs_consumption_series,
    solar_health_history,
    solar_health_summary,
)

pytestmark = pytest.mark.db


@pytest.fixture()
def facility(db_session):
    org_id = uuid.uuid4()
    db_session.execute(
        text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
    )
    db_session.execute(
        text("INSERT INTO organization (id, name) VALUES (:id, 'Solar Test Co')"),
        {"id": str(org_id)},
    )
    facility_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO facility (id, organization_id, name, install_capacity_kw) "
            "VALUES (:id, :org_id, 'Test Facility', 100)"
        ),
        {"id": str(facility_id), "org_id": str(org_id)},
    )
    return facility_id


def _seed_energy_content_factors(session):
    session.execute(
        text(
            "INSERT INTO energy_content_factor "
            "(fuel_type, kwh_per_unit, unit, effective_from, methodology_note) VALUES "
            "('diesel', 10.72, 'litre', '2026-01-01', 'test factor')"
        )
    )


def _add_energy_reading(session, facility_id, reading_type, period_start, period_end, quantity):
    session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, source_channel) "
            "VALUES (:f, :rt, :ps, :pe, :q, 'kWh', 'manual')"
        ),
        {"f": str(facility_id), "rt": reading_type, "ps": period_start, "pe": period_end, "q": quantity},
    )


def _add_irradiance(session, facility_id, day, ghi_kwh_per_m2, source="test"):
    session.execute(
        text(
            "INSERT INTO solar_irradiance_daily (facility_id, day, ghi_kwh_per_m2, source) "
            "VALUES (:f, :day, :ghi, :source)"
        ),
        {"f": str(facility_id), "day": day, "ghi": ghi_kwh_per_m2, "source": source},
    )


def _add_health_reading(session, facility_id, ts, **overrides):
    fields = {
        "battery_soc_pct": 60.0,
        "battery_soh_pct": 95.0,
        "panel_status": "normal",
        "battery_status": "normal",
        "panel_temp_c": 38.0,
        "source_channel": "seed",
    }
    fields.update(overrides)
    session.execute(
        text(
            "INSERT INTO solar_health_reading "
            "(facility_id, ts, battery_soc_pct, battery_soh_pct, panel_status, battery_status, "
            "panel_temp_c, source_channel) "
            "VALUES (:f, :ts, :soc, :soh, :ps, :bs, :temp, :sc)"
        ),
        {
            "f": str(facility_id),
            "ts": ts,
            "soc": fields["battery_soc_pct"],
            "soh": fields["battery_soh_pct"],
            "ps": fields["panel_status"],
            "bs": fields["battery_status"],
            "temp": fields["panel_temp_c"],
            "sc": fields["source_channel"],
        },
    )


def test_generation_vs_consumption_reconciles_grid_diesel_solar(db_session, facility):
    _seed_energy_content_factors(db_session)
    _add_energy_reading(
        db_session, facility, "grid_electricity", date(2026, 1, 1), date(2026, 1, 31), 10000
    )
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 1, 1), date(2026, 1, 31), 2000
    )

    series = generation_vs_consumption_series(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))

    assert series.install_capacity_kw == 100.0
    assert len(series.points) == 1
    point = series.points[0]
    assert point.generation_kwh == 2000
    assert point.consumption_kwh == 12000  # grid + solar, no diesel this period
    assert point.self_consumption_pct == pytest.approx(2000 / 12000 * 100)


def test_no_readings_in_range_returns_empty_points(db_session, facility):
    series = generation_vs_consumption_series(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))
    assert series.points == []


def test_health_summary_with_no_readings_is_empty(db_session, facility):
    summary = solar_health_summary(db_session, facility, date(2026, 8, 31))
    assert summary.latest is None
    assert summary.battery_soh_trend_pct is None
    assert summary.insights == []


def test_health_summary_falls_back_to_operating_normally(db_session, facility):
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 31, 12, tzinfo=timezone.utc), battery_soh_pct=95.0
    )
    summary = solar_health_summary(db_session, facility, date(2026, 8, 31))
    assert len(summary.insights) == 1
    assert summary.insights[0].severity == "info"


def test_health_summary_flags_low_state_of_health(db_session, facility):
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 31, 12, tzinfo=timezone.utc), battery_soh_pct=65.0
    )
    summary = solar_health_summary(db_session, facility, date(2026, 8, 31))
    assert any(i.severity == "critical" and "state of health" in i.message for i in summary.insights)


def test_health_summary_flags_fault_status(db_session, facility):
    _add_health_reading(
        db_session,
        facility,
        datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
        panel_status="fault",
        battery_soh_pct=95.0,
    )
    summary = solar_health_summary(db_session, facility, date(2026, 8, 31))
    assert any(i.severity == "critical" and "Panel array" in i.message for i in summary.insights)


def test_health_summary_flags_generation_well_below_trailing_average(db_session, facility):
    _seed_energy_content_factors(db_session)
    for month in (5, 6, 7):
        _add_energy_reading(
            db_session,
            facility,
            "solar_generation",
            date(2026, month, 1),
            date(2026, month, 28),
            10000,
        )
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 8, 1), date(2026, 8, 28), 4000
    )
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 28, 12, tzinfo=timezone.utc), battery_soh_pct=95.0
    )

    summary = solar_health_summary(db_session, facility, date(2026, 8, 28))

    assert any("trailing average" in i.message for i in summary.insights)


def test_health_history_returns_points_ascending(db_session, facility):
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 3, 15, tzinfo=timezone.utc), battery_soc_pct=40.0
    )
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 1, 15, tzinfo=timezone.utc), battery_soc_pct=60.0
    )
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 2, 15, tzinfo=timezone.utc), battery_soc_pct=50.0
    )

    points = solar_health_history(db_session, facility, date(2026, 8, 1), date(2026, 8, 31))

    assert [p.battery_soc_pct for p in points] == [60.0, 50.0, 40.0]
    # Full timestamps, not dates — the chart a live feed appends to needs to
    # place two readings taken on the same day at different x positions.
    assert [p.ts for p in points] == [
        datetime(2026, 8, 1, 15, tzinfo=timezone.utc),
        datetime(2026, 8, 2, 15, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 15, tzinfo=timezone.utc),
    ]


def test_health_summary_trend_spans_the_full_time_window(db_session, facility):
    # 10 daily readings, declining SoH — a row-count-based window (the old
    # trailing_count=6 behavior) would only see the last 6 and understate
    # the drop. trailing_days is date-based, so it should see all 10.
    for day in range(1, 11):
        _add_health_reading(
            db_session,
            facility,
            datetime(2026, 8, day, 15, tzinfo=timezone.utc),
            battery_soh_pct=100.0 - day,  # 99.0 .. 90.0
        )

    summary = solar_health_summary(db_session, facility, date(2026, 8, 10), trailing_days=30)

    assert summary.battery_soh_trend_pct == pytest.approx(90.0 - 99.0)


def test_low_soc_insight_ignores_readings_outside_recent_window(db_session, facility):
    # An old low-SoC reading, well outside the ~14-day "recent" window the
    # low-SoC check uses, plus healthy recent readings. Averaging the whole
    # trailing_days window would wrongly drag in the old low reading.
    _add_health_reading(
        db_session,
        facility,
        datetime(2026, 6, 1, 15, tzinfo=timezone.utc),
        battery_soc_pct=5.0,
        battery_soh_pct=95.0,
    )
    for day in range(1, 6):
        _add_health_reading(
            db_session,
            facility,
            datetime(2026, 8, day, 15, tzinfo=timezone.utc),
            battery_soc_pct=70.0,
            battery_soh_pct=95.0,
        )

    summary = solar_health_summary(db_session, facility, date(2026, 8, 5))

    assert not any("running low" in i.message.lower() or "load may be" in i.message for i in summary.insights)


def test_series_computes_expected_generation_from_cached_irradiance(db_session, facility):
    for offset in range(31):
        _add_irradiance(db_session, facility, date(2026, 8, 1) + timedelta(days=offset), 5.0)
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 8, 1), date(2026, 8, 31), 5000
    )

    series = generation_vs_consumption_series(db_session, facility, date(2026, 8, 1), date(2026, 8, 31))

    assert len(series.points) == 1
    # install_capacity_kw (100, from the fixture) x total GHI (31 x 5.0) x
    # the 0.78 performance ratio.
    assert series.points[0].expected_generation_kwh == pytest.approx(100 * (31 * 5.0) * 0.78)


def test_expected_generation_is_none_below_the_coverage_threshold(db_session, facility):
    # Only 10 of 31 days cached — well under the 90% coverage floor, so the
    # sum would understate a full month's expected yield if used anyway.
    for offset in range(10):
        _add_irradiance(db_session, facility, date(2026, 8, 1) + timedelta(days=offset), 5.0)
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 8, 1), date(2026, 8, 31), 5000
    )

    series = generation_vs_consumption_series(db_session, facility, date(2026, 8, 1), date(2026, 8, 31))

    assert series.points[0].expected_generation_kwh is None


def test_health_summary_flags_weather_adjusted_underperformance(db_session, facility):
    for offset in range(31):
        _add_irradiance(db_session, facility, date(2026, 8, 1) + timedelta(days=offset), 5.0)
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 8, 1), date(2026, 8, 31), 5000
    )
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 31, 15, tzinfo=timezone.utc), battery_soh_pct=95.0
    )

    summary = solar_health_summary(db_session, facility, date(2026, 8, 31))

    assert any("what recorded irradiance" in i.message for i in summary.insights)


def test_weather_adjusted_check_avoids_a_false_positive_the_fallback_would_raise(db_session, facility):
    # June was sunny and generated a lot; August was genuinely cloudy and
    # generated much less — normal, not a fault. The self-relative fallback
    # (comparing August against June's trailing average) would misread this
    # as an 80%+ drop and wrongly flag it. Weather-adjustment should compare
    # August's actual output against what August's own (lower) irradiance
    # predicts instead, and find nothing wrong.
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 6, 1), date(2026, 6, 30), 10000
    )
    for offset in range(31):
        _add_irradiance(db_session, facility, date(2026, 8, 1) + timedelta(days=offset), 1.7)
    _add_energy_reading(
        db_session, facility, "solar_generation", date(2026, 8, 1), date(2026, 8, 31), 4000
    )
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 31, 15, tzinfo=timezone.utc), battery_soh_pct=95.0
    )

    summary = solar_health_summary(db_session, facility, date(2026, 8, 31))

    assert not any(
        "irradiance" in i.message or "trailing average" in i.message for i in summary.insights
    )
    assert any(i.severity == "info" for i in summary.insights)
