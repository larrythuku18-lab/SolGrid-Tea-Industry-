"""Solar generation vs. consumption, and panel/battery health — see
migrations/0002 and services/solar_insights.py for why this exists ahead
of real panels being contracted at either factory."""

from datetime import date

from flask import Blueprint, jsonify, request

from solgrid_tea.extensions import db
from solgrid_tea.schemas.solar import SolarHealthQuery, SolarQuery
from solgrid_tea.security import tenant_scoped
from solgrid_tea.services.solar_insights import (
    generation_vs_consumption_series,
    solar_health_summary,
)

solar_bp = Blueprint("solar", __name__)


@solar_bp.get("/generation")
@tenant_scoped()
def get_generation_vs_consumption():
    query = SolarQuery.model_validate(
        {
            "facility_id": request.args.get("facility_id"),
            "period_start": request.args.get("period_start"),
            "period_end": request.args.get("period_end"),
        }
    )
    result = generation_vs_consumption_series(
        db.session, query.facility_id, query.period_start, query.period_end
    )
    return jsonify(result.model_dump(mode="json"))


@solar_bp.get("/health")
@tenant_scoped()
def get_solar_health():
    query = SolarHealthQuery.model_validate(
        {"facility_id": request.args.get("facility_id"), "as_of": request.args.get("as_of")}
    )
    result = solar_health_summary(db.session, query.facility_id, query.as_of or date.today())
    return jsonify(result.model_dump(mode="json"))
