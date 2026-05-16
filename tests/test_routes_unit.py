"""Unit tests for route helpers that don't need a live server or ACE."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# App fixture — creates the Flask app and pushes a context so routes.py
# can be imported and its module-level decorators can execute.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    from web import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    ctx = _app.app_context()
    ctx.push()
    yield _app
    ctx.pop()


# ---------------------------------------------------------------------------
# dat_path_for — zero-size and missing file handling
# ---------------------------------------------------------------------------

class TestDatPathFor:
    def test_missing_dat_returns_none(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        (tmp_path / "db").mkdir()
        assert routes.dat_path_for("ERG_2025.db") is None

    def test_zero_size_dat_returns_none(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        (tmp_path / "db").mkdir()
        (tmp_path / "db" / "ERG_2025.dat").touch()          # 0 bytes
        assert routes.dat_path_for("ERG_2025.db") is None

    def test_non_empty_dat_returns_path(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        dat = db_dir / "ERG_2025.dat"
        dat.write_bytes(b"\x00" * 1024)
        assert routes.dat_path_for("ERG_2025.db") == str(dat)

    def test_strips_db_suffix(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        (tmp_path / "db").mkdir()
        (tmp_path / "db" / "GG.dat").write_bytes(b"data")
        assert routes.dat_path_for("GG.db") is not None


# ---------------------------------------------------------------------------
# MRS raw-string fallback when pydelphin cannot parse ACE's MRS output
# ---------------------------------------------------------------------------

_RAW_MRS = "[ TOP: h0 INDEX: e2 [ e SF: prop ] RELS: < > HCONS: < h0 qeq e2 > ]"


def _make_ace_result(*, mrs_raises=False, raw_mrs=None):
    result = MagicMock()
    if mrs_raises:
        result.mrs.side_effect = Exception("MRSSyntaxError: expected a symbol")
    else:
        result.mrs.return_value = MagicMock()
    result.get.side_effect = lambda key, default=None: (
        raw_mrs if key == "mrs" else default
    )
    result.result.return_value = None
    return result


@pytest.fixture()
def client(app, tmp_path, monkeypatch):
    """Test client with a fake non-empty .dat for grammar 'fake.db'."""
    import web.routes as routes
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    (db_dir / "fake.dat").write_bytes(b"x" * 512)
    monkeypatch.setattr(routes, "current_directory", str(tmp_path))
    return app.test_client()


def _post_parse(client, *, grm="fake.db", sentence="test", mrs="json"):
    return client.post(
        "/parse",
        data={
            "input": sentence,
            "grm": grm,
            "results": 1,
            "derivation": "null",
            "mrs": mrs,
            "dmrs": "null",
        },
    )


class TestMrsRawFallback:
    def test_fallback_sets_mrs_str_on_pydelphin_failure(self, client):
        """When result.mrs() raises, the raw ACE string is used as mrs_str."""
        mock_result = _make_ace_result(mrs_raises=True, raw_mrs=_RAW_MRS)
        mock_response = MagicMock()
        mock_response.results.return_value = [mock_result]

        with patch("delphin.ace.ACEParser") as MockParser, \
             patch("web.routes.find_ace", return_value="/bin/ace"):
            MockParser.return_value.__enter__.return_value.interact.return_value = (
                mock_response
            )
            MockParser.return_value.__exit__.return_value = False
            r = _post_parse(client)

        data = r.get_json()
        assert r.status_code == 200
        assert len(data["errors"]) == 1
        assert "MRSSyntaxError" in data["errors"][0]
        assert data["results"][0].get("mrs_str") == _RAW_MRS

    def test_no_fallback_when_raw_mrs_absent(self, client):
        """When result.get('mrs') is None there is no mrs_str in the response."""
        mock_result = _make_ace_result(mrs_raises=True, raw_mrs=None)
        mock_response = MagicMock()
        mock_response.results.return_value = [mock_result]

        with patch("delphin.ace.ACEParser") as MockParser, \
             patch("web.routes.find_ace", return_value="/bin/ace"):
            MockParser.return_value.__enter__.return_value.interact.return_value = (
                mock_response
            )
            MockParser.return_value.__exit__.return_value = False
            r = _post_parse(client)

        data = r.get_json()
        assert r.status_code == 200
        assert "mrs_str" not in data["results"][0]

    def test_successful_pydelphin_parse_no_errors(self, client):
        """When pydelphin succeeds, errors list is empty and mrs_str is set."""
        mrsjson_encoded = (
            '{"top": "h0", "index": "e2", "relations": [], "constraints": []}'
        )
        mock_result = _make_ace_result(mrs_raises=False)
        mock_response = MagicMock()
        mock_response.results.return_value = [mock_result]

        with patch("delphin.ace.ACEParser") as MockParser, \
             patch("delphin.codecs.simplemrs.encode", return_value=_RAW_MRS), \
             patch("delphin.codecs.mrsjson.encode", return_value=mrsjson_encoded), \
             patch("web.routes.find_ace", return_value="/bin/ace"):
            MockParser.return_value.__enter__.return_value.interact.return_value = (
                mock_response
            )
            MockParser.return_value.__exit__.return_value = False
            r = _post_parse(client)

        data = r.get_json()
        assert r.status_code == 200
        assert data["errors"] == []
        assert data["results"][0]["mrs_str"] == _RAW_MRS


# ---------------------------------------------------------------------------
# get_doctest — DB query helper
# ---------------------------------------------------------------------------

class TestGetDoctest:
    def _make_db_with_doctest(self, tmp_path):
        """Create a minimal grammar DB with all tables required by _render_type."""
        import sqlite3

        # Use 'rule' status so the route doesn't try to query the lex table
        db_dir = tmp_path / "db"
        db_dir.mkdir(exist_ok=True)
        db = db_dir / "test.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE types (typ TEXT PRIMARY KEY, parents TEXT, children TEXT,
                cat TEXT, val TEXT, cont TEXT, definition TEXT, status TEXT,
                arity INTEGER, head INTEGER, lname TEXT, description TEXT,
                criteria TEXT, reference TEXT, todo TEXT);
            CREATE TABLE tdl (typ TEXT, src TEXT, line INTEGER, kind TEXT,
                tdl TEXT, docstring TEXT);
            CREATE TABLE lex (lexid TEXT PRIMARY KEY, typ TEXT, orth TEXT,
                pred TEXT, altpred TEXT, carg TEXT, altcarg TEXT, docstring TEXT);
            CREATE TABLE meta (att TEXT, val TEXT);
            CREATE TABLE doctest (typ TEXT NOT NULL, sent TEXT NOT NULL,
                kind TEXT NOT NULL, wf INTEGER NOT NULL, n_parses INTEGER,
                type_found INTEGER, pass INTEGER NOT NULL, verdict TEXT NOT NULL);
            CREATE TABLE lexfreq (lexid TEXT, word TEXT, freq INTEGER);
            CREATE TABLE typfreq (typ TEXT, freq INTEGER);
            CREATE TABLE gold (sid INTEGER, profile TEXT, sent TEXT, comment TEXT,
                deriv TEXT, pst TEXT, mrs TEXT, flags TEXT,
                UNIQUE(profile, sid));
            CREATE TABLE sent (sid INTEGER, profile TEXT, wid INTEGER,
                word TEXT, lexid TEXT, UNIQUE(profile, sid, wid));
            CREATE TABLE typind (typ TEXT, profile TEXT, sid INTEGER,
                kara INTEGER, made INTEGER);
            CREATE TABLE hie (child TEXT, parent TEXT);
            INSERT INTO meta VALUES ('GRAMMAR_NAME', 'Test Grammar');
            INSERT INTO types VALUES ('hd-cmp_u_c', '', '', '', '', '', '',
                'rule', 0, 0, '', 'Head-complement rule.', '', '', '');
            INSERT INTO tdl VALUES ('hd-cmp_u_c', 'gram.tdl', 10,
                'TypeDefinition', 'hd-cmp_u_c := headed-phrase.', '');
            INSERT INTO doctest VALUES
                ('hd-cmp_u_c', 'The cat sat.', 'ex', 1, 3, 1, 1, 'PASS'),
                ('hd-cmp_u_c', 'Cat the sat.', 'nex', 0, 0, 0, 1, 'PASS'),
                ('hd-cmp_u_c', 'Sat.', 'ex', 1, 0, 0, 0, 'FAIL-no-parse');
        """)
        conn.commit()
        conn.close()
        return tmp_path

    def test_get_doctest_returns_summary_and_examples(self, app, tmp_path):
        import sqlite3
        from web.db import get_doctest
        self._make_db_with_doctest(tmp_path)
        conn = sqlite3.connect(str(tmp_path / "db" / "test.db"))
        summary, examples = get_doctest(conn, "hd-cmp_u_c")
        assert summary is not None
        assert summary["ex"]["total"] == 2
        assert summary["ex"]["pass"] == 1
        assert summary["ex"]["fail"] == {"FAIL-no-parse": 1}
        assert summary["nex"]["total"] == 1
        assert summary["nex"]["pass"] == 1
        assert len(examples) == 3
        conn.close()

    def test_get_doctest_missing_type_returns_none(self, app, tmp_path):
        import sqlite3
        from web.db import get_doctest
        self._make_db_with_doctest(tmp_path)
        conn = sqlite3.connect(str(tmp_path / "db" / "test.db"))
        summary, examples = get_doctest(conn, "nonexistent")
        assert summary is None
        assert examples is None
        conn.close()

    def test_get_doctest_missing_table_returns_none(self, app, tmp_path):
        import sqlite3
        from web.db import get_doctest
        db = tmp_path / "no_table.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE foo (x TEXT)")
        conn.commit()
        summary, examples = get_doctest(conn, "anything")
        assert summary is None
        assert examples is None
        conn.close()

    def test_type_page_includes_doctest_section(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        self._make_db_with_doctest(tmp_path)
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        app.config["SECRET_KEY"] = "test"
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["grm"] = "test.db"
            r = c.get("/type/hd-cmp_u_c")
            html = r.data.decode()
        assert r.status_code == 200
        assert "Docstring Tests" in html
        assert "&lt;ex&gt;" in html
        assert "PASS" in html
        assert "FAIL-no-parse" in html
