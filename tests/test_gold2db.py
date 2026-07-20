"""Tests for scripts/gold2db.py surface-form extraction."""

from __future__ import annotations

from types import SimpleNamespace

from gold2db import extract_span, get_surface_form

# Real ACE token strings (trimmed) as seen in a UDF derivation, keyed by
# +FROM/+TO like the ones gold2db.py's regex expects.
_TOK_OR = r'token [ +FORM \"or\" +FROM \"14\" +TO \"16\" ]'
_TOK_WHAT = r'token [ +FORM \"what\" +FROM \"17\" +TO \"21\" ]'
_TOK_ARE = r'token [ +FORM \"are\" +FROM \"0\" +TO \"3\" ]'


def _terminal(tokens, form=""):
    return SimpleNamespace(tokens=tokens, form=form)


class TestExtractSpan:
    def test_single_token_span(self):
        term = _terminal([("78", _TOK_ARE)])
        assert extract_span(term) == (0, 3)

    def test_multi_token_span_covers_all_tokens(self):
        # a multiword lexical entry ("or what") spans two input tokens;
        # the span must run from the first token's start to the last
        # token's end, not just the first token's
        term = _terminal([("84", _TOK_OR), ("86", _TOK_WHAT)])
        assert extract_span(term) == (14, 21)

    def test_no_tokens_returns_none(self):
        assert extract_span(_terminal([])) is None

    def test_unparsable_token_returns_none(self):
        term = _terminal([("1", "token [ +FORM \\\"x\\\" ]")])
        assert extract_span(term) is None


class TestGetSurfaceForm:
    def test_single_token_extracts_substring(self):
        term = _terminal([("78", _TOK_ARE)], form="are")
        assert get_surface_form(term, "Are you kiasi or what?") == "Are"

    def test_multi_token_extracts_full_span_not_first_word_only(self):
        term = _terminal([("84", _TOK_OR), ("86", _TOK_WHAT)], form="or what")
        assert (
            get_surface_form(term, "Are you kiasi or what?") == "or what"
        )

    def test_falls_back_to_terminal_form_without_span(self):
        term = _terminal([], form="or what")
        assert get_surface_form(term, "Are you kiasi or what?") == "or what"
