from uuid import uuid4

import pytest
from pydantic import ValidationError

from solgrid_tea.schemas.scenario import ScenarioInput
from solgrid_tea.services.calculation_engine import run_solar_scenario

FACILITY_ID = uuid4()
FACTOR_ID = uuid4()


def _base_kwargs(**overrides):
    kwargs = dict(
        facility_id=FACILITY_ID,
        financing_mode="capex",
        target_solar_kw=100.0,
        grid_tariff_kes_per_kwh=25.0,
        capex_kes=12_000_000.0,
        daytime_coincidence_factor=0.5,
        solar_capacity_factor=0.20,
        baseline_annual_grid_kwh=500_000.0,
        baseline_annual_electrical_kwh=500_000.0,
        baseline_annual_total_energy_kwh=4_000_000.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_capex_mode_payback_uses_full_avoided_grid_cost():
    scenario_input = ScenarioInput(**_base_kwargs())
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )

    solar_gen = 100.0 * 0.20 * 8760
    coincident = 500_000.0 * 0.5
    expected_addressable = min(solar_gen, coincident)

    assert result.solar_annual_generation_kwh == pytest.approx(solar_gen)
    assert result.addressable_kwh == pytest.approx(expected_addressable)
    assert result.annual_savings_kes == pytest.approx(expected_addressable * 25.0)
    assert result.payback_years == pytest.approx(12_000_000.0 / result.annual_savings_kes)


def test_ppa_mode_has_no_payback_and_uses_rate_spread():
    scenario_input = ScenarioInput(
        **_base_kwargs(financing_mode="ppa", capex_kes=None, ppa_rate_kes_per_kwh=14.0)
    )
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )

    assert result.payback_years is None
    assert result.annual_savings_kes == pytest.approx(result.addressable_kwh * (25.0 - 14.0))


def test_addressable_kwh_is_capped_by_coincident_demand_not_solar_capacity():
    # Oversized array relative to demand: addressable should cap at the
    # coincident electrical load, not run away with solar's raw output.
    scenario_input = ScenarioInput(
        **_base_kwargs(
            target_solar_kw=10_000.0,
            baseline_annual_grid_kwh=100_000.0,
            baseline_annual_electrical_kwh=100_000.0,
        )
    )
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )
    assert result.addressable_kwh == pytest.approx(100_000.0 * 0.5)


def test_addressable_of_total_energy_pct_is_always_smaller_than_electrical_share():
    scenario_input = ScenarioInput(**_base_kwargs())
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )
    assert result.addressable_of_total_energy_pct < result.addressable_electrical_share_pct


def test_pure_solar_scenario_never_reports_fuelwood_impact():
    scenario_input = ScenarioInput(**_base_kwargs())
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )
    assert result.emissions_avoided_fuelwood_tco2 == 0.0
    assert result.fuelwood_reduction_m3 == 0.0


def test_emissions_avoided_scales_with_supplied_factor_not_a_hardcoded_constant():
    scenario_input = ScenarioInput(**_base_kwargs())
    result_a = run_solar_scenario(
        scenario_input, grid_emission_factor_kg_per_kwh=0.10, grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="a",
    )
    result_b = run_solar_scenario(
        scenario_input, grid_emission_factor_kg_per_kwh=0.20, grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="b",
    )
    assert result_b.emissions_avoided_grid_tco2 == pytest.approx(
        2 * result_a.emissions_avoided_grid_tco2
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"financing_mode": "ppa", "capex_kes": None, "ppa_rate_kes_per_kwh": None},
        {"financing_mode": "capex", "capex_kes": None},
    ],
)
def test_financing_mode_requires_its_matching_field(overrides):
    with pytest.raises(ValidationError):
        ScenarioInput(**_base_kwargs(**overrides))


def test_electrical_baseline_cannot_be_less_than_grid_baseline():
    with pytest.raises(ValidationError):
        ScenarioInput(
            **_base_kwargs(baseline_annual_grid_kwh=600_000.0, baseline_annual_electrical_kwh=500_000.0)
        )


# --- thermal-efficiency add-on -------------------------------------------

FUELWOOD_FACTOR_ID = uuid4()


def _thermal_kwargs(**overrides):
    kwargs = dict(
        fuelwood_reduction_pct=20.0,
        baseline_annual_fuelwood_m3=1000.0,
        fuelwood_price_kes_per_m3=4000.0,
    )
    kwargs.update(overrides)
    return kwargs


@pytest.mark.parametrize(
    "missing_field",
    ["fuelwood_reduction_pct", "baseline_annual_fuelwood_m3", "fuelwood_price_kes_per_m3"],
)
def test_thermal_fields_must_be_given_together(missing_field):
    thermal = _thermal_kwargs()
    thermal[missing_field] = None
    with pytest.raises(ValidationError):
        ScenarioInput(**_base_kwargs(**thermal))


def test_scenario_without_thermal_input_reports_zero_fuelwood_impact():
    scenario_input = ScenarioInput(**_base_kwargs())
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )
    assert result.fuelwood_reduction_m3 == 0.0
    assert result.fuelwood_cost_savings_kes == 0.0
    assert result.emissions_avoided_fuelwood_tco2 == 0.0
    assert result.fuelwood_emission_factor_id is None
    assert result.fuelwood_emission_factor_methodology_note is None


def test_thermal_component_computes_deterministic_delta_from_stated_pct():
    scenario_input = ScenarioInput(**_base_kwargs(**_thermal_kwargs(fuelwood_reduction_pct=20.0)))
    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
        fuelwood_emission_factor_kg_per_m3=350.0,
        fuelwood_emission_factor_id=FUELWOOD_FACTOR_ID,
        fuelwood_emission_factor_methodology_note="fuelwood test factor",
    )

    # 1000 m3 baseline * 20% stated reduction
    assert result.fuelwood_reduction_m3 == pytest.approx(200.0)
    assert result.fuelwood_cost_savings_kes == pytest.approx(200.0 * 4000.0)
    assert result.emissions_avoided_fuelwood_tco2 == pytest.approx(200.0 * 350.0 / 1000)
    assert result.fuelwood_emission_factor_id == FUELWOOD_FACTOR_ID
    assert result.fuelwood_emission_factor_methodology_note == "fuelwood test factor"


def test_thermal_savings_are_not_folded_into_solar_payback():
    # Same solar assumptions with and without a thermal component: payback
    # (and annual_savings_kes, which drives it) must be identical, since
    # capex only buys the solar installation — see ScenarioResult's comment.
    solar_only = ScenarioInput(**_base_kwargs())
    with_thermal = ScenarioInput(**_base_kwargs(**_thermal_kwargs()))

    kwargs = dict(
        grid_emission_factor_kg_per_kwh=0.11,
        grid_emission_factor_id=FACTOR_ID,
        grid_emission_factor_methodology_note="test factor",
    )
    result_solar_only = run_solar_scenario(solar_only, **kwargs)
    result_with_thermal = run_solar_scenario(
        with_thermal,
        fuelwood_emission_factor_kg_per_m3=350.0,
        fuelwood_emission_factor_id=FUELWOOD_FACTOR_ID,
        fuelwood_emission_factor_methodology_note="fuelwood test factor",
        **kwargs,
    )

    assert result_with_thermal.annual_savings_kes == pytest.approx(
        result_solar_only.annual_savings_kes
    )
    assert result_with_thermal.payback_years == pytest.approx(result_solar_only.payback_years)
    assert result_with_thermal.fuelwood_cost_savings_kes > 0
