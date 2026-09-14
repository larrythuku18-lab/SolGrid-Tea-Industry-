from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

# expire_on_commit=False: by default SQLAlchemy expires every ORM attribute
# on commit, so the next access re-queries the DB — but RLS's tenant
# context (app.org_id) is set with set_config(..., is_local=true), scoped
# to exactly the transaction that just ended. A route that reads
# `some_row.id` right after db.session.commit() would otherwise trigger
# that reload with no tenant context set, and get rejected by RLS instead
# of just returning the value it already had.
db = SQLAlchemy(session_options={"expire_on_commit": False})
jwt = JWTManager()
cors = CORS()
limiter = Limiter(key_func=get_remote_address)
