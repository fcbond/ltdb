"""Unit tests for web.preprocess (the morphological-analyzer hook)."""

from __future__ import annotations

from web import preprocess as pp
from web.preprocess import PreprocessResult


class _Stub:
    """A fake analyzer for exercising the registry without external tools."""

    def __init__(self, name="Stub", avail=True, result=None, exc=None):
        self.name = name
        self._avail = avail
        self._result = result
        self._exc = exc

    def available(self):
        return self._avail

    def run(self, text):
        if self._exc:
            raise self._exc
        return self._result or PreprocessResult(ace_input="X", analyzer=self.name)


# --- iso_for -------------------------------------------------------------


def test_iso_for_direct_and_alias():
    assert pp.iso_for({"ISO_CODE": "jpn"}) == "jpn"
    assert pp.iso_for({"ISO_CODE": "ja"}) == "jpn"
    assert pp.iso_for({"ISO_CODE": "zho"}) == "cmn"
    assert pp.iso_for({"ISO_CODE": "es"}) == "spa"


def test_iso_for_shortname_fallback():
    assert pp.iso_for({"SHORT_GRAMMAR_NAME": "Jacy"}) == "jpn"
    assert pp.iso_for({"SHORT_GRAMMAR_NAME": "zhong-zht"}) == "cmn"
    assert pp.iso_for({"SHORT_GRAMMAR_NAME": "kal-hpsg"}) == "kal"


def test_iso_for_unknown_returns_none():
    assert pp.iso_for({"ISO_CODE": "eng"}) is None
    assert pp.iso_for({}) is None


# --- preprocess_for ------------------------------------------------------


def test_preprocess_no_analyzer_passthrough():
    r = pp.preprocess_for({"ISO_CODE": "eng"}, "the dog barks")
    assert r.ace_input == "the dog barks"
    assert r.analyzer is None
    assert r.extra_cmdargs == []
    assert r.yy is False


def test_preprocess_runs_available_analyzer(monkeypatch):
    stub = _Stub(
        "MeCab",
        result=PreprocessResult(
            ace_input="犬 は 猫", tokens=["犬", "は", "猫"], analyzer="MeCab"
        ),
    )
    monkeypatch.setitem(pp.REGISTRY, "jpn", stub)
    r = pp.preprocess_for({"ISO_CODE": "jpn"}, "犬は猫")
    assert r.ace_input == "犬 は 猫"
    assert r.analyzer == "MeCab"
    assert r.tokens == ["犬", "は", "猫"]


def test_preprocess_unavailable_falls_back_with_note(monkeypatch):
    monkeypatch.setitem(pp.REGISTRY, "jpn", _Stub("MeCab", avail=False))
    r = pp.preprocess_for({"ISO_CODE": "jpn"}, "犬は猫")
    assert r.ace_input == "犬は猫"  # raw, unchanged
    assert r.analyzer == "MeCab"
    assert "not installed" in (r.note or "")


def test_preprocess_error_falls_back_with_note(monkeypatch):
    monkeypatch.setitem(pp.REGISTRY, "jpn", _Stub("MeCab", exc=RuntimeError("boom")))
    r = pp.preprocess_for({"ISO_CODE": "jpn"}, "犬は猫")
    assert r.ace_input == "犬は猫"
    assert r.analyzer == "MeCab"
    assert r.note  # a generic note is present
    assert "boom" not in (r.note or "")  # raw exception text is not leaked


def test_preprocess_disabled_by_env(monkeypatch):
    monkeypatch.setitem(
        pp.REGISTRY,
        "jpn",
        _Stub("MeCab", result=PreprocessResult(ace_input="X", analyzer="MeCab")),
    )
    monkeypatch.setenv("LTDB_ANALYZERS", "spa,cmn")  # jpn deliberately excluded
    r = pp.preprocess_for({"ISO_CODE": "jpn"}, "犬は猫")
    assert r.ace_input == "犬は猫"
    assert r.analyzer is None


class _BoomAvailable:
    """Analyzer whose availability discovery itself raises."""

    name = "Boom"

    def available(self):
        raise RuntimeError("secret /opt/path discovery failure")

    def run(self, text):
        return PreprocessResult(ace_input="unused", analyzer=self.name)


def test_preprocess_available_exception_falls_back_without_500(monkeypatch):
    monkeypatch.setitem(pp.REGISTRY, "jpn", _BoomAvailable())
    r = pp.preprocess_for({"ISO_CODE": "jpn"}, "犬は猫")
    assert r.ace_input == "犬は猫"  # graceful fallback, not an exception
    assert r.analyzer == "Boom"
    # the raw exception text (which can leak paths) is not sent to the client
    assert "secret" not in (r.note or "")


def test_preprocess_command_empty_output_falls_back(monkeypatch):
    # spa uses CommandAnalyzer; `true` is available but prints nothing →
    # run() raises → preprocess_for falls back to raw with no leaked YY flags
    monkeypatch.setenv("SRG_YY_CMD", "true")
    r = pp.preprocess_for({"ISO_CODE": "spa"}, "el perro ladra")
    assert r.ace_input == "el perro ladra"
    assert r.analyzer == "FreeLing"
    assert r.extra_cmdargs == []
    assert r.yy is False


# --- CommandAnalyzer (FreeLing / KARMA style) ----------------------------


def test_command_analyzer_yy_mode(monkeypatch):
    # `cat` stands in for a YY producer: it echoes stdin to stdout.
    monkeypatch.setenv("SRG_YY_CMD", "cat")
    a = pp.CommandAnalyzer("FreeLing", "desc", "SRG_YY_CMD", mode="yy", yy_rules=True)
    assert a.available() is True
    r = a.run('(1, 0, 1, <0:2>, 1, "el", ...)')
    assert r.yy is True
    assert r.extra_cmdargs == ["-y", "--yy-rules"]
    assert r.ace_input.startswith("(1, 0, 1")


def test_command_analyzer_segment_mode(monkeypatch):
    monkeypatch.setenv("KARMA_CMD", "cat")
    a = pp.CommandAnalyzer("KARMA", "desc", "KARMA_CMD", mode="segment")
    r = a.run("inuk pok")
    assert r.yy is False
    assert r.extra_cmdargs == []
    assert r.tokens == ["inuk", "pok"]


def test_command_analyzer_unset_is_unavailable(monkeypatch):
    monkeypatch.delenv("SRG_YY_CMD", raising=False)
    a = pp.CommandAnalyzer("FreeLing", "desc", "SRG_YY_CMD")
    assert a.available() is False


def test_command_analyzer_empty_output_raises(monkeypatch):
    # exit 0 with no stdout must not hand ACE an empty sentence + YY flags
    monkeypatch.setenv("SRG_YY_CMD", "true")
    a = pp.CommandAnalyzer("FreeLing", "desc", "SRG_YY_CMD", mode="yy", yy_rules=True)
    import pytest

    with pytest.raises(ValueError):
        a.run("el perro ladra")


def test_command_analyzer_quoted_args(monkeypatch):
    # shlex.split keeps quoted arguments together
    monkeypatch.setenv("SRG_YY_CMD", 'printf "%s" "hi there"')
    a = pp.CommandAnalyzer("FreeLing", "desc", "SRG_YY_CMD", mode="segment")
    assert a._command() == ["printf", "%s", "hi there"]


# --- KarmaAnalyzer (in-process Kalaallisut morphology) -------------------


def _install_fake_karma(monkeypatch, result):
    """Inject a fake `karma.encode_decode.parse_sentence` returning *result*."""
    import sys
    import types

    class _ParseResult:
        pass

    pr = _ParseResult()
    pr.result = result
    enc = types.ModuleType("karma.encode_decode")
    enc.parse_sentence = lambda text: pr
    monkeypatch.setitem(sys.modules, "karma", types.ModuleType("karma"))
    monkeypatch.setitem(sys.modules, "karma.encode_decode", enc)


class _Morph:
    """Stand-in for KARMA's MorphemeSeqData whose str() is the segmentation."""

    def __init__(self, s):
        self._s = s

    def __str__(self):
        return self._s


def test_karma_run_takes_first_analysis_per_word(monkeypatch):
    # word 1: single analysis; word 2: two analyses (ambiguous)
    _install_fake_karma(
        monkeypatch,
        [[_Morph("inuk")], [_Morph("taku-vuq"), _Morph("taku=vuq")]],
    )
    r = pp.KarmaAnalyzer().run("Inuk takuvoq")
    assert r.ace_input == "inuk taku-vuq"
    assert r.tokens == ["inuk", "taku-vuq"]
    assert r.yy is False
    assert "multiple analyses" in (r.note or "")


def test_karma_run_no_segmentation_falls_back(monkeypatch):
    _install_fake_karma(monkeypatch, [[]])  # no analysis for the word
    r = pp.KarmaAnalyzer().run("xyz")
    assert r.ace_input == "xyz"
    assert "could not segment" in (r.note or "")


def test_karma_run_partial_failure_falls_back_to_raw(monkeypatch):
    # one word analyzed, one not: must NOT drop the unknown word (that could
    # yield a misleadingly successful parse of a shorter sentence)
    _install_fake_karma(monkeypatch, [[_Morph("inuk")], []])
    r = pp.KarmaAnalyzer().run("inuk qqq")
    assert r.ace_input == "inuk qqq"  # raw, unchanged
    assert "could not segment" in (r.note or "")


def test_karma_available_reflects_importlib(monkeypatch):
    monkeypatch.setattr(
        pp.importlib.util,
        "find_spec",
        lambda name: object() if name == "karma" else None,
    )
    assert pp.KarmaAnalyzer().available() is True
    monkeypatch.setattr(pp.importlib.util, "find_spec", lambda name: None)
    assert pp.KarmaAnalyzer().available() is False
