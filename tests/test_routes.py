"""Tests for Flask routes in web/routes.py."""

from __future__ import annotations

import os
import sqlite3

import pytest


class TestHomePage:
    def test_get_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_lists_grammar(self, client):
        resp = client.get("/")
        assert b"test-grammar" in resp.data

    def test_grm_param_sets_session_and_redirects(self, client):
        resp = client.get("/?grm=test-grammar_1.0")
        assert resp.status_code == 302
        assert "/grammar" in resp.headers["Location"]

    def test_grm_param_without_extension(self, client):
        resp = client.get("/?grm=test-grammar_1.0")
        assert resp.status_code == 302

    def test_post_selects_grammar(self, client):
        resp = client.post("/", data={"grm": "test-grammar_1.0.db"})
        assert resp.status_code == 302
        assert "/grammar" in resp.headers["Location"]


class TestSentPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/sent/gold/1")
        assert resp.status_code == 302

    def test_loads_renderer_scripts(self, grm_client):
        # ltdb-examples.js drives the tree/DMRS/MRS rendering; without it
        # the page shows only the sentence text
        resp = grm_client.get("/sent/gold/1")
        assert resp.status_code == 200
        assert b"js/ltdb-tree.js" in resp.data
        assert b"js/ltdb-mrs.js" in resp.data
        assert b"js/ltdb-examples.js" in resp.data


class TestGrammarPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/grammar.html")
        assert resp.status_code == 302

    def test_with_session_returns_200(self, grm_client):
        assert grm_client.get("/grammar.html").status_code == 200

    def test_grammar_name_in_response(self, grm_client):
        assert b"Test Grammar" in grm_client.get("/grammar.html").data


class TestBuildLogs:
    """Build-log download links on /grammar.html (see routes.download_log
    and _available_logs); logs are only shown/served when the
    corresponding file exists next to the database."""

    def test_no_links_without_log_files(self, grm_client):
        assert b"/log/" not in grm_client.get("/grammar.html").data

    def test_link_shown_and_download_works_when_log_exists(self, grm_client):
        import web.routes as routes_mod

        db_dir = os.path.join(routes_mod.current_directory, "db")
        log_path = os.path.join(db_dir, "test-grammar_1.0-grew.log")
        with open(log_path, "w") as f:
            f.write("ERROR derivation gold/1 unreadable: bad token\n")
        try:
            data = grm_client.get("/grammar.html").data
            assert b"/log/test-grammar_1.0.db/grew" in data
            resp = grm_client.get("/log/test-grammar_1.0.db/grew")
            assert resp.status_code == 200
            assert b"unreadable" in resp.data
        finally:
            os.unlink(log_path)

    def test_missing_log_returns_404(self, grm_client):
        resp = grm_client.get("/log/test-grammar_1.0.db/grew")
        assert resp.status_code == 404

    def test_unknown_kind_returns_404(self, grm_client):
        resp = grm_client.get("/log/test-grammar_1.0.db/bogus")
        assert resp.status_code == 404

    def test_path_traversal_in_grm_returns_404(self, grm_client):
        resp = grm_client.get("/log/..%2f..%2fetc%2fpasswd/grew")
        assert resp.status_code == 404

    def test_no_links_on_static_mirror_page(self, client):
        # the mirror is frozen to static HTML with no backend to serve
        # /log/..., so _render_grammar deliberately omits "logs"
        import web.routes as routes_mod

        db_dir = os.path.join(routes_mod.current_directory, "db")
        log_path = os.path.join(db_dir, "test-grammar_1.0-grew.log")
        with open(log_path, "w") as f:
            f.write("ERROR whatever\n")
        try:
            resp = client.get("/ltdb/test-grammar_1.0/grammar.html")
            assert resp.status_code == 200
            assert b"/log/" not in resp.data
        finally:
            os.unlink(log_path)


class TestConditionalNav:
    """Docstring Tests / Demo tabs and the <ex> column only appear
    when the grammar has doctest rows / a compiled .dat file."""

    def test_tabs_hidden_without_doctests_or_dat(self, grm_client):
        data = grm_client.get("/grammar.html").data
        assert b"Docstring Tests" not in data
        assert b">Demo<" not in data

    def test_ex_column_hidden_without_doctests(self, client):
        assert b"&lt;ex&gt;" not in client.get("/").data

    def test_tabs_and_ex_column_shown_with_doctests_and_dat(self, grm_client):
        import web.routes as routes_mod

        db_dir = os.path.join(routes_mod.current_directory, "db")
        dbfile = os.path.join(db_dir, "test-grammar_1.0.db")
        dat = os.path.join(db_dir, "test-grammar_1.0.dat")
        conn = sqlite3.connect(dbfile)
        with conn:
            conn.execute("CREATE TABLE doctest (typ TEXT)")
            conn.execute("INSERT INTO doctest VALUES ('noun-le')")
        conn.close()
        with open(dat, "w") as f:
            f.write("x")
        try:
            data = grm_client.get("/grammar.html").data
            assert b"Docstring Tests" in data
            assert b">Demo<" in data
            assert b"&lt;ex&gt;" in grm_client.get("/").data
        finally:
            conn = sqlite3.connect(dbfile)
            with conn:
                conn.execute("DROP TABLE doctest")
            conn.close()
            os.unlink(dat)


class TestRulesPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/rules.html")
        assert resp.status_code == 302

    def test_with_session_returns_200(self, grm_client):
        assert grm_client.get("/rules.html").status_code == 200

    def test_rule_type_in_response(self, grm_client):
        assert b"hd-cmp_c" in grm_client.get("/rules.html").data


class TestLtypesPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/ltypes.html")
        assert resp.status_code == 302

    def test_with_session_returns_200(self, grm_client):
        assert grm_client.get("/ltypes.html").status_code == 200

    def test_lex_types_in_response(self, grm_client):
        assert b"noun-le" in grm_client.get("/ltypes.html").data


class TestTypePage:
    def test_without_session_redirects(self, client):
        resp = client.get("/type/noun-le")
        assert resp.status_code == 302

    def test_known_type_returns_200(self, grm_client):
        assert grm_client.get("/type/noun-le").status_code == 200

    def test_type_name_in_response(self, grm_client):
        assert b"noun-le" in grm_client.get("/type/noun-le").data

    def test_unknown_type_returns_200(self, grm_client):
        assert grm_client.get("/type/no-such-type").status_code == 200

    def test_lex_type_shows_lexids(self, grm_client):
        assert b"dog" in grm_client.get("/type/noun-le").data

    def test_tdl_shown_for_type(self, grm_client):
        assert b"noun" in grm_client.get("/type/noun-le").data

    def test_rule_type_page(self, grm_client):
        assert grm_client.get("/type/hd-cmp_c").status_code == 200

    def test_root_type_page(self, grm_client):
        assert grm_client.get("/type/root").status_code == 200


class TestSearchPage:
    def test_without_session_redirects(self, client):
        resp = client.post("/search", data={"search": "dog"})
        assert resp.status_code == 302

    def test_search_returns_200(self, grm_client):
        assert grm_client.post("/search", data={"search": "dog"}).status_code == 200

    def test_search_finds_lemma(self, grm_client):
        assert b"dog" in grm_client.post("/search", data={"search": "dog"}).data

    def test_search_no_results(self, grm_client):
        assert grm_client.post("/search", data={"search": "zzznomatch"}).status_code == 200

    def test_search_type_glob(self, grm_client):
        assert b"noun" in grm_client.post("/search", data={"search": "noun*"}).data


class TestParseRoute:
    def test_no_grammar_returns_400(self, client):
        resp = client.post("/parse", data={"input": "The dog barks."})
        assert resp.status_code == 400
        assert b"grammar" in resp.data.lower()

    def test_no_dat_file_returns_400(self, grm_client):
        resp = grm_client.post("/parse", data={"input": "The dog barks."})
        assert resp.status_code == 400
        assert b".dat" in resp.data or b"compiled" in resp.data.lower()

    def test_no_input_returns_400(self, grm_client, monkeypatch):
        monkeypatch.setattr("web.routes.dat_path_for", lambda grm: "/fake/path.dat")
        resp = grm_client.post("/parse", data={"input": ""})
        assert resp.status_code == 400
        assert b"input" in resp.data.lower()

    def test_invalid_results_param_returns_400(self, grm_client, monkeypatch):
        monkeypatch.setattr("web.routes.dat_path_for", lambda grm: "/fake/path.dat")
        resp = grm_client.post("/parse", data={"input": "test", "results": "notanint"})
        assert resp.status_code == 400
        assert "Results must be" in resp.get_json()["error"]

    def test_successful_parse_returns_json(self, grm_client, monkeypatch):
        import delphin.ace as ace_mod

        class _FakeResult:
            def derivation(self):
                raise RuntimeError("no derivation")
            def mrs(self):
                raise RuntimeError("no mrs")

        class _FakeResponse:
            def results(self):
                return [_FakeResult()]

        monkeypatch.setattr(ace_mod, "parse", lambda *a, **kw: _FakeResponse())
        monkeypatch.setattr("web.routes.dat_path_for", lambda grm: "/fake/path.dat")
        monkeypatch.setattr("web.routes.find_ace", lambda: "/fake/ace")
        resp = grm_client.post("/parse", data={"input": "The dog barks."})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["readings"] == 1
        assert data["input"] == "The dog barks."

    def test_parse_uses_udx_and_returns_raw_derivation(
        self, grm_client, monkeypatch
    ):
        import delphin.ace as ace_mod

        class _FakeDeriv:
            def to_dict(self):
                return {"entity": "root"}

            def to_udx(self):
                return '(root (1 dog_n1@n_-_c_le 0 0 1 ("dog")))'

        class _FakeResult:
            def derivation(self):
                return _FakeDeriv()

        class _FakeResponse:
            def results(self):
                return [_FakeResult()]

        seen = {}

        def fake_parse(dat, text, **kwargs):
            seen.update(kwargs)
            return _FakeResponse()

        monkeypatch.setattr(ace_mod, "parse", fake_parse)
        monkeypatch.setattr("web.routes.dat_path_for", lambda grm: "/fake/path.dat")
        monkeypatch.setattr("web.routes.find_ace", lambda: "/fake/ace")
        resp = grm_client.post(
            "/parse", data={"input": "The dog barks.", "derivation": "json"}
        )
        assert resp.status_code == 200
        # types come from --udx=all; the root from --rooted-derivations
        assert "--udx=all" in seen["cmdargs"]
        assert "--rooted-derivations" in seen["cmdargs"]
        result = resp.get_json()["results"][0]
        assert result["derivation"] == {"entity": "root"}
        assert result["derivation_str"] == '(root (1 dog_n1@n_-_c_le 0 0 1 ("dog")))'


class TestGenerateRoute:
    def test_no_grammar_returns_400(self, client):
        resp = client.post("/generate", data={"mrs": "{}"})
        assert resp.status_code == 400

    def test_no_dat_file_returns_400(self, grm_client):
        resp = grm_client.post("/generate", data={"mrs": "{}"})
        assert resp.status_code == 400

    def test_no_mrs_returns_400(self, grm_client, monkeypatch):
        monkeypatch.setattr("web.routes.dat_path_for", lambda grm: "/fake/path.dat")
        resp = grm_client.post("/generate", data={})
        assert resp.status_code == 400
        assert b"MRS" in resp.data or b"mrs" in resp.data.lower()


class TestDemoPage:
    def test_demo_returns_200(self, client):
        assert client.get("/demo").status_code == 200

    def test_can_generate_reflects_meta_flag(self, client):
        """The Generate button is gated client-side on _canGenerate, which
        must be True only for grammars with a CAN_GENERATE meta row."""
        import web.routes as routes_mod

        db_dir = os.path.join(routes_mod.current_directory, "db")
        dbfile = os.path.join(db_dir, "test-grammar_1.0.db")
        dat = os.path.join(db_dir, "test-grammar_1.0.dat")
        conn = sqlite3.connect(dbfile)
        with conn:
            conn.execute("INSERT INTO meta VALUES ('CAN_GENERATE', '1')")
        conn.close()
        with open(dat, "w") as f:
            f.write("x")
        try:
            data = client.get("/demo").data.decode()
            assert '"test-grammar_1.0.db": true' in data
        finally:
            conn = sqlite3.connect(dbfile)
            with conn:
                conn.execute("DELETE FROM meta WHERE att = 'CAN_GENERATE'")
            conn.close()
            os.unlink(dat)

    def test_can_generate_false_without_meta_flag(self, client):
        import web.routes as routes_mod

        db_dir = os.path.join(routes_mod.current_directory, "db")
        dat = os.path.join(db_dir, "test-grammar_1.0.dat")
        with open(dat, "w") as f:
            f.write("x")
        try:
            data = client.get("/demo").data.decode()
            assert '"test-grammar_1.0.db": false' in data
        finally:
            os.unlink(dat)


class TestSummaryCache:
    def test_cache_invalidates_on_new_db(self, flask_app, tmp_path):
        import web.routes as routes_mod
        from tests.conftest import _init_db

        client = flask_app.test_client()
        client.get("/")  # prime the cache

        db_dir = routes_mod.current_directory
        new_db = tmp_path / "extra_1.0.db"
        conn = sqlite3.connect(str(new_db))
        _init_db(conn)
        conn.close()

        import shutil
        dest = routes_mod.current_directory + "/db/extra_1.0.db"
        shutil.copy(str(new_db), dest)
        try:
            resp = client.get("/")
            assert b"extra_1.0" in resp.data
        finally:
            import os
            os.unlink(dest)

    def test_cache_hit_served_without_requery(self, client, monkeypatch):
        import web.routes as routes_mod
        client.get("/")  # prime cache
        call_count = []
        original = routes_mod.get_short_summary
        monkeypatch.setattr(routes_mod, "get_short_summary",
                            lambda *a, **kw: call_count.append(1) or original(*a, **kw))
        client.get("/")
        assert call_count == [], "get_short_summary should not be called on cache hit"


class TestGrmParam:
    def test_invalid_grm_ignored(self, client):
        assert client.get("/?grm=nonexistent_grammar").status_code == 200

    def test_grm_without_db_extension_works(self, client):
        assert client.get("/?grm=test-grammar_1.0").status_code == 302

    def test_grm_with_db_extension_works(self, client):
        assert client.get("/?grm=test-grammar_1.0.db").status_code == 302


class TestGrmSecurity:
    """Path traversal and injection rejection via sanitize_grm."""

    @pytest.mark.parametrize("payload", [
        "../../../etc/passwd",
        "../../web/db/test-grammar_1.0",
        "/etc/passwd",
        "foo/bar.db",
        "foo\\bar.db",
        "",
        "   ",
    ])
    def test_traversal_get_rejected(self, client, payload):
        resp = client.get(f"/?grm={payload}")
        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert "grm" not in sess or sess.get("grm") != payload

    @pytest.mark.parametrize("payload", [
        "../../../etc/passwd",
        "/etc/passwd",
        "foo/bar.db",
    ])
    def test_traversal_post_rejected(self, client, payload):
        client.post("/", data={"grm": payload})
        with client.session_transaction() as sess:
            assert sess.get("grm") != payload
