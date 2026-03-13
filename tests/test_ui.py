"""Playwright UI tests for the ltdb Flask application."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.playwright


def _select_grammar(page, live_server_url):
    """Navigate to home and select the test grammar."""
    page.goto(live_server_url)
    page.select_option("select[name=grm]", "test-grammar_1.0.db")
    page.click("button[type=submit]")
    page.wait_for_url("**/grammar.html")


class TestHomePage:
    def test_home_page_loads(self, page, live_server_url):
        page.goto(live_server_url)
        assert page.title() != ""

    def test_grammar_dropdown_present(self, page, live_server_url):
        page.goto(live_server_url)
        assert page.locator("select[name=grm]").count() == 1

    def test_grammar_listed_in_dropdown(self, page, live_server_url):
        page.goto(live_server_url)
        options = page.locator("select[name=grm] option").all_text_contents()
        assert any("test-grammar" in o for o in options)

    def test_grm_param_redirects_to_grammar(self, page, live_server_url):
        page.goto(f"{live_server_url}/?grm=test-grammar_1.0")
        page.wait_for_url("**/grammar.html")
        assert "grammar" in page.url


class TestGrammarSelection:
    def test_form_submission_navigates_to_grammar(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        assert "grammar" in page.url

    def test_grammar_name_displayed(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        assert "Test Grammar" in page.content()


class TestNavigation:
    def test_rules_link_works(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.click("a[href*='rules']")
        page.wait_for_url("**/rules.html")
        assert page.locator("body").is_visible()

    def test_ltypes_link_works(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.click("a[href*='ltypes']")
        page.wait_for_url("**/ltypes.html")
        assert page.locator("body").is_visible()

    def test_rules_page_shows_rule(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/rules.html")
        assert "hd-cmp_c" in page.content()

    def test_ltypes_page_shows_type(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/ltypes.html")
        assert "noun-le" in page.content()


class TestTypePage:
    def test_type_page_loads(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/type/noun-le")
        assert page.locator("body").is_visible()

    def test_type_name_shown(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/type/noun-le")
        assert "noun-le" in page.content()

    def test_lexeme_shown_for_lex_type(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/type/noun-le")
        assert "dog" in page.content()

    def test_type_link_clickable_from_ltypes(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/ltypes.html")
        page.click("a[href*='/type/noun-le']")
        page.wait_for_url("**/type/noun-le")
        assert "noun-le" in page.content()


class TestSearch:
    def test_search_form_present(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/grammar.html")
        assert page.locator("input[name=search]").count() >= 1

    def test_search_returns_results(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/grammar.html")
        page.fill("input[name=search]", "dog")
        page.press("input[name=search]", "Enter")
        page.wait_for_url("**/search")
        assert "dog" in page.content()

    def test_search_no_results_page_loads(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/grammar.html")
        page.fill("input[name=search]", "zzznomatch")
        page.press("input[name=search]", "Enter")
        page.wait_for_url("**/search")
        assert page.locator("body").is_visible()


class TestDemoPage:
    def test_demo_page_loads(self, page, live_server_url):
        page.goto(f"{live_server_url}/demo")
        assert page.locator("body").is_visible()

    def test_demo_page_title(self, page, live_server_url):
        page.goto(f"{live_server_url}/demo")
        assert "Demo" in page.title() or "demo" in page.content().lower()


class TestAllLinksRespond:
    """Smoke-test that every nav link returns a non-error page."""

    def test_grammar_page_ok(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/grammar.html")
        assert "Test Grammar" in page.content()

    def test_rules_page_ok(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/rules.html")
        assert page.locator("body").is_visible()

    def test_ltypes_page_ok(self, page, live_server_url):
        _select_grammar(page, live_server_url)
        page.goto(f"{live_server_url}/ltypes.html")
        assert page.locator("body").is_visible()

    def test_demo_page_ok(self, page, live_server_url):
        page.goto(f"{live_server_url}/demo")
        assert page.locator("body").is_visible()
