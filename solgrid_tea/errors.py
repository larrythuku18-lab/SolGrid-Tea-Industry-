import logging

from flask import jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger("solgrid_tea")


class DomainError(Exception):
    """Raised by service-layer code for a business-rule violation that
    should surface as a 4xx, not a 500."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register_error_handlers(app):
    @app.errorhandler(DomainError)
    def handle_domain_error(err: DomainError):
        return jsonify(error="domain_error", detail=err.message), err.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        return jsonify(error="validation_error", detail=err.errors()), 422

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        return jsonify(error=err.name, detail=err.description), err.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):
        logger.exception("unhandled exception")
        return jsonify(error="internal_error", detail="an unexpected error occurred"), 500
