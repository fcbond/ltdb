"""Initialize Flask Application."""
from flask import Flask, session


def create_app():
    """Construct the core application."""
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "ltdb"
    
    with app.app_context():
        from . import routes

        return app
