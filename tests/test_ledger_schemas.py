from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from solgrid_tea.schemas.ledger import EnergyReadingCreate, ProductionRecordCreate

FACILITY_ID = uuid4()


def _reading(**overrides):
    kwargs = dict(
        facility_id=FACILITY_ID,
        reading_type="grid_electricity",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        quantity=1000.0,
        unit="kWh",
        cost_kes=15000.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_valid_grid_reading():
    reading = EnergyReadingCreate(**_reading())
    assert reading.source_channel == "manual"


def test_period_end_before_period_start_is_rejected():
    with pytest.raises(ValidationError):
        EnergyReadingCreate(**_reading(period_start=date(2026, 2, 1), period_end=date(2026, 1, 1)))


def test_moisture_pct_rejected_for_non_fuelwood():
    with pytest.raises(ValidationError):
        EnergyReadingCreate(**_reading(moisture_pct=12.0))


def test_source_plantation_rejected_for_non_fuelwood():
    with pytest.raises(ValidationError):
        EnergyReadingCreate(**_reading(source_plantation="North Block"))


def test_fuelwood_reading_accepts_moisture_and_plantation():
    reading = EnergyReadingCreate(
        **_reading(
            reading_type="fuelwood",
            unit="m3",
            moisture_pct=18.5,
            source_plantation="North Block",
            cost_kes=8000.0,
        )
    )
    assert reading.moisture_pct == 18.5


def test_solar_generation_cannot_carry_a_cost():
    with pytest.raises(ValidationError):
        EnergyReadingCreate(**_reading(reading_type="solar_generation", unit="kWh", cost_kes=1.0))


def test_solar_generation_without_cost_is_valid():
    reading = EnergyReadingCreate(**_reading(reading_type="solar_generation", unit="kWh", cost_kes=None))
    assert reading.cost_kes is None


def test_quantity_must_be_positive():
    with pytest.raises(ValidationError):
        EnergyReadingCreate(**_reading(quantity=0))


def test_production_record_period_order():
    with pytest.raises(ValidationError):
        ProductionRecordCreate(
            facility_id=FACILITY_ID,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 1, 1),
            made_tea_kg=1000.0,
        )


def test_production_record_made_tea_kg_must_be_positive():
    with pytest.raises(ValidationError):
        ProductionRecordCreate(
            facility_id=FACILITY_ID,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            made_tea_kg=0,
        )
