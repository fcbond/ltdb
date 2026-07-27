"""Tests for scripts/gold2db.py surface-form extraction."""

from __future__ import annotations

from types import SimpleNamespace

from gold2db import align_span, extract_span, get_surface_form, preterminal_rows

# Real ACE token strings (trimmed) as seen in a UDF derivation, keyed by
# +FROM/+TO like the ones gold2db.py's regex expects.
_TOK_OR = r'token [ +FORM \"or\" +FROM \"14\" +TO \"16\" ]'
_TOK_WHAT = r'token [ +FORM \"what\" +FROM \"17\" +TO \"21\" ]'
_TOK_ARE = r'token [ +FORM \"are\" +FROM \"0\" +TO \"3\" ]'
_TOK_HIKERS = r'token [ +FORM \"hikers\" +FROM \"11\" +TO \"17\" ]'
_TOK_APOS = r'token [ +FORM \"\'\" +FROM \"17\" +TO \"18\" ]'
_TOK_HUT = r'token [ +FORM \"hut\" +FROM \"19\" +TO \"22\" ]'


def _terminal(tokens, form=""):
    return SimpleNamespace(tokens=tokens, form=form)


def _preterminal(entity, start, end):
    return SimpleNamespace(entity=entity, start=start, end=end)


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


class TestPreterminalRows:
    """Regression coverage for the sent.wid / typind.kara,made indexing
    mismatch: a preterminal's row must be keyed by its own `start`
    (pydelphin's raw-token index, matching typind/lexind), not by its
    position in the preterminal/terminal list -- which undercounts by
    one for every multiword entry already seen, since multiword
    entries take up more than one raw-token slot but only one list
    position.
    """

    def test_single_token_entries_are_contiguous(self):
        # baseline: without any multiword entry, start values are the
        # same as a plain enumerate() position would have been
        pairs = [
            (_preterminal("are_v1", 0, 1), _terminal([("1", _TOK_ARE)], "are")),
            (_preterminal("what_q", 1, 2), _terminal([("2", _TOK_WHAT)], "what")),
        ]
        rows = preterminal_rows(pairs, "Are what?")
        assert [r[0] for r in rows] == [0, 1]

    def test_multiword_entry_creates_gap_in_start_index(self):
        # mirrors real ERG data: "...before the hikers' hut..." --
        # "hikers'" is one lexical entry (hikers_a2) spanning two raw
        # tokens (14, 16); the *next* entry, "hut", must start at 16,
        # not 15 as a naive position-based count would give it
        sentence = "before the hikers' hut"
        pairs = [
            (
                _preterminal("hikers_a2", 14, 16),
                _terminal([("1", _TOK_HIKERS), ("2", _TOK_APOS)], "hikers'"),
            ),
            (
                _preterminal("hut_n1", 16, 17),
                _terminal([("3", _TOK_HUT)], "hut"),
            ),
        ]
        rows = preterminal_rows(pairs, sentence)
        assert [r[0] for r in rows] == [14, 16]
        hikers_row, hut_row = rows
        assert hikers_row == (14, 16, "hikers'", "hikers_a2", 11, 18)
        assert hut_row == (16, 17, "hut", "hut_n1", 19, 22)

    def test_falls_back_to_align_span_without_tfs_offsets(self):
        # grammars with no +FROM/+TO at all (e.g. LKB-sourced) still
        # get a correct, gap-preserving start index from the
        # preterminal itself -- align_span only supplies cfrom/cto
        pairs = [
            (_preterminal("hikers_a2", 14, 16), _terminal([], "hikers'")),
            (_preterminal("hut_n1", 16, 17), _terminal([], "hut")),
        ]
        rows = preterminal_rows(pairs, "before the hikers' hut")
        assert [r[0] for r in rows] == [14, 16]
        assert rows[0][4:] == (11, 18)  # cfrom, cto for "hikers'"
        assert rows[1][4:] == (19, 22)  # cfrom, cto for "hut"
