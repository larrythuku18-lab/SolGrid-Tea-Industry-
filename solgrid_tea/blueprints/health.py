from flask import Blueprint, jsonify
from sqlalchemy import text

from solgrid_tea.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def healthz():
    return jsonify(status="ok")


@health_bp.get("/readyz")
def readyz():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify(status="not ready"), 503
    return jsonify(status="ready")
