"""Campfyr application factory."""

import os
import secrets
from pathlib import Path

from flask import Flask, Response, request

from .db import init_database


def _default_database_path(app):
    configured = os.getenv("CAMPFYR_DATABASE_PATH")
    if configured:
        return configured
    return str(Path(app.instance_path) / "campfyr.db")


def create_app(test_config=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_mapping(
        DATABASE_PATH=_default_database_path(app),
        CHECK_INTERVAL_SECONDS=int(os.getenv("CHECK_INTERVAL_SECONDS", "600")),
        RECREATION_TIMEOUT_SECONDS=int(os.getenv("RECREATION_TIMEOUT_SECONDS", "20")),
        CAMPFYR_USERNAME=os.getenv("CAMPFYR_USERNAME", ""),
        CAMPFYR_PASSWORD=os.getenv("CAMPFYR_PASSWORD", ""),
        MAX_CONTENT_LENGTH=32 * 1024,
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    init_database(app.config["DATABASE_PATH"])

    from .web import web

    app.register_blueprint(web)

    @app.before_request
    def require_optional_basic_auth():
        username = app.config.get("CAMPFYR_USERNAME", "")
        password = app.config.get("CAMPFYR_PASSWORD", "")
        if not username or not password or request.path == "/healthz":
            return None

        supplied = request.authorization
        valid = (
            supplied
            and secrets.compare_digest(supplied.username or "", username)
            and secrets.compare_digest(supplied.password or "", password)
        )
        if not valid:
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Campfyr"'},
            )
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    return app
