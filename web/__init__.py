"""Initialize Flask Application."""
import os

from flask import Flask, session


def create_app():
    """Construct the core application."""
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "ltdb"
    # URL of a grew-match instance serving this grammar's exported
    # corpora (see doc/grew-match.md); the nav link is hidden if unset
    app.config["GREW_MATCH_URL"] = os.environ.get("LTDB_GREW_MATCH_URL", "")
    
    with app.app_context():
        from . import routes

        return app
