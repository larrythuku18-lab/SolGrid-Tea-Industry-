from flask import Flask

from .config import get_config
from .errors import register_error_handlers
from .extensions import cors, db, jwt, limiter


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"] or "*")
    limiter.init_app(app)

    register_error_handlers(app)

    from .blueprints.auth import auth_bp
    from .blueprints.benchmark import benchmark_bp
    from .blueprints.health import health_bp
    from .blueprints.ledger import ledger_bp
    from .blueprints.scenario import scenario_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(ledger_bp, url_prefix="/api/v1/ledger")
    app.register_blueprint(benchmark_bp, url_prefix="/api/v1/benchmark")
    app.register_blueprint(scenario_bp, url_prefix="/api/v1/scenarios")

    from . import cli as cli_module

    cli_module.register_cli(app)

    return app
