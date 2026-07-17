"""Playwright browser tests for the ltdb demo page.

These tests drive a real browser against the gunicorn server to verify that
parse trees, MRS, and DMRS visualisations actually render in the DOM.

Run with:
    uv run pytest tests/test_demo_browser.py -v --headed   # visible browser
    uv run pytest tests/test_demo_browser.py -v            # headless
"""

import re

import pytest

from .conftest import GRAMMAR, SENTENCES, needs_dat

TIMEOUT = 30_000  # ms


def _load_demo(page, gunicorn_url, sentence, grammar=GRAMMAR):
    """Navigate to /demo, select grammar, fill input, and submit the parse form.

    Uses jQuery's trigger('submit') rather than a native button click.
    Playwright's page.click() on a submit button in headless Chromium does
    not always fire the form submit event when the input value was set
    programmatically (even with validity.valid == True), so we trigger the
    handler directly instead.
    """
    page.goto(gunicorn_url + "/demo")
    page.wait_for_load_state("networkidle", timeout=20_000)
    page.select_option("#grammarSelect", grammar)
    page.locator("#inputText").fill(sentence)
    page.evaluate("$('#parseForm').trigger('submit')")


@needs_dat
def test_demo_page_shows_grammar(page, gunicorn_url):
    page.goto(gunicorn_url + "/demo")
    options = page.locator("#grammarSelect option").all_text_contents()
    assert any("ERG_2025" in o for o in options), f"ERG_2025 not in grammar list: {options}"


@needs_dat
def test_parse_tree_renders(page, gunicorn_url):
    """Submitting a sentence should produce at least one result card with a tree."""
    _load_demo(page, gunicorn_url, "Dogs bark.")

    page.wait_for_selector(".result-card", timeout=TIMEOUT)
    assert page.locator(".result-card").count() > 0

    # Tree button should be present and already toggled active (Tree shown by default)
    tree_btn = page.locator(".result-card").first.locator("button", has_text="Tree")
    assert tree_btn.is_visible()

    # The tree SVG/canvas should be in the DOM
    viz = page.locator(".result-card").first.locator(".result-viz").first
    assert viz.is_visible()


@needs_dat
def test_dmrs_renders_on_click(page, gunicorn_url):
    """Clicking the DMRS button should lazily render an SVG."""
    _load_demo(page, gunicorn_url, "The dog barked.")

    page.wait_for_selector(".result-card", timeout=TIMEOUT)

    dmrs_btn = page.locator(".result-card").first.locator("button", has_text="DMRS")
    assert dmrs_btn.is_visible(), "DMRS button missing — dmrs may be null in response"
    dmrs_btn.click()

    page.wait_for_selector(".result-card svg", timeout=5_000)
    svg_count = page.locator(".result-card svg").count()
    assert svg_count > 0, "No SVG rendered after clicking DMRS"


@needs_dat
def test_mrs_renders_on_click(page, gunicorn_url):
    """Clicking the MRS button should render MRS content."""
    _load_demo(page, gunicorn_url, "Kim likes Sandy.")

    page.wait_for_selector(".result-card", timeout=TIMEOUT)

    mrs_btn = page.locator(".result-card").first.get_by_role("button", name=re.compile(r"^MRS$"))
    assert mrs_btn.is_visible(), "MRS button missing — mrs may be null in response"
    mrs_btn.click()

    # MRS renderer (mrs.js) produces a table or span structure
    page.wait_for_selector(".result-viz:visible", timeout=5_000)


@needs_dat
def test_tree_shows_lexical_types(page, gunicorn_url):
    """The rendered tree includes lex-type (_le) and lex-entry nodes."""
    _load_demo(page, gunicorn_url, "Dogs bark.")
    page.wait_for_selector(".result-card .ltdb-tree-svg", timeout=TIMEOUT)

    card = page.locator(".result-card").first
    lex_types = card.locator(".ltdb-tree-node.lex-type text")
    assert lex_types.count() > 0, "no lex-type nodes in the tree"
    labels = lex_types.all_text_contents()
    assert any(label.endswith("_le") for label in labels), \
        f"no _le lexical type shown: {labels}"
    assert card.locator(".ltdb-tree-node.lex-entry").count() > 0, \
        "no lex-entry nodes in the tree"


@needs_dat
def test_raw_buttons_show_source_strings(page, gunicorn_url):
    """Tree, MRS and DMRS each get a [raw] toggle with the original string."""
    _load_demo(page, gunicorn_url, "Dogs bark.")
    page.wait_for_selector(".result-card", timeout=TIMEOUT)

    card = page.locator(".result-card").first
    raw_btns = card.get_by_role("button", name="raw", exact=True)
    assert raw_btns.count() == 3, "expected raw buttons for tree, MRS and DMRS"

    def visible_pre_texts():
        pres = card.locator("pre:visible")
        return [pres.nth(i).inner_text() for i in range(pres.count())]

    raw_btns.nth(0).click()  # tree: ACE's UDX derivation string
    assert any("@" in t and "(" in t for t in visible_pre_texts()), \
        "tree raw did not show a UDX derivation string"

    raw_btns.nth(1).click()  # MRS: simplemrs string
    assert any("TOP:" in t and "RELS:" in t for t in visible_pre_texts()), \
        "MRS raw did not show a simplemrs string"

    raw_btns.nth(2).click()  # DMRS: JSON
    assert any('"nodes"' in t for t in visible_pre_texts()), \
        "DMRS raw did not show DMRS JSON"


@needs_dat
@pytest.mark.parametrize("sentence", SENTENCES[:5])
def test_multiple_sentences_parse(page, gunicorn_url, sentence):
    """Each sentence should yield results without a 500 or 'No parses' warning."""
    _load_demo(page, gunicorn_url, sentence)

    # Either results appear or an error/warning is shown — never a blank page
    page.wait_for_selector("#results :is(.result-card, .alert)", timeout=TIMEOUT)

    error = page.locator("#results .alert-danger")
    assert not error.is_visible(), \
        f"Error shown for {sentence!r}: {error.inner_text() if error.count() else ''}"

    cards = page.locator(".result-card").count()
    assert cards > 0, f"No result cards for {sentence!r}"
