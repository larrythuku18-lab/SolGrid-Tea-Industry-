"""Integration tests for report_engine — needs a live database, same
fixture pattern as test_benchmark_engine.py."""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from solgrid_tea.services.report_engine import (
    build_report_payload,
    check_completeness,
    period_summary,
    trailing_period_summaries,
)

pytestmark = pytest.mark.db


@pytest.fixture()
def facility(db_session):
    org_id = uuid.uuid4()
    db_session.execute(
        text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
    )
    db_session.execute(
        text("INSERT INTO organization (id, name) VALUES (:id, 'Gatitu Test')"),
        {"id": str(org_id)},
    )
    facility_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO facility (id, organization_id, name) VALUES (:id, :org_id, 'Gatitu')"),
        {"id": str(facility_id), "org_id": str(org_id)},
    )
    return facility_id


def _seed_factors(session, emission_note="test factor", energy_note="test factor"):
    session.execute(
        text(
            "INSERT INTO energy_content_factor "
            "(fuel_type, kwh_per_unit, unit, effective_from, methodology_note) VALUES "
            "('grid_electricity', 1.0, 'kWh', '2026-01-01', :note)"
        ),
        {"note": energy_note},
    )
    session.execute(
        text(
            "INSERT INTO emission_factor "
            "(fuel_type, kg_co2_per_unit, unit, effective_from, methodology_note) VALUES "
            "('grid_electricity', 0.11, 'kWh', '2026-01-01', :note)"
        ),
        {"note": emission_note},
    )


def _seed_reading_and_production(session, facility_id, cost_kes=150000, made_tea_kg=5000):
    session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, cost_kes, source_channel) "
            "VALUES (:f, 'grid_electricity', '2026-01-01', '2026-01-31', 10000, 'kWh', :cost, 'manual')"
        ),
        {"f": str(facility_id), "cost": cost_kes},
    )
    session.execute(
        text(
            "INSERT INTO production_record (facility_id, period_start, period_end, made_tea_kg) "
            "VALUES (:f, '2026-01-01', '2026-01-31', :made_tea_kg)"
        ),
        {"f": str(facility_id), "made_tea_kg": made_tea_kg},
    )


def test_completeness_fails_on_empty_ledger(db_session, facility):
    result = check_completeness(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))
    assert result.passed is False
    assert any("production_record" in g for g in result.gaps)


def test_completeness_passes_with_production_and_energy_data(db_session, facility):
    _seed_factors(db_session)
    _seed_reading_and_production(db_session, facility)

    result = check_completeness(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))
    assert result.passed is True
    assert result.gaps == []


def test_completeness_flags_missing_energy_content_factor(db_session, facility):
    # emission_factor seeded, but NOT energy_content_factor — the benchmark
    # excludes the reading from total_energy_kwh and flags it as missing.
    db_session.execute(
        text(
            "INSERT INTO emission_factor "
            "(fuel_type, kg_co2_per_unit, unit, effective_from, methodology_note) VALUES "
            "('grid_electricity', 0.11, 'kWh', '2026-01-01', 'test factor')"
        )
    )
    _seed_reading_and_production(db_session, facility)

    result = check_completeness(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))
    assert result.passed is False
    assert any("energy_content_factor" in g for g in result.gaps)


def test_build_report_payload_computes_emissions(db_session, facility):
    _seed_factors(db_session)
    _seed_reading_and_production(db_session, facility)

    payload, placeholder_sources = build_report_payload(
        db_session, facility, date(2026, 1, 1), date(2026, 1, 31)
    )

    assert placeholder_sources == []
    assert payload.total_made_tea_kg == 5000
    # 10000 kWh * 0.11 kgCO2/kWh / 1000 = 1.1 tCO2
    assert payload.total_emissions_tco2 == pytest.approx(1.1)
    assert payload.emissions_by_type_tco2["grid_electricity"] == pytest.approx(1.1)


def test_build_report_payload_flags_placeholder_emission_factor(db_session, facility):
    _seed_factors(db_session, emission_note="PLACEHOLDER pending real data")
    _seed_reading_and_production(db_session, facility)

    _payload, placeholder_sources = build_report_payload(
        db_session, facility, date(2026, 1, 1), date(2026, 1, 31)
    )

    assert "emission_factor:grid_electricity" in placeholder_sources


def test_build_report_payload_flags_placeholder_energy_content_factor(db_session, facility):
    _seed_factors(db_session, energy_note="PLACEHOLDER — rough estimate")
    _seed_reading_and_production(db_session, facility)

    _payload, placeholder_sources = build_report_payload(
        db_session, facility, date(2026, 1, 1), date(2026, 1, 31)
    )

    assert "energy_content_factor:grid_electricity" in placeholder_sources


def test_period_summary_breaks_out_electricity_and_fuelwood(db_session, facility):
    _seed_factors(db_session)
    _seed_reading_and_production(db_session, facility)
    db_session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, cost_kes, source_channel) "
            "VALUES (:f, 'fuelwood', '2026-01-01', '2026-01-31', 60, 'm3', 240000, 'manual')"
        ),
        {"f": str(facility)},
    )

    summary = period_summary(db_session, facility, date(2026, 1, 1), date(2026, 1, 31))
    assert summary.electricity_kwh == 10000
    assert summary.electricity_cost_kes == 150000
    assert summary.fuelwood_volume_m3 == 60
    assert summary.fuelwood_cost_kes == 240000
    assert summary.made_tea_kg == 5000


def test_trailing_period_summaries_only_returns_periods_with_production(db_session, facility):
    _seed_factors(db_session)
    _seed_reading_and_production(db_session, facility)  # January 1-31 only

    # A 31-day current period starting Feb 1 makes the immediately-preceding
    # 31-day trailing window exactly [Jan 1, Jan 31], matching the seeded
    # production record's period exactly (containment is exact-match here,
    # same "fully contained" rule as compute_benchmark).
    trailing = trailing_period_summaries(
        db_session, facility, date(2026, 2, 1), date(2026, 3, 3), count=6
    )
    # Only that one window has production; the other 5 trailing windows are
    # empty and must be excluded, not returned as zeros.
    assert len(trailing) == 1
    assert trailing[0].made_tea_kg == 5000
    assert trailing[0].period_start == date(2026, 1, 1)
    assert trailing[0].period_end == date(2026, 1, 31)
