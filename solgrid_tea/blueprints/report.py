"""report_snapshot publish/read — architecture doc §6 and §10.

Publishing is gated by three checks. Two are overridable with a logged
reason (completeness, plausibility); the placeholder-data check is not —
see report_engine's module docstring for why.
"""

from flask import Blueprint, g, jsonify, request

from solgrid_tea.errors import DomainError
from solgrid_tea.extensions import db
from solgrid_tea.models import Facility, ReportSnapshot
from solgrid_tea.schemas.report import PlaceholderDataError, PublishReportRequest, ReportPayload
from solgrid_tea.security import tenant_scoped
from solgrid_tea.services.plausibility_check import run_plausibility_check
from solgrid_tea.services.report_engine import (
    REPORT_METHODOLOGY_VERSION,
    assert_no_placeholder_sources,
    build_report_payload,
    check_completeness,
    external_payload_view,
    period_summary,
    trailing_period_summaries,
)

report_bp = Blueprint("report", __name__)

WRITE_ROLES = ("admin", "operator")


def _resolve_superseded_snapshot(payload_in: PublishReportRequest) -> ReportSnapshot | None:
    """Look up and validate the snapshot a new publish is correcting, if any."""
    if payload_in.supersedes is None:
        return None

    # RLS-scoped lookup, same as the facility check above the call site —
    # a cross-tenant id simply won't be found.
    snapshot = db.session.get(ReportSnapshot, payload_in.supersedes)
    if snapshot is None:
        raise DomainError("snapshot to supersede not found", status_code=404)
    if snapshot.superseded_by is not None:
        raise DomainError("that snapshot has already been superseded", status_code=409)
    if (
        snapshot.facility_id != payload_in.facility_id
        or snapshot.period_start != payload_in.period_start
        or snapshot.period_end != payload_in.period_end
    ):
        raise DomainError(
            "supersedes must reference a snapshot for the same facility_id, "
            "period_start, and period_end",
            status_code=422,
        )
    return snapshot


@report_bp.post("")
@tenant_scoped(roles=WRITE_ROLES)
def publish_report():
    payload_in = PublishReportRequest.model_validate(request.get_json(silent=True) or {})

    # facility carries RLS, so this also rejects a facility_id from another tenant.
    if db.session.get(Facility, payload_in.facility_id) is None:
        raise DomainError("facility not found", status_code=404)

    superseded_snapshot = _resolve_superseded_snapshot(payload_in)

    completeness = check_completeness(
        db.session, payload_in.facility_id, payload_in.period_start, payload_in.period_end
    )

    current = period_summary(
        db.session, payload_in.facility_id, payload_in.period_start, payload_in.period_end
    )
    trailing = trailing_period_summaries(
        db.session, payload_in.facility_id, payload_in.period_start, payload_in.period_end
    )
    plausibility = run_plausibility_check(current, trailing)

    checks_failed = (not completeness.passed) or plausibility.flagged
    if checks_failed and not payload_in.override_reason:
        return (
            jsonify(
                published=False,
                completeness=completeness.model_dump(),
                plausibility=plausibility.model_dump(),
                detail=(
                    "one or more pre-publish checks failed — resubmit with "
                    "override_reason to publish anyway"
                ),
            ),
            422,
        )

    report_payload, placeholder_sources = build_report_payload(
        db.session, payload_in.facility_id, payload_in.period_start, payload_in.period_end
    )
    try:
        assert_no_placeholder_sources(placeholder_sources)
    except PlaceholderDataError as exc:
        raise DomainError(str(exc), status_code=409) from exc

    full_payload = {
        "report": report_payload.model_dump(mode="json"),
        "checks": {
            "completeness": completeness.model_dump(mode="json"),
            "plausibility": plausibility.model_dump(mode="json"),
            "override_reason": payload_in.override_reason,
        },
        "published_by_user_id": g.current_user_id,
    }

    snapshot = ReportSnapshot(
        facility_id=payload_in.facility_id,
        period_start=payload_in.period_start,
        period_end=payload_in.period_end,
        payload=full_payload,
        methodology_version=REPORT_METHODOLOGY_VERSION,
    )
    db.session.add(snapshot)
    if superseded_snapshot is not None:
        db.session.flush()  # populate snapshot.id (server-side default)
        superseded_snapshot.superseded_by = snapshot.id
    db.session.commit()

    return (
        jsonify(
            id=str(snapshot.id),
            published=True,
            methodology_version=snapshot.methodology_version,
            supersedes=str(payload_in.supersedes) if payload_in.supersedes else None,
            **full_payload,
        ),
        201,
    )


@report_bp.get("/<uuid:snapshot_id>")
@tenant_scoped()
def get_report(snapshot_id):
    snapshot = db.session.get(ReportSnapshot, snapshot_id)
    if snapshot is None:
        raise DomainError("report snapshot not found", status_code=404)

    tier = request.args.get("tier", "internal")
    if tier not in ("internal", "external"):
        raise DomainError("tier must be 'internal' or 'external'", status_code=422)

    internal_payload = ReportPayload.model_validate(snapshot.payload["report"])
    if tier == "external":
        report_out = external_payload_view(internal_payload, snapshot.methodology_version)
    else:
        report_out = internal_payload

    return jsonify(
        id=str(snapshot.id),
        facility_id=str(snapshot.facility_id),
        period_start=snapshot.period_start.isoformat(),
        period_end=snapshot.period_end.isoformat(),
        published_at=snapshot.published_at.isoformat(),
        methodology_version=snapshot.methodology_version,
        superseded_by=str(snapshot.superseded_by) if snapshot.superseded_by else None,
        tier=tier,
        report=report_out.model_dump(mode="json"),
    )
