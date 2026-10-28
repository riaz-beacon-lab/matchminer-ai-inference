"""Flask application factory."""

from __future__ import annotations

import logging

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from mmai_web.api import BLUEPRINTS
from mmai_web.services import get_services
from mmai_web.services.notes import PatientNotFound
from mmai_web.services.trials import TrialNotFound
from mmai_web.settings import BACKEND_DIR

logger = logging.getLogger(__name__)

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    settings = get_services().settings
    CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    @app.errorhandler(HTTPException)
    def http_error(exc: HTTPException):
        return jsonify({"error": exc.name, "detail": exc.description}), exc.code

    @app.errorhandler(PatientNotFound)
    @app.errorhandler(TrialNotFound)
    def not_found(exc: LookupError):
        return jsonify({"error": "Not Found", "detail": str(exc)}), 404

    @app.errorhandler(ValueError)
    def bad_request(exc: ValueError):
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400

    @app.errorhandler(Exception)
    def server_error(exc: Exception):
        # Log the type only: messages from model calls can echo patient text.
        logger.error("Unhandled %s", type(exc).__name__)
        return jsonify(
            {"error": "Internal Server Error", "detail": type(exc).__name__}
        ), 500

    # Serve the built Vue app (bun run build) when present.
    if FRONTEND_DIST.exists():

        @app.get("/")
        @app.get("/<path:path>")
        def spa(path: str = ""):
            target = FRONTEND_DIST / path
            if path and target.is_file():
                return send_from_directory(FRONTEND_DIST, path)
            return send_from_directory(FRONTEND_DIST, "index.html")

    return app
