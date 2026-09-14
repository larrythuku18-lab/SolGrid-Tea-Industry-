from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, jwt_required

from .tenant_context import apply_tenant_context


def tenant_scoped(roles: tuple[str, ...] | None = None):
    """Require a valid JWT, apply RLS tenant context, and optionally gate by role.

    Every route that touches a tenant-scoped table must use this instead of
    bare @jwt_required(), or its queries run without app.org_id set.
    """

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            apply_tenant_context()
            if roles is not None:
                claims = get_jwt()
                if claims.get("role") not in roles:
                    return jsonify(error="forbidden", detail="insufficient role"), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator
