"""Tier-4 ledger ingestion — web-form channel only for now.

The SMS/USSD channel (architecture doc §3, build step 4) shares this same
EnergyReadingCreate schema and EnergyReading model; it's a second blueprint
to add later (Africa's Talking webhook -> same validation -> source_channel
'sms'), not a change to this one.
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from solgrid_tea.errors import DomainError
from solgrid_tea.extensions import db
from solgrid_tea.models import EnergyReading, Facility, ProductionRecord
from solgrid_tea.schemas.ledger import EnergyReadingCreate, ProductionRecordCreate
from solgrid_tea.security import tenant_scoped

ledger_bp = Blueprint("ledger", __name__)

WRITE_ROLES = ("admin", "operator")


def _assert_facility_in_org(facility_id) -> None:
    # facility carries RLS too, so a facility_id from another tenant simply
    # doesn't resolve here — this existence check *is* the tenant check.
    if db.session.get(Facility, facility_id) is None:
        raise DomainError("facility not found", status_code=404)


@ledger_bp.post("/energy-readings")
@tenant_scoped(roles=WRITE_ROLES)
def create_energy_reading():
    payload = EnergyReadingCreate.model_validate(request.get_json(silent=True) or {})
    _assert_facility_in_org(payload.facility_id)

    reading = EnergyReading(
        facility_id=payload.facility_id,
        reading_type=payload.reading_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        quantity=payload.quantity,
        unit=payload.unit,
        cost_kes=payload.cost_kes,
        moisture_pct=payload.moisture_pct,
        source_plantation=payload.source_plantation,
        source_channel=payload.source_channel,
        entered_by_user_id=g.current_user_id,
        entered_by_phone=payload.entered_by_phone,
    )
    db.session.add(reading)
    db.session.commit()
    return jsonify(id=str(reading.id)), 201


@ledger_bp.get("/energy-readings")
@tenant_scoped()
def list_energy_readings():
    query = select(EnergyReading)
    facility_id = request.args.get("facility_id")
    if facility_id:
        query = query.where(EnergyReading.facility_id == facility_id)
    if period_start := request.args.get("period_start"):
        query = query.where(EnergyReading.period_start >= period_start)
    if period_end := request.args.get("period_end"):
        query = query.where(EnergyReading.period_end <= period_end)
    query = query.order_by(EnergyReading.period_start.desc()).limit(500)

    readings = db.session.scalars(query).all()
    return jsonify([_serialize_reading(r) for r in readings])


def _serialize_reading(r: EnergyReading) -> dict:
    return {
        "id": str(r.id),
        "facility_id": str(r.facility_id),
        "reading_type": r.reading_type,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "quantity": float(r.quantity),
        "unit": r.unit,
        "cost_kes": float(r.cost_kes) if r.cost_kes is not None else None,
        "moisture_pct": float(r.moisture_pct) if r.moisture_pct is not None else None,
        "source_plantation": r.source_plantation,
        "source_channel": r.source_channel,
    }


@ledger_bp.post("/production-records")
@tenant_scoped(roles=WRITE_ROLES)
def create_production_record():
    payload = ProductionRecordCreate.model_validate(request.get_json(silent=True) or {})
    _assert_facility_in_org(payload.facility_id)

    record = ProductionRecord(
        facility_id=payload.facility_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        made_tea_kg=payload.made_tea_kg,
        source=payload.source,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(id=str(record.id)), 201


@ledger_bp.get("/production-records")
@tenant_scoped()
def list_production_records():
    query = select(ProductionRecord)
    facility_id = request.args.get("facility_id")
    if facility_id:
        query = query.where(ProductionRecord.facility_id == facility_id)
    query = query.order_by(ProductionRecord.period_start.desc()).limit(500)

    records = db.session.scalars(query).all()
    return jsonify(
        [
            {
                "id": str(r.id),
                "facility_id": str(r.facility_id),
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "made_tea_kg": float(r.made_tea_kg),
                "source": r.source,
            }
            for r in records
        ]
    )
