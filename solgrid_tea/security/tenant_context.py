"""Wires the authenticated user's organization into Postgres RLS.

RLS policies (see migrations/versions/0001_initial_schema.py) key off the
`app.org_id` session variable. That variable has to be set with `SET LOCAL`
as the first statement of the transaction that serves a request — set it
too late and earlier queries in the same request ran unscoped (and, because
every tenant table has FORCE ROW LEVEL SECURITY, "unscoped" means "returns
nothing", not "returns everything" — a query run before the GUC is set
against a table with no matching current_setting simply matches no rows).
"""

from flask import g
from flask_jwt_extended import get_jwt
from sqlalchemy import text

from solgrid_tea.extensions import db


def apply_tenant_context() -> None:
    claims = get_jwt()
    org_id = claims.get("org_id")
    if not org_id:
        raise RuntimeError("JWT is missing the org_id claim; cannot scope tenant context")

    # SET LOCAL doesn't accept a bind parameter (Postgres rejects "SET LOCAL
    # x = $1" as a syntax error — SET is parsed, not planned, so it only
    # takes literals). set_config() is a normal SQL function and does.
    db.session.execute(text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": org_id})
    g.current_org_id = org_id
    g.current_user_id = claims.get("sub")
    g.current_role = claims.get("role")
