"""Integration tests for solar_insights — same fixture pattern as
test_report_engine.py. Needs a live database."""

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from solgrid_tea.services.solar_insights import (
    generation_vs_consumption_series,
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
