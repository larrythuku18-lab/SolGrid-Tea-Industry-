from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from solgrid_tea.extensions import db
from solgrid_tea.models import Facility
from solgrid_tea.schemas.facility import FacilityCreate
from solgrid_tea.security import tenant_scoped

facility_bp = Blueprint("facility", __name__)

WRITE_ROLES = ("admin",)


def _serialize(f: Facility) -> dict:
    return {
        "id": str(f.id),
        "name": f.name,
        "county": f.county,
        "install_capacity_kw": float(f.install_capacity_kw) if f.install_capacity_kw is not None else None,
        "is_active": f.is_active,
    }


@facility_bp.get("")
@tenant_scoped()
def list_facilities():
    facilities = db.session.scalars(select(Facility).order_by(Facility.name)).all()
    return jsonify([_serialize(f) for f in facilities])


@facility_bp.post("")
@tenant_scoped(roles=WRITE_ROLES)
def create_facility():
    payload = FacilityCreate.model_validate(request.get_json(silent=True) or {})

    # organization_id is set directly (not trigger-derived, unlike
    # energy_reading/production_record) since facility is the root of the
    # tenant hierarchy, not scoped through another facility.
    facility = Facility(
        organization_id=g.current_org_id,
        name=payload.name,
        county=payload.county,
        install_capacity_kw=payload.install_capacity_kw,
    )
    db.session.add(facility)
    db.session.commit()
    return jsonify(_serialize(facility)), 201
