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
from solgrid_tea.schemas.extraction import DOCUMENT_TYPES
from solgrid_tea.schemas.ledger import EnergyReadingCreate, ProductionRecordCreate
from solgrid_tea.security import tenant_scoped
from solgrid_tea.services.extraction import extract_document_fields

ledger_bp = Blueprint("ledger", __name__)

WRITE_ROLES = ("admin", "operator")

ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_EXTRACTION_IMAGE_BYTES = 10 * 1024 * 1024  # generous for a phone photo


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


@ledger_bp.post("/extract")
@tenant_scoped(roles=WRITE_ROLES)
def extract_ledger_fields():
    """Propose field values from a photographed document for a human to
    review before submitting through the endpoints above. Writes nothing —
    see solgrid_tea.services.extraction for the full contract."""
    document_type = request.form.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        raise DomainError(
            f"document_type must be one of {', '.join(DOCUMENT_TYPES)}", status_code=422
        )

    image = request.files.get("image")
    if image is None or image.filename == "":
        raise DomainError("image file is required", status_code=422)
    if image.mimetype not in ALLOWED_IMAGE_MIME_TYPES:
        raise DomainError(
            f"unsupported image type {image.mimetype!r} — use PNG, JPEG, WEBP, or GIF",
            status_code=422,
        )

    image_bytes = image.read(MAX_EXTRACTION_IMAGE_BYTES + 1)
    if not image_bytes:
        raise DomainError("image file is empty", status_code=422)
    if len(image_bytes) > MAX_EXTRACTION_IMAGE_BYTES:
        raise DomainError("image exceeds the 10MB limit", status_code=422)

    result = extract_document_fields(image_bytes, image.mimetype, document_type)
    return jsonify(result.model_dump(mode="json"))
