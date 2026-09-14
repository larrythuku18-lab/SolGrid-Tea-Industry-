from flask import Blueprint, jsonify, request

from solgrid_tea.extensions import db
from solgrid_tea.schemas.benchmark import BenchmarkQuery
from solgrid_tea.security import tenant_scoped
from solgrid_tea.services.benchmark_engine import compute_benchmark

benchmark_bp = Blueprint("benchmark", __name__)


@benchmark_bp.get("")
@tenant_scoped()
def get_benchmark():
    query = BenchmarkQuery.model_validate(
        {
            "facility_id": request.args.get("facility_id"),
            "period_start": request.args.get("period_start"),
            "period_end": request.args.get("period_end"),
        }
    )
    result = compute_benchmark(db.session, query.facility_id, query.period_start, query.period_end)
    return jsonify(result.model_dump(mode="json"))
