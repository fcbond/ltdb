"""Unit tests for route helpers that don't need a live server or ACE."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# App fixture — creates the Flask app and pushes a context so routes.py
# can be imported and its module-level decorators can execute.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app(flask_app):
    """Reuse the session-scoped flask_app so routes (bound at first import) are available."""
    yield flask_app


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
                deriv TEXT, pst TEXT, mrs TEXT, flags TEXT, rule_count INTEGER,
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


# ---------------------------------------------------------------------------
# HOME_BLURB_FILE — an optional deployment-specific intro on the home page,
# so a fork/install (e.g. a curated grammar collection) can brand its own
# instance without hardcoding text into the shared app.
# ---------------------------------------------------------------------------

class TestLoadHomeBlurb:
    def test_unset_env_var_returns_empty(self, app, monkeypatch):
        import web.routes as routes
        monkeypatch.delenv("HOME_BLURB_FILE", raising=False)
        assert routes._load_home_blurb() == ""

    def test_renders_markdown_file_to_html(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        blurb = tmp_path / "blurb.md"
        blurb.write_text("This is the **Curated Collection**.\n")
        monkeypatch.setenv("HOME_BLURB_FILE", str(blurb))
        html = routes._load_home_blurb()
        assert "<strong>Curated Collection</strong>" in html

    def test_missing_file_returns_empty_without_raising(
        self, app, tmp_path, monkeypatch
    ):
        import web.routes as routes
        monkeypatch.setenv("HOME_BLURB_FILE", str(tmp_path / "nonexistent.md"))
        assert routes._load_home_blurb() == ""


class TestHomeBlurbRendering:
    def test_blurb_shown_on_home_page_when_set(self, app, client, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(
            routes, "HOME_BLURB_HTML", "<p>The Curated Collection.</p>"
        )
        html = client.get("/").data.decode()
        assert "The Curated Collection." in html

    def test_no_blurb_block_when_unset(self, app, client, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "HOME_BLURB_HTML", "")
        html = client.get("/").data.decode()
        assert "home-blurb" not in html


# ---------------------------------------------------------------------------
# data-type-href-template: shift-clicking a rendered tree node navigates to
# its type page. On the static mirror that's built from data-grammar/-type
# attributes on an .ltdb-examples ancestor, but on the live app (sent.html,
# type.html's own inline trees, demo.html) there is no such ancestor, and
# the JS used to fall back to a bare client-built "/type/..." path -- which
# silently dropped the app's mount prefix (e.g. "/ltdb") when reverse-proxied,
# since only server-side url_for() (via ProxyFix + X-Forwarded-Prefix, see
# wsgi.py) knows about it. layout.html now renders a server-built url_for()
# template with a placeholder for the JS to substitute into instead.
# ---------------------------------------------------------------------------

class TestTypeHrefTemplate:
    # web/routes.py binds its @app.route(...) decorators via `from flask
    # import current_app as app`, i.e. to whichever Flask instance is
    # active the *first* time the module is imported -- since Python only
    # imports a module once, a *second*, separate create_app() call (as
    # wsgi.py's own module-level `app = create_app()` would be here) never
    # gets any routes registered on it. So this reuses the existing,
    # already-routed `app`/`client` fixtures rather than importing wsgi:app,
    # and simulates ProxyFix's effect (translating an X-Forwarded-Prefix
    # header into the WSGI SCRIPT_NAME variable) directly via
    # environ_overrides -- SCRIPT_NAME-aware url_for() is core
    # Werkzeug/Flask behavior, not something ProxyFix itself implements.
    def _get(self, app, tmp_path, monkeypatch, script_name=""):
        import sqlite3

        import web.routes as routes
        db_dir = tmp_path / "db"
        db_dir.mkdir(exist_ok=True)
        conn = sqlite3.connect(db_dir / "test.db")
        conn.execute(
            "CREATE TABLE gold (profile TEXT, sid INTEGER, deriv TEXT, "
            "mrs TEXT, sent TEXT)"
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        app.config["SECRET_KEY"] = "test"
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["grm"] = "test.db"
            return c.get(
                "/sent/gold/1", environ_overrides={"SCRIPT_NAME": script_name}
            ).data.decode()

    def test_template_has_no_prefix_when_accessed_directly(
        self, app, tmp_path, monkeypatch
    ):
        html = self._get(app, tmp_path, monkeypatch)
        assert 'data-type-href-template="/type/__TYPE__?grm=test.db"' in html

    def test_template_carries_mount_prefix_behind_reverse_proxy(
        self, app, tmp_path, monkeypatch
    ):
        # SCRIPT_NAME="/ltdb" is what ProxyFix's x_prefix=1 (wsgi.py) sets
        # from Apache's X-Forwarded-Prefix header in the live deployment
        # at compling.upol.cz/ltdb
        html = self._get(app, tmp_path, monkeypatch, script_name="/ltdb")
        assert 'data-type-href-template="/ltdb/type/__TYPE__?grm=test.db"' in html


# ---------------------------------------------------------------------------
# Span highlighting on the type page: a lex-type's occurrence should carry
# its word-index span (data-hl-kara/made, for the tree) and, when the
# derivation supplies character offsets, the translated char span
# (data-hl-cfrom/cto, for MRS/DMRS) onto the rendered sentence's divs.
# ---------------------------------------------------------------------------

class TestTypePageSpanHighlighting:
    # a real ERG derivation/MRS pair (build/DBS/ERG_2025.db, ws203/1000001800010),
    # trimmed and re-indexed to word position 2 (third word) of a
    # synthetic 3-word test sentence "It is cross-platform"
    DERIV = (
        '(root_inffrag (0 np_frg_c 0 2 3 (0 hdn_bnp_c 0 2 3 '
        '(0 n_ms_ilr 0 2 3 (0 cross_platform_n1 0 2 3 '
        '("cross-platform" 30 "token [ +FORM \\"cross-platform\\" '
        '+FROM \\"10\\" +TO \\"24\\" ]"))))))'
    )
    MRS = (
        "[ TOP: h0 INDEX: e2 [ e SF: prop ] "
        "RELS: < [ _cross-platform_n_1<10:24> LBL: h1 ARG0: x4 ] > "
        "HCONS: < h0 qeq h1 > ]"
    )

    def _make_db(self, tmp_path):
        import sqlite3

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
                deriv TEXT, pst TEXT, mrs TEXT, flags TEXT, rule_count INTEGER,
                UNIQUE(profile, sid));
            CREATE TABLE sent (sid INTEGER, profile TEXT, wid INTEGER,
                word TEXT, lexid TEXT, UNIQUE(profile, sid, wid));
            CREATE TABLE typind (typ TEXT, profile TEXT, sid INTEGER,
                kara INTEGER, made INTEGER);
            CREATE TABLE hie (child TEXT, parent TEXT);
            INSERT INTO meta VALUES ('GRAMMAR_NAME', 'Test Grammar');
            INSERT INTO types VALUES ('cross_platform_n1', 'n_ms_ilr', '', '', '',
                '', '', 'lex-type', 0, 0, '', '', '', '', '');
        """)
        conn.execute(
            "INSERT INTO lex VALUES (?,?,?,?,?,?,?,?)",
            ("cp1", "cross_platform_n1", "cross-platform",
             "_cross-platform_n_1", None, None, None, None),
        )
        for wid, word in enumerate(["It", "is", "cross-platform"]):
            conn.execute(
                "INSERT INTO sent VALUES (?,?,?,?,?)",
                (1, "ws203", wid, word, "cp1" if wid == 2 else None),
            )
        conn.execute(
            "INSERT INTO gold VALUES (?,?,?,?,?,?,?,?,?)",
            (1, "ws203", "It is cross-platform.", None,
             self.DERIV, None, self.MRS, None, 3),
        )
        conn.commit()
        conn.close()
        return tmp_path

    def test_tree_gets_word_span_attributes(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        self._make_db(tmp_path)
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        app.config["SECRET_KEY"] = "test"
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["grm"] = "test.db"
            html = c.get("/type/cross_platform_n1").data.decode()
        assert 'data-hl-kara="2"' in html
        assert 'data-hl-made="3"' in html

    def test_mrs_dmrs_get_translated_char_span_attributes(
        self, app, tmp_path, monkeypatch
    ):
        import web.routes as routes
        self._make_db(tmp_path)
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        app.config["SECRET_KEY"] = "test"
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["grm"] = "test.db"
            html = c.get("/type/cross_platform_n1").data.decode()
        assert 'data-hl-cfrom="10"' in html
        assert 'data-hl-cto="24"' in html


# ---------------------------------------------------------------------------
# Span highlighting on the standalone /sent/ page, driven by the same
# optional ?kara=&made= query params type.html's sentence-list link (see
# TestTypePageSpanHighlighting above) now points here with.
# ---------------------------------------------------------------------------

class TestSentPageSpanHighlighting:
    DERIV = (
        '(root_inffrag (0 np_frg_c 0 2 3 (0 hdn_bnp_c 0 2 3 '
        '(0 n_ms_ilr 0 2 3 (0 cross_platform_n1 0 2 3 '
        '("cross-platform" 30 "token [ +FORM \\"cross-platform\\" '
        '+FROM \\"10\\" +TO \\"24\\" ]"))))))'
    )
    MRS = (
        "[ TOP: h0 INDEX: e2 [ e SF: prop ] "
        "RELS: < [ _cross-platform_n_1<10:24> LBL: h1 ARG0: x4 ] > "
        "HCONS: < h0 qeq h1 > ]"
    )

    def _make_db(self, tmp_path):
        import sqlite3

        db_dir = tmp_path / "db"
        db_dir.mkdir(exist_ok=True)
        db = db_dir / "test.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE meta (att TEXT, val TEXT);
            CREATE TABLE gold (sid INTEGER, profile TEXT, sent TEXT, comment TEXT,
                deriv TEXT, pst TEXT, mrs TEXT, flags TEXT, rule_count INTEGER,
                UNIQUE(profile, sid));
            CREATE TABLE sent (sid INTEGER, profile TEXT, wid INTEGER,
                word TEXT, lexid TEXT, UNIQUE(profile, sid, wid));
            INSERT INTO meta VALUES ('GRAMMAR_NAME', 'Test Grammar');
        """)
        conn.execute(
            "INSERT INTO gold VALUES (?,?,?,?,?,?,?,?,?)",
            (1, "ws203", "It is cross-platform.", None,
             self.DERIV, None, self.MRS, None, 3),
        )
        for wid, word in enumerate(["It", "is", "cross-platform"]):
            conn.execute(
                "INSERT INTO sent VALUES (?,?,?,?,?)",
                (1, "ws203", wid, word, None),
            )
        conn.commit()
        conn.close()
        return tmp_path

    def _get(self, app, tmp_path, monkeypatch, query=""):
        import web.routes as routes
        self._make_db(tmp_path)
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        app.config["SECRET_KEY"] = "test"
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["grm"] = "test.db"
            return c.get(f"/sent/ws203/1{query}").data.decode()

    def test_without_params_reproduces_page_unchanged(self, app, tmp_path, monkeypatch):
        html = self._get(app, tmp_path, monkeypatch)
        assert "data-hl-kara" not in html
        assert "data-hl-cfrom" not in html
        assert "text-success" not in html
        # sentence text still renders, word-reconstructed same as type.html
        assert "cross-platform" in html

    def test_kara_made_highlight_word_and_tree(self, app, tmp_path, monkeypatch):
        html = self._get(app, tmp_path, monkeypatch, "?kara=2&made=3")
        assert '<span class=\'text-success\'>cross-platform</span>' in html
        assert 'data-hl-kara="2"' in html
        assert 'data-hl-made="3"' in html

    def test_kara_made_translates_to_char_span_for_mrs_dmrs(
        self, app, tmp_path, monkeypatch
    ):
        html = self._get(app, tmp_path, monkeypatch, "?kara=2&made=3")
        assert 'data-hl-cfrom="10"' in html
        assert 'data-hl-cto="24"' in html
