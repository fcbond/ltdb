"""Tests for scripts/gold2db.py surface-form extraction."""

from __future__ import annotations

from types import SimpleNamespace

from gold2db import align_span, extract_span, get_surface_form

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


class TestAlignSpan:
    """align_span is the fallback used when extract_span finds no
    +FROM/+TO at all (e.g. older LKB-sourced grammars, which carry no
    character-offset data in their tokens whatsoever) -- it locates a
    word by searching the raw sentence text directly instead.
    """

    def test_finds_word_from_cursor(self):
        assert align_span("dog", "The dog barks.", 0) == (4, 7, 7)

    def test_advances_cursor_to_end_of_match(self):
        _, _, cursor = align_span("The", "The dog barks.", 0)
        assert cursor == 3

    def test_repeated_word_finds_next_occurrence_not_first(self):
        # a naive search-from-0 would find the first "the" again;
        # advancing the cursor past each match finds the second one
        sentence = "The dog chased the cat."
        _, _, cursor = align_span("The", sentence, 0)
        assert align_span("the", sentence, cursor) == (15, 18, 18)

    def test_case_insensitive_fallback(self):
        # citation form is lowercase; sentence has it capitalized
        assert align_span("the", "The dog barks.", 0) == (0, 3, 3)

    def test_not_found_returns_none(self):
        assert align_span("cat", "The dog barks.", 0) is None

    def test_not_found_after_cursor_returns_none(self):
        # "The" exists, but not at or after this cursor position
        assert align_span("The", "The dog barks.", 5) is None
