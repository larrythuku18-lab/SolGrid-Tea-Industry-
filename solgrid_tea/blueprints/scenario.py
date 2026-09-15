from datetime import date

from flask import Blueprint, g, jsonify, request

from solgrid_tea.errors import DomainError
from solgrid_tea.extensions import db
from solgrid_tea.models import Facility, ScenarioRun
from solgrid_tea.schemas.scenario import ScenarioInput
from solgrid_tea.security import tenant_scoped
from solgrid_tea.services.calculation_engine import run_solar_scenario
from solgrid_tea.services.reference_lookup import latest_emission_factor

scenario_bp = Blueprint("scenario", __name__)

WRITE_ROLES = ("admin", "operator")


@scenario_bp.post("")
@tenant_scoped(roles=WRITE_ROLES)
def create_scenario():
    scenario_input = ScenarioInput.model_validate(request.get_json(silent=True) or {})

    # facility carries RLS, so this also rejects a facility_id from another tenant.
    if db.session.get(Facility, scenario_input.facility_id) is None:
        raise DomainError("facility not found", status_code=404)

    factor = latest_emission_factor(db.session, "grid_electricity", date.today())
    if factor is None:
        raise DomainError(
            "no grid_electricity emission factor is on file — seed reference data first",
            status_code=409,
        )

    fuelwood_factor = None
    if scenario_input.fuelwood_reduction_pct is not None:
        fuelwood_factor = latest_emission_factor(db.session, "fuelwood", date.today())
        if fuelwood_factor is None:
            raise DomainError(
                "no fuelwood emission factor is on file — seed reference data first",
                status_code=409,
            )

    result = run_solar_scenario(
        scenario_input,
        grid_emission_factor_kg_per_kwh=float(factor.kg_co2_per_unit),
        grid_emission_factor_id=factor.id,
        grid_emission_factor_methodology_note=factor.methodology_note,
        fuelwood_emission_factor_kg_per_m3=(
            float(fuelwood_factor.kg_co2_per_unit) if fuelwood_factor else None
        ),
        fuelwood_emission_factor_id=fuelwood_factor.id if fuelwood_factor else None,
        fuelwood_emission_factor_methodology_note=(
            fuelwood_factor.methodology_note if fuelwood_factor else None
        ),
    )

    run = ScenarioRun(
        facility_id=scenario_input.facility_id,
        assumptions=scenario_input.model_dump(mode="json"),
        results=result.model_dump(mode="json"),
        created_by_user_id=g.current_user_id,
    )
    db.session.add(run)
    db.session.commit()

    return jsonify(id=str(run.id), **result.model_dump(mode="json")), 201


@scenario_bp.get("/<uuid:scenario_run_id>")
@tenant_scoped()
def get_scenario(scenario_run_id):
    run = db.session.get(ScenarioRun, scenario_run_id)
    if run is None:
        raise DomainError("scenario run not found", status_code=404)
    return jsonify(
        id=str(run.id),
        facility_id=str(run.facility_id),
        assumptions=run.assumptions,
        results=run.results,
        created_at=run.created_at.isoformat(),
    )
