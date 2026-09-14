"""Deterministic scenario math — see architecture doc §0.2 and §5.

Every number here must be traceable to an input and a formula, never a
model. Intermediate values (solar_annual_generation_kwh, addressable_kwh)
are returned alongside the headline figures precisely so a report reader
can retrace the calculation by hand.

Only the pure-solar scenario is implemented. The architecture doc's §5
mapping table also calls for a thermal-efficiency scenario (fuelwood
reduction via better dryers, briquette blending, etc.), citing a
sector-wide 15-30% range — but that range isn't concretized into a formula
anywhere in the doc, and inventing one here would violate the same
determinism/traceability principle this module exists to uphold. It's
left unimplemented on purpose until that methodology is specified.
"""

from uuid import UUID

from solgrid_tea.schemas.scenario import ScenarioInput, ScenarioResult

HOURS_PER_YEAR = 8760


def run_solar_scenario(
    scenario_input: ScenarioInput,
    grid_emission_factor_kg_per_kwh: float,
    grid_emission_factor_id: UUID,
    grid_emission_factor_methodology_note: str,
) -> ScenarioResult:
    solar_annual_generation_kwh = (
        scenario_input.target_solar_kw * scenario_input.solar_capacity_factor * HOURS_PER_YEAR
    )

    # Capped by the coincident daytime electrical load: you cannot claim
    # credit for solar generation that has nothing to displace.
    coincident_electrical_kwh = (
        scenario_input.baseline_annual_electrical_kwh * scenario_input.daytime_coincidence_factor
    )
    addressable_kwh = min(solar_annual_generation_kwh, coincident_electrical_kwh)

    addressable_electrical_share_pct = (
        addressable_kwh / scenario_input.baseline_annual_electrical_kwh * 100
    )
    addressable_of_total_energy_pct = (
        addressable_kwh / scenario_input.baseline_annual_total_energy_kwh * 100
    )

    annual_savings_kes, payback_years = _financing_outcome(scenario_input, addressable_kwh)

    emissions_avoided_grid_tco2 = addressable_kwh * grid_emission_factor_kg_per_kwh / 1000

    return ScenarioResult(
        solar_annual_generation_kwh=solar_annual_generation_kwh,
        addressable_kwh=addressable_kwh,
        addressable_electrical_share_pct=addressable_electrical_share_pct,
        addressable_of_total_energy_pct=addressable_of_total_energy_pct,
        annual_savings_kes=annual_savings_kes,
        payback_years=payback_years,
        emissions_avoided_grid_tco2=emissions_avoided_grid_tco2,
        emissions_avoided_fuelwood_tco2=0.0,
        fuelwood_reduction_m3=0.0,
        grid_emission_factor_id=grid_emission_factor_id,
        grid_emission_factor_methodology_note=grid_emission_factor_methodology_note,
    )


def _financing_outcome(
    scenario_input: ScenarioInput, addressable_kwh: float
) -> tuple[float, float | None]:
    if scenario_input.financing_mode == "ppa":
        # No capex, so no payback figure — "payback" isn't the right frame
        # for a PPA. Savings are the per-kWh spread between grid and PPA rate.
        assert scenario_input.ppa_rate_kes_per_kwh is not None  # enforced by ScenarioInput
        annual_savings_kes = addressable_kwh * (
            scenario_input.grid_tariff_kes_per_kwh - scenario_input.ppa_rate_kes_per_kwh
        )
        return annual_savings_kes, None

    # Capex mode: the customer now owns the generation, so savings are the
    # full avoided grid cost (capex is a one-time outlay, not a recurring
    # per-kWh cost — O&M is out of scope for v1). Deducting a per-kWh
    # "levelized" cost here as well as dividing capex by savings for payback
    # would double-count the same capex in two places.
    assert scenario_input.capex_kes is not None  # enforced by ScenarioInput
    annual_savings_kes = addressable_kwh * scenario_input.grid_tariff_kes_per_kwh
    payback_years = (
        scenario_input.capex_kes / annual_savings_kes if annual_savings_kes > 0 else None
    )
    return annual_savings_kes, payback_years
