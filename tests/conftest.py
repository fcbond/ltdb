"""Shared fixtures for ltdb tests."""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import threading
import time

import pytest

from web import create_app

# ---------------------------------------------------------------------------
# Minimal in-memory database schema and seed data
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE meta   (att TEXT, val TEXT);
CREATE TABLE types  (typ TEXT PRIMARY KEY, parents TEXT, children TEXT,
                     cat TEXT, val TEXT, cont TEXT, definition TEXT,
                     status TEXT, arity INTEGER, head INTEGER,
                     lname TEXT, description TEXT, criteria TEXT,
                     reference TEXT, todo TEXT);
CREATE TABLE tdl    (typ TEXT, src TEXT, line INTEGER, kind TEXT,
                     tdl TEXT, docstring TEXT);
CREATE TABLE lex    (lexid TEXT PRIMARY KEY, typ TEXT, orth TEXT,
                     pred TEXT, altpred TEXT, carg TEXT, altcarg TEXT,
                     docstring TEXT);
CREATE TABLE hie    (child TEXT, parent TEXT);
CREATE TABLE typfreq  (typ TEXT PRIMARY KEY, freq INTEGER);
CREATE TABLE lexfreq  (lexid TEXT, word TEXT, freq INTEGER);
CREATE TABLE sent   (sid INTEGER, profile TEXT, wid INTEGER,
                     word TEXT, lexid TEXT);
CREATE TABLE gold   (sid INTEGER, profile TEXT, sent TEXT,
                     comment TEXT, deriv TEXT, pst TEXT, mrs TEXT, flags TEXT,
                     UNIQUE(profile, sid));
CREATE TABLE typind (typ TEXT, profile TEXT, sid INTEGER,
                     kara INTEGER, made INTEGER);
CREATE TABLE lexind (lexid TEXT, profile TEXT, sid INTEGER,
                     kara INTEGER, made INTEGER);
"""

SEED = """
INSERT INTO meta VALUES ('GRAMMAR_NAME', 'Test Grammar');
INSERT INTO meta VALUES ('WEBSITE', 'https://example.com');
INSERT INTO meta VALUES ('LICENSE', 'MIT');
INSERT INTO meta VALUES ('EXAMPLES', '["The dog barks.", "Who barked?"]');

INSERT INTO types VALUES ('noun-le',  'noun', '',   'noun', '', '', '', 'lex-type',  0, 0, 'noun',   '', '', '', '');
INSERT INTO types VALUES ('verb-le',  'verb', '',   'verb', '', '', '', 'lex-type',  0, 0, 'verb',   '', '', '', '');
INSERT INTO types VALUES ('hd-cmp_c', 'rule', '',   '',     '', '', '', 'rule',      2, 1, '',       '', '', '', '');
INSERT INTO types VALUES ('root',     '',     '',   '',     '', '', '', 'root',      0, 0, '',       '', '', '', '');
INSERT INTO types VALUES ('noun',     'avm',  'noun-le', '', '', '', '', 'type',     0, 0, '',       '', '', '', '');

INSERT INTO tdl VALUES ('noun-le', 'nouns.tdl', 1, 'type', 'noun-le := noun.',
    '<ex>The dog barks.\n<nex>Dog the barks.\n<mex>Dog barks.');
INSERT INTO tdl VALUES ('verb-le', 'verbs.tdl', 5, 'type', 'verb-le := verb.',
    'A verb lexical type.');

INSERT INTO lex VALUES ('dog_n1',  'noun-le', 'dog',  '_dog_n_1', NULL, NULL, NULL, NULL);
INSERT INTO lex VALUES ('bark_v1', 'verb-le', 'bark', '_bark_v_1', NULL, NULL, NULL, NULL);

INSERT INTO hie VALUES ('noun-le', 'noun');
INSERT INTO hie VALUES ('noun',    'avm');
INSERT INTO hie VALUES ('verb-le', 'verb');

INSERT INTO typfreq VALUES ('noun-le', 42);
INSERT INTO typfreq VALUES ('verb-le', 17);

INSERT INTO lexfreq VALUES ('dog_n1',  'dog',  10);
INSERT INTO lexfreq VALUES ('dog_n1',  'dogs',  5);
INSERT INTO lexfreq VALUES ('bark_v1', 'bark',  7);

INSERT INTO sent VALUES (1, 'gold', 0, 'The',  NULL);
INSERT INTO sent VALUES (1, 'gold', 1, 'dog',  'dog_n1');
INSERT INTO sent VALUES (1, 'gold', 2, 'barks', 'bark_v1');
"""


def _init_db(conn):
    """Populate a SQLite connection with the minimal test schema and seed data."""
    for sql in (SCHEMA, SEED):
        for stmt in sql.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
    conn.commit()


@pytest.fixture
def mem_conn():
    """In-memory SQLite connection with minimal ltdb schema and seed data."""
    conn = sqlite3.connect(":memory:")
    _init_db(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Flask test app
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def flask_app(tmp_path_factory):
    """Flask app wired to a temp db/ directory containing one test grammar."""
    base_dir = tmp_path_factory.mktemp("ltdb")
    db_subdir = base_dir / "db"
    db_subdir.mkdir()

    conn = sqlite3.connect(str(db_subdir / "test-grammar_1.0.db"))
    _init_db(conn)
    conn.close()

    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    import web.routes as routes_mod
    routes_mod.current_directory = str(base_dir)

    yield app


@pytest.fixture
def client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


@pytest.fixture
def grm_client(flask_app):
    """Flask test client with the test grammar pre-selected in the session."""
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["grm"] = "test-grammar_1.0.db"
    return c


# ---------------------------------------------------------------------------
# Live server for Playwright
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def live_server_url(flask_app):
    """Start the Flask app in a background thread; yield its base URL."""
    port = _free_port()

    def _run():
        flask_app.run(port=port, use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.5)
    yield f"http://localhost:{port}"


@pytest.fixture
def page(playwright, live_server_url):
    """Playwright page pointed at the live test server."""
    browser = playwright.chromium.launch()
    context = browser.new_context(base_url=live_server_url)
    pg = context.new_page()
    yield pg
    context.close()
    browser.close()


# ---------------------------------------------------------------------------
# Gunicorn server for integration tests
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Grammar/sentence constants shared across test modules
GRAMMAR = "ERG_2025.db"

_DAT = os.path.join(_REPO_ROOT, "web", "db", GRAMMAR[:-3] + ".dat")
needs_dat = pytest.mark.skipif(
    not os.path.exists(_DAT),
    reason=f"{GRAMMAR[:-3]}.dat not found — run: python scripts/grm2db.py --ace",
)

SENTENCES = [
    "The dog barked.",
    "Dogs bark.",
    "Kim likes Sandy.",
    "It is raining.",
    "Every cat sees a dog.",
    "The old man saw the young woman.",
    "She gave him a book.",
    "The cat sat on the mat.",
    "Abrams knows that Browne left.",
    "The manager hired a new employee.",
]

# A long, syntactically complex sentence to exercise ACE timeouts and
# robustness under heavy parse load.
LONG_SENTENCE = (
    "The distinguished professor of linguistics who had been studying the "
    "intricate syntactic structures of natural language for many decades "
    "argued convincingly that the children who the teachers that the "
    "administrators the school board hired supervised taught were remarkably "
    "talented and would one day make significant contributions to the field."
)


@pytest.fixture(scope="session")
def gunicorn_url():
    """Start a gunicorn server for the session; yield its base URL."""
    port = _free_port()
    env = {**os.environ, "SECRET_KEY": "test-secret-not-for-production"}

    proc = subprocess.Popen(
        [
            ".venv/bin/gunicorn",
            "--workers=4",
            "--worker-class=sync",
            f"--bind=127.0.0.1:{port}",
            "--timeout=60",
            "wsgi:app",
        ],
        cwd=_REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if not _wait_for_port(port, timeout=20):
        proc.terminate()
        stderr = proc.stderr.read().decode()
        pytest.fail(f"gunicorn did not start within 20s:\n{stderr}")

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(gunicorn_url):
    """Override pytest-playwright base_url with our gunicorn server."""
    return gunicorn_url
