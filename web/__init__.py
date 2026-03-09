"""Initialize Flask Application."""
from flask import Flask


def create_app():
    """Construct the core application."""
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "ltdb"

    with app.app_context():
        from . import routes
        from .db import close_db
        app.teardown_appcontext(close_db)

        return app
