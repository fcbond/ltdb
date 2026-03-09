"""Initialize Flask Application."""

import os
import secrets
import sys

from flask import Flask


def create_app():
    """Construct the core application."""
    app = Flask(__name__, template_folder="templates")
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        secret = secrets.token_hex(24)
        print(
            "WARNING: SECRET_KEY not set; sessions will not survive restarts",
            file=sys.stderr,
        )
    app.secret_key = secret

    with app.app_context():
        from . import routes  # noqa: F401
        from .db import close_db

        app.teardown_appcontext(close_db)

        return app
