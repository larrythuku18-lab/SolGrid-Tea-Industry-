"""Integration test for the benchmark engine — needs real energy_reading /
production_record / energy_content_factor rows, hence a live database.
See test_rls_isolation.py for the fixture/skip behavior.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from solgrid_tea.services.benchmark_engine import compute_benchmark

pytestmark = pytest.mark.db


@pytest.fixture()
def facility(db_session):
    org_id = uuid.uuid4()
    # SET LOCAL doesn't accept bind parameters; set_config() does.
    db_session.execute(text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)})
    db_session.execute(
        text("INSERT INTO organization (id, name) VALUES (:id, 'Kipchabo Test')"),
        {"id": str(org_id)},
    )
    facility_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO facility (id, organization_id, name) VALUES (:id, :org_id, 'Kipchabo')"),
        {"id": str(facility_id), "org_id": str(org_id)},
    )
    return facility_id


def _seed_energy_content_factors(session):
    session.execute(
        text(
            "INSERT INTO energy_content_factor "
            "(fuel_type, kwh_per_unit, unit, effective_from, methodology_note) VALUES "
            "('grid_electricity', 1.0, 'kWh', '2026-01-01', 'identity'), "
            "('diesel', 10.72, 'litre', '2026-01-01', 'test factor')"
        )
    )


def test_cost_per_kg_and_energy_mix(db_session, facility):
    _seed_energy_content_factors(db_session)

    db_session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, cost_kes, source_channel) "
            "VALUES "
            "(:f, 'grid_electricity', '2026-01-01', '2026-01-31', 10000, 'kWh', 150000, 'manual'), "
            "(:f, 'diesel', '2026-01-01', '2026-01-31', 500, 'litre', 75000, 'manual')"
        ),
        {"f": str(facility)},
    )
    db_session.execute(
        text(
            "INSERT INTO production_record (facility_id, period_start, period_end, made_tea_kg) "
            "VALUES (:f, '2026-01-01', '2026-01-31', 5000)"
        ),
        {"f": str(facility)},
    )

    result = compute_benchmark(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))

    assert result.total_made_tea_kg == 5000
    assert result.total_cost_kes == 225000
    assert result.cost_per_kg_tea_kes == pytest.approx(45.0)

    expected_grid_kwh = 10000 * 1.0
    expected_diesel_kwh = 500 * 10.72
    total_kwh = expected_grid_kwh + expected_diesel_kwh
    assert result.total_energy_kwh == pytest.approx(total_kwh)
    assert result.energy_mix_pct["grid_electricity"] == pytest.approx(
        expected_grid_kwh / total_kwh * 100
    )
    assert result.missing_energy_content_factors == []


def test_reading_type_without_factor_is_excluded_and_flagged(db_session, facility):
    # solar_generation has no energy_content_factor seeded anywhere — unlike
    # grid_electricity/diesel/fuelwood, which seed-reference-data always
    # populates, so this holds regardless of what's already on file in
    # whatever database these tests run against.
    db_session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, source_channel) "
            "VALUES (:f, 'solar_generation', '2026-01-01', '2026-01-31', 12, 'kWh', 'manual')"
        ),
        {"f": str(facility)},
    )

    result = compute_benchmark(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))

    assert result.total_energy_kwh == 0
    assert result.missing_energy_content_factors == ["solar_generation"]


def test_reading_partially_outside_window_is_excluded(db_session, facility):
    _seed_energy_content_factors(db_session)
    db_session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, cost_kes, source_channel) "
            "VALUES (:f, 'grid_electricity', '2026-01-25', '2026-02-05', 1000, 'kWh', 15000, 'manual')"
        ),
        {"f": str(facility)},
    )

    result = compute_benchmark(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))
    assert result.total_energy_kwh == 0
    assert result.total_cost_kes == 0
