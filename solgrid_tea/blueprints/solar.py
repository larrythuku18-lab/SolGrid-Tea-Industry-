"""Solar generation vs. consumption, and panel/battery health — see
migrations/0002 and services/solar_insights.py for why this exists ahead
of real panels being contracted at either factory."""

from datetime import date

from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt

from solgrid_tea.extensions import db
from solgrid_tea.schemas.solar import SolarHealthQuery, SolarLiveQuery, SolarQuery
from solgrid_tea.security import tenant_scoped
from solgrid_tea.services.solar_insights import (
    generation_vs_consumption_series,
    solar_health_history,
    solar_health_summary,
)
from solgrid_tea.services.solar_live import (
    DEFAULT_INTERVAL_S,
    solar_live_events,
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


@solar_bp.get("/live")
@tenant_scoped()
def get_solar_live():
    """Server-sent events for the Solar page: new panel/battery readings as
    they land, the generation series when the ledger rows behind it change,
    and a freshness tick every interval so a viewer can tell "quiet" from
    "stopped reporting" (see services/solar_live.py).

    Deliberately not a websocket and deliberately not polled by the client on
    a timer: one open stream per dashboard, and the server decides what is
    worth sending.
    """
    query = SolarLiveQuery.model_validate(
        {
            "facility_id": request.args.get("facility_id"),
            "period_start": request.args.get("period_start"),
            "period_end": request.args.get("period_end"),
            "interval_s": request.args.get("interval_s"),
        }
    )
    # Read the org out here, on the request that carried the JWT. The
    # streaming response outlives this request's context — by the time the
    # generator's third poll runs, g (and therefore get_jwt()) is long gone,
    # and a generator calling apply_tenant_context() itself would raise.
    org_id = get_jwt().get("org_id")
    if not org_id:
        raise RuntimeError("JWT is missing the org_id claim; cannot scope tenant context")

    return Response(
        stream_with_context(
            solar_live_events(
                db.engine,
                org_id,
                query.facility_id,
                interval_s=query.interval_s or DEFAULT_INTERVAL_S,
                period_start=query.period_start,
                period_end=query.period_end,
            )
        ),
        mimetype="text/event-stream",
        headers={
            # No buffering anywhere along the path, or the whole point of a
            # stream is lost: nginx needs X-Accel-Buffering, and the explicit
            # no-cache keeps intermediary proxies from holding frames back.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@solar_bp.get("/health/history")
@tenant_scoped()
def get_solar_health_history():
    query = SolarQuery.model_validate(
        {
            "facility_id": request.args.get("facility_id"),
            "period_start": request.args.get("period_start"),
            "period_end": request.args.get("period_end"),
        }
    )
    points = solar_health_history(db.session, query.facility_id, query.period_start, query.period_end)
    return jsonify([p.model_dump(mode="json") for p in points])
