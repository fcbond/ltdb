"""App entry point."""

import os

from werkzeug.middleware.proxy_fix import ProxyFix

from web import create_app

app = create_app()
# Trust one proxy (Apache) and respect X-Forwarded-Prefix for sub-path serving
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

if __name__ == "__main__":
    # Development only. Production should use gunicorn/systemd.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", debug=debug)
