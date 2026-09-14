import os

import pytest
from sqlalchemy import text

from solgrid_tea import create_app
from solgrid_tea.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("FLASK_ENV", "testing")
    application = create_app("testing")
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    """A live DB session, for tests marked `db`. Skips (not fails) if no
    TEST_DATABASE_URL / DATABASE_URL is reachable — these tests need
    `docker compose up db` and aren't expected to run in a plain checkout.
    """
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        pytest.skip("no database configured (set TEST_DATABASE_URL or DATABASE_URL)")

    with app.app_context():
        try:
            _db.session.execute(text("SELECT 1"))
        except Exception as exc:
            pytest.skip(f"database not reachable: {exc}")
        yield _db.session
        _db.session.rollback()
