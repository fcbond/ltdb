"""Tests for web/ltdb.py utility functions."""

from __future__ import annotations

import pytest

from web.ltdb import (
    deriv_word_span_to_char_span,
    docstring2html,
    munge_desc,
    sanitize_grm,
)


class TestMungeDesc:
    def test_plain_text_passthrough(self):
        text, exes, nams = munge_desc("noun-le", "A simple description.")
        assert "A simple description." in text
        assert exes == []
        assert nams == []

    def test_grammatical_example(self):
        text, exes, nams = munge_desc("noun-le", "<ex>The dog barks.")
        assert len(exes) == 1
        assert exes[0] == ("The dog barks.", "noun-le", 1)
        assert "The dog barks." in text

    def test_ungrammatical_example(self):
        text, exes, nams = munge_desc("noun-le", "<nex>Dog the barks.")
        assert len(exes) == 1
        assert exes[0] == ("Dog the barks.", "noun-le", 0)
        assert "∗" in text

    def test_marginal_example(self):
        text, exes, nams = munge_desc("noun-le", "<mex>Dog barks.")
        assert len(exes) == 1
        assert exes[0] == ("Dog barks.", "noun-le", 1)
        assert "⊛" in text

    def test_multiple_examples(self):
        docstring = "<ex>The dog barks.\n<nex>Dog the barks.\n<mex>Dog barks."
        text, exes, nams = munge_desc("noun-le", docstring)
        assert len(exes) == 3
        assert exes[0][2] == 1  # grammatical
        assert exes[1][2] == 0  # ungrammatical
        assert exes[2][2] == 1  # marginal

    def test_name_tag(self):
        docstring = "<name lang='en'>Alex</name>"
        text, exes, nams = munge_desc("noun-le", docstring)
        assert len(nams) == 1
        assert nams[0] == ("noun-le", "en", "Alex")

    def test_name_tag_double_quotes(self):
        docstring = '<name lang="ja">光</name>'
        text, exes, nams = munge_desc("verb-le", docstring)
        assert nams[0] == ("verb-le", "ja", "光")

    def test_empty_docstring(self):
        text, exes, nams = munge_desc("noun-le", "")
        assert text == ""
        assert exes == []
        assert nams == []

    def test_mixed_content(self):
        docstring = "A noun type.\n<ex>The dog barks.\nMore text."
        text, exes, nams = munge_desc("noun-le", docstring)
        assert "A noun type." in text
        assert "More text." in text
        assert len(exes) == 1

    def test_whitespace_stripped_from_examples(self):
        text, exes, nams = munge_desc("noun-le", "<ex>  The dog barks.  ")
        assert exes[0][0] == "The dog barks."


class TestRst2Html:
    def test_empty_docstring_returns_empty(self):
        assert docstring2html("noun-le", "") == ""

    def test_none_returns_empty(self):
        assert docstring2html("noun-le", None) == ""

    def test_plain_text_renders_to_html(self):
        result = docstring2html("noun-le", "A simple description.")
        assert "<p>" in result
        assert "A simple description." in result

    def test_example_rendered_as_italic(self):
        result = docstring2html("noun-le", "<ex>The dog barks.")
        assert "The dog barks." in result

    def test_returns_string(self):
        result = docstring2html("noun-le", "Some text.")
        assert isinstance(result, str)


class TestSanitizeGrm:
    @pytest.mark.parametrize("inp,expected", [
        ("test-grammar_1.0",    "test-grammar_1.0.db"),
        ("test-grammar_1.0.db", "test-grammar_1.0.db"),
        ("erg_trunk",           "erg_trunk.db"),
        ("yue_2026.03.12",      "yue_2026.03.12.db"),
    ])
    def test_valid_names(self, inp, expected):
        assert sanitize_grm(inp) == expected

    @pytest.mark.parametrize("inp", [
        "../../../etc/passwd",
        "/etc/passwd",
        "foo/bar",
        "foo\\bar",
        "",
        "   ",
    ])
    def test_invalid_names_return_none(self, inp):
        assert sanitize_grm(inp) is None


class TestDerivWordSpanToCharSpan:
    """deriv_word_span_to_char_span translates a [start, end) word-index
    span (the same scheme typind.kara/made and sent.wid already use) into
    a (cfrom, cto) character span, by unioning the +FROM/+TO offsets PET
    embeds in each preterminal's token feature structure — present for
    ACE/PET-parsed grammars like the ERG, absent for older LKB-sourced
    ones like Jacy, which carry no character-offset data at all.
    """

    # a real ERG derivation excerpt (build/DBS/ERG_2025.db, ws203/1000001800010),
    # trimmed to the token feature structure's relevant +FROM/+TO fields
    ERG_DERIV = (
        '(root_inffrag (0 np_frg_c 0 0 1 (0 hdn_bnp_c 0 0 1 '
        '(0 n_ms_ilr 0 0 1 (0 cross_platform_n1 0 0 1 '
        '("cross-platform" 30 "token [ +FORM \\"cross-platform\\" '
        '+FROM \\"2\\" +TO \\"16\\" ]"))))))'
    )

    # a real Jacy derivation excerpt (build/DBS/Jacy_2020.07.20.db):
    # bare terminals, no token feature structure at all
    JACY_DERIV = (
        "(utterance-root (923 rule -1.5 0 2 "
        '(11 kare 0 0 1 ("kare")) (21 narg 0.4 1 2 ("ni"))))'
    )

    def test_erg_style_span_found(self):
        assert deriv_word_span_to_char_span(self.ERG_DERIV, 0, 1) == (2, 16)

    def test_jacy_style_returns_none(self):
        """Older LKB-sourced grammars carry no +FROM/+TO at all."""
        assert deriv_word_span_to_char_span(self.JACY_DERIV, 0, 1) is None
        assert deriv_word_span_to_char_span(self.JACY_DERIV, 1, 2) is None

    def test_empty_deriv_returns_none(self):
        assert deriv_word_span_to_char_span("", 0, 1) is None
        assert deriv_word_span_to_char_span(None, 0, 1) is None

    def test_unparsable_deriv_returns_none(self):
        assert deriv_word_span_to_char_span("not a derivation (((", 0, 1) is None

    # a real GG (German Grammar, PET-parsed) derivation excerpt
    # (etc/ltdb/web/db/GG_1311.db, mrs/78): PET's token FS is not
    # consistent about +FROM/+TO order -- this token has +TO before
    # +FROM, unlike the ERG example above
    GG_REVERSED_ORDER_DERIV = (
        '(1037 pos-es -1.3 0 1 '
        '(86 es-expl 0.17 0 1 ("es" 66 "token [ +PRED predsort '
        '+TO \\"2\\" +FROM \\"0\\" ]")))'
    )

    def test_reversed_from_to_order_still_found(self):
        """PET serializes some tokens as \"+TO ... +FROM ...\", not just
        \"+FROM ... +TO ...\" -- both orders must resolve to the same span.
        """
        assert deriv_word_span_to_char_span(self.GG_REVERSED_ORDER_DERIV, 0, 1) == (0, 2)
