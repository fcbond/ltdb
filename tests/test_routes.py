"""Tests for Flask routes in web/routes.py."""

from __future__ import annotations

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
        # before_request sets session; home() sees grm param and redirects
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

    def test_with_session_returns_200(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.get("/grammar.html")
        assert resp.status_code == 200

    def test_grammar_name_in_response(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.get("/grammar.html")
        assert b"Test Grammar" in resp.data


class TestRulesPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/rules.html")
        assert resp.status_code == 302

    def test_with_session_returns_200(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.get("/rules.html")
        assert resp.status_code == 200

    def test_rule_type_in_response(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.get("/rules.html")
        assert b"hd-cmp_c" in resp.data


class TestLtypesPage:
    def test_without_session_redirects(self, client):
        resp = client.get("/ltypes.html")
        assert resp.status_code == 302

    def test_with_session_returns_200(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.get("/ltypes.html")
        assert resp.status_code == 200

    def test_lex_types_in_response(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.get("/ltypes.html")
        assert b"noun-le" in resp.data


class TestTypePage:
    def _set_session(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"

    def test_without_session_redirects(self, client):
        resp = client.get("/type/noun-le")
        assert resp.status_code == 302

    def test_known_type_returns_200(self, client):
        self._set_session(client)
        resp = client.get("/type/noun-le")
        assert resp.status_code == 200

    def test_type_name_in_response(self, client):
        self._set_session(client)
        resp = client.get("/type/noun-le")
        assert b"noun-le" in resp.data

    def test_unknown_type_returns_200(self, client):
        self._set_session(client)
        resp = client.get("/type/no-such-type")
        assert resp.status_code == 200

    def test_lex_type_shows_lexids(self, client):
        self._set_session(client)
        resp = client.get("/type/noun-le")
        assert b"dog" in resp.data

    def test_tdl_shown_for_type(self, client):
        self._set_session(client)
        resp = client.get("/type/noun-le")
        assert b"noun" in resp.data

    def test_rule_type_page(self, client):
        self._set_session(client)
        resp = client.get("/type/hd-cmp_c")
        assert resp.status_code == 200

    def test_root_type_page(self, client):
        self._set_session(client)
        resp = client.get("/type/root")
        assert resp.status_code == 200


class TestSearchPage:
    def test_without_session_redirects(self, client):
        resp = client.post("/search", data={"search": "dog"})
        assert resp.status_code == 302

    def test_search_returns_200(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.post("/search", data={"search": "dog"})
        assert resp.status_code == 200

    def test_search_finds_lemma(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.post("/search", data={"search": "dog"})
        assert b"dog" in resp.data

    def test_search_no_results(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.post("/search", data={"search": "zzznomatch"})
        assert resp.status_code == 200

    def test_search_type_glob(self, client):
        with client.session_transaction() as sess:
            sess["grm"] = "test-grammar_1.0.db"
        resp = client.post("/search", data={"search": "noun*"})
        assert b"noun" in resp.data


class TestDemoPage:
    def test_demo_returns_200(self, client):
        resp = client.get("/demo")
        assert resp.status_code == 200


class TestGrmParam:
    def test_invalid_grm_ignored(self, client):
        resp = client.get("/?grm=nonexistent_grammar")
        assert resp.status_code == 200

    def test_grm_without_db_extension_works(self, client):
        resp = client.get("/?grm=test-grammar_1.0")
        assert resp.status_code == 302

    def test_grm_with_db_extension_works(self, client):
        resp = client.get("/?grm=test-grammar_1.0.db")
        assert resp.status_code == 302
