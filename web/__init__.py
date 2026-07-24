"""Initialize Flask Application."""

import os
import secrets
import sys
import threading

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
    # URL of a grew-match instance serving the exported corpora
    # (see doc/grew-match.md); the nav link is hidden if unset
    app.config["GREW_MATCH_URL"] = os.environ.get("LTDB_GREW_MATCH_URL", "")

    with app.app_context():
        from . import routes  # noqa: F401
        from .db import close_db, warm_caches

        app.teardown_appcontext(close_db)
        _db_dir = os.path.dirname(__file__)
        threading.Thread(target=warm_caches, args=(_db_dir,), daemon=True).start()

        return app
