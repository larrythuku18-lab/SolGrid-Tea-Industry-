from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import text
from werkzeug.security import check_password_hash

from solgrid_tea.extensions import db, limiter
from solgrid_tea.models import AppUser, Organization
from solgrid_tea.schemas.auth import LoginRequest, TokenResponse
from solgrid_tea.security import tenant_scoped

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    payload = LoginRequest.model_validate(request.get_json(silent=True) or {})

    # auth_lookup_user is a SECURITY DEFINER function (see migration
    # 0001) that deliberately reads across tenants — there is no org
    # context yet at login time, so a plain RLS-scoped ORM query on
    # app_user can never find the row.
    row = (
        db.session.execute(
            text(
                "SELECT id, organization_id, password_hash, role, is_active "
                "FROM auth_lookup_user(:email)"
            ),
            {"email": payload.email},
        )
        .mappings()
        .first()
    )

    if row is None or not row["is_active"] or not check_password_hash(
        row["password_hash"], payload.password
    ):
        return jsonify(error="invalid_credentials"), 401

    claims = {"org_id": str(row["organization_id"]), "role": row["role"]}
    access_token = create_access_token(identity=str(row["id"]), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(row["id"]), additional_claims=claims)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=row["role"],
        organization_id=str(row["organization_id"]),
    )
    return jsonify(response.model_dump())


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    identity = get_jwt_identity()
    new_claims = {"org_id": claims["org_id"], "role": claims["role"]}
    access_token = create_access_token(identity=identity, additional_claims=new_claims)
    return jsonify(access_token=access_token)


@auth_bp.get("/me")
@tenant_scoped()
def me():
    user = db.session.get(AppUser, g.current_user_id)
    org = db.session.get(Organization, g.current_org_id)
    return jsonify(
        user_id=g.current_user_id,
        org_id=g.current_org_id,
        role=g.current_role,
        email=user.email if user else None,
        organization_name=org.name if org else None,
    )
