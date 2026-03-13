"""Shared fixtures for ltdb tests."""

from __future__ import annotations

import socket
import sqlite3
import threading
import time

import pytest

from web import create_app

# ---------------------------------------------------------------------------
# Minimal in-memory database
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
CREATE TABLE gold   (sid INTEGER, profile TEXT, deriv_json TEXT,
                     mrs TEXT, mrs_json TEXT, dmrs_json TEXT, sent TEXT);
CREATE TABLE typind (typ TEXT, profile TEXT, sid INTEGER,
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


@pytest.fixture
def mem_conn():
    """In-memory SQLite connection with minimal ltdb schema and seed data."""
    conn = sqlite3.connect(":memory:")
    for stmt in SCHEMA.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    for stmt in SEED.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Flask test app
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def flask_app(tmp_path_factory):
    """Flask app wired to a temp db/ directory containing one test grammar."""
    db_dir = tmp_path_factory.mktemp("db")

    # Write a minimal .db file the app can open
    db_path = db_dir / "test-grammar_1.0.db"
    conn = sqlite3.connect(str(db_path))
    for stmt in SCHEMA.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    for stmt in SEED.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    conn.close()

    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
    )

    # Point the app at our temp db directory
    import web.routes as routes_mod
    routes_mod.current_directory = str(db_dir.parent)

    # Create the db/ subdirectory structure the app expects
    (db_dir.parent / "db").mkdir(exist_ok=True)
    import shutil
    shutil.copy(str(db_path), str(db_dir.parent / "db" / "test-grammar_1.0.db"))

    yield app


@pytest.fixture
def client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


# ---------------------------------------------------------------------------
# Live server for Playwright
# ---------------------------------------------------------------------------

def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url(flask_app):
    """Start the Flask app in a background thread; yield its base URL."""
    port = _get_free_port()

    def _run():
        flask_app.run(port=port, use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.5)  # give the server a moment to bind
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
