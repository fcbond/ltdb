"""Tests for Flask routes in web/routes.py."""

from __future__ import annotations

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


class TestGrammarPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/grammar.html")
        assert resp.status_code == 302

    def test_with_session_returns_200(self, grm_client):
        assert grm_client.get("/grammar.html").status_code == 200

    def test_grammar_name_in_response(self, grm_client):
        assert b"Test Grammar" in grm_client.get("/grammar.html").data


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
        resp = grm_client.post("/parse", data={"input": "The dog barks."})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["readings"] == 1
        assert data["input"] == "The dog barks."


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
