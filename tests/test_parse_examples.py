"""Unit tests for parse_examples.py.

All ACE parsing is mocked; no grammar binary or .dat file is needed.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from parse_examples import (
    Example,
    Verdict,
    _build_descendants_for_type,
    _parse_doc,
    run_examples,
    type_in_results,
    verdict_label,
)

# ── _parse_doc ────────────────────────────────────────────────────────────────


class TestParseDoc:
    def test_ex_tag(self):
        doc = "<ex>She sleeps."
        assert _parse_doc("some-type", doc) == [
            ("She sleeps.", "some-type", 1, "ex")
        ]

    def test_nex_tag(self):
        doc = "<nex>She sleep."
        assert _parse_doc("some-type", doc) == [
            ("She sleep.", "some-type", 0, "nex")
        ]

    def test_mex_tag(self):
        doc = "<mex>Her sleeps."
        assert _parse_doc("some-type", doc) == [
            ("Her sleeps.", "some-type", 1, "mex")
        ]

    def test_mixed_tags_and_prose(self):
        doc = (
            "A head-complement rule.\n"
            "<ex>Dogs bark.\n"
            "<nex>Bark dogs.\n"
            "<mex>Her sleep.\n"
            "Some trailing prose."
        )
        result = _parse_doc("hd-cmp_u_c", doc)
        assert len(result) == 3
        assert result[0] == ("Dogs bark.", "hd-cmp_u_c", 1, "ex")
        assert result[1] == ("Bark dogs.", "hd-cmp_u_c", 0, "nex")
        assert result[2] == ("Her sleep.", "hd-cmp_u_c", 1, "mex")

    def test_empty_docstring(self):
        assert _parse_doc("t", "") == []

    def test_blank_example_skipped(self):
        assert _parse_doc("t", "<ex>") == []
        assert _parse_doc("t", "<ex>  ") == []

    def test_strips_leading_whitespace(self):
        doc = "   <ex>  Dogs bark.  "
        result = _parse_doc("t", doc)
        assert result == [("Dogs bark.", "t", 1, "ex")]


# ── type_in_results ───────────────────────────────────────────────────────────


def _mock_node(spec):
    """Node from "entity" or ("entity", "type") — type is the --udx=all
    annotation (None when absent, as in pre-udx derivations)."""
    if isinstance(spec, tuple):
        entity, typ = spec
    else:
        entity, typ = spec, None
    return MagicMock(entity=entity, type=typ)


def _make_derivation(internals=(), preterminals=()):
    """Build a mock derivation with given entity names (or (entity, type))."""
    deriv = MagicMock()
    deriv.internals.return_value = [_mock_node(e) for e in internals]
    deriv.preterminals.return_value = [_mock_node(e) for e in preterminals]
    return deriv


def _make_result(deriv):
    result = MagicMock()
    result.derivation.return_value = deriv
    return result


# ── _build_descendants_for_type ─────────────────────────────────────────────


class TestBuildDescendantsForType:
    def test_direct_parent(self):
        types = {"sleep_v1": ["lex-entry"], "verb-lxm": ["type"], "sign": ["type"]}
        hierarchy = [("sleep_v1", "verb-lxm"), ("verb-lxm", "sign")]
        result = _build_descendants_for_type(types, hierarchy)
        assert "sleep_v1" in result["verb-lxm"]
        assert "sleep_v1" in result["sign"]

    def test_indirect_ancestor(self):
        types = {
            "run_v1": ["lex-entry"],
            "intrans-verb-lxm": ["type"],
            "verb-lxm": ["type"],
            "word": ["type"],
        }
        hierarchy = [
            ("run_v1", "intrans-verb-lxm"),
            ("intrans-verb-lxm", "verb-lxm"),
            ("verb-lxm", "word"),
        ]
        result = _build_descendants_for_type(types, hierarchy)
        assert "run_v1" in result["intrans-verb-lxm"]
        assert "run_v1" in result["verb-lxm"]
        assert "run_v1" in result["word"]

    def test_empty_types(self):
        assert _build_descendants_for_type({}, []) == {}

    def test_every_type_is_its_own_descendant(self):
        types = {"hd-cmp_u_c": ["rule"]}
        result = _build_descendants_for_type(types, [])
        assert result["hd-cmp_u_c"] == {"hd-cmp_u_c"}

    def test_rule_descendant_not_just_lexical(self):
        # the walk is not lexicon-specific: an abstract rule supertype
        # with no direct instances is reached via its concrete subtype
        types = {
            "hd-cmp_u_c": ["rule"],
            "basic-head-comp-phrase": ["rule"],
        }
        hierarchy = [("hd-cmp_u_c", "basic-head-comp-phrase")]
        result = _build_descendants_for_type(types, hierarchy)
        assert "hd-cmp_u_c" in result["basic-head-comp-phrase"]


# ── type_in_results ───────────────────────────────────────────────────────────


class TestTypeInResults:
    def test_rule_found_in_internals(self):
        deriv = _make_derivation(internals=["hd-cmp_u_c"])
        result = _make_result(deriv)
        assert type_in_results("hd-cmp_u_c", ["rule"], [result], {})

    def test_rule_not_found(self):
        deriv = _make_derivation(internals=["other-rule"])
        result = _make_result(deriv)
        assert not type_in_results("hd-cmp_u_c", ["rule"], [result], {})

    def test_lex_rule_found_in_preterminals(self):
        deriv = _make_derivation(preterminals=["v_pst_olr"])
        result = _make_result(deriv)
        assert type_in_results("v_pst_olr", ["lex-rule"], [result], {})

    def test_lex_type_via_descendants_for_type(self):
        lex_ids = {"intrans-verb-lxm": {"sleep_v1", "run_v1"}}
        deriv = _make_derivation(preterminals=["sleep_v1"])
        result = _make_result(deriv)
        assert type_in_results("intrans-verb-lxm", ["type"], [result], lex_ids)

    def test_lex_type_works_regardless_of_status(self):
        # status 'type' (not 'lex-type') — should still find the lex entry
        lex_ids = {"verb-lxm": {"sleep_v1"}}
        deriv = _make_derivation(preterminals=["sleep_v1"])
        result = _make_result(deriv)
        assert type_in_results("verb-lxm", ["type"], [result], lex_ids)

    def test_lex_type_lexid_absent(self):
        lex_ids = {"intrans-verb-lxm": {"run_v1"}}
        deriv = _make_derivation(preterminals=["bark_v1"])
        result = _make_result(deriv)
        assert not type_in_results("intrans-verb-lxm", ["type"], [result], lex_ids)

    def test_lex_type_via_udx_node_type(self):
        # --udx=all annotates the preterminal with its lexical type
        deriv = _make_derivation(preterminals=[("dog_n1", "n_-_c_le")])
        result = _make_result(deriv)
        assert type_in_results("n_-_c_le", ["lex-type"], [result], {})

    def test_generic_lex_type_via_udx_node_type(self):
        # generic/unknown-word types have no static lex entries, so only
        # the udx annotation can find them (the *-gen_le / *-unk_le case)
        deriv = _make_derivation(
            preterminals=[("generic_proper_ne", "n_-_pn-gen_le")]
        )
        result = _make_result(deriv)
        assert type_in_results("n_-_pn-gen_le", ["lex-type"], [result], {})

    def test_phrase_type_via_udx_node_type(self):
        # internal nodes are annotated with their phrase type
        deriv = _make_derivation(internals=[("sb-hd_mc_c", "subjh_mc_rule")])
        result = _make_result(deriv)
        assert type_in_results("subjh_mc_rule", ["rule"], [result], {})

    def test_udx_node_type_absent_is_not_found(self):
        deriv = _make_derivation(preterminals=[("dog_n1", "n_-_c_le")])
        result = _make_result(deriv)
        assert not type_in_results("v_-_le", ["lex-type"], [result], {})

    def test_found_in_any_parse(self):
        deriv1 = _make_derivation(internals=["other-rule"])
        deriv2 = _make_derivation(internals=["hd-cmp_u_c"])
        results = [_make_result(deriv1), _make_result(deriv2)]
        assert type_in_results("hd-cmp_u_c", ["rule"], results, {})

    def test_broken_derivation_skipped(self):
        result = MagicMock()
        result.derivation.side_effect = RuntimeError("bad UDF")
        assert not type_in_results("t", ["rule"], [result], {})

    def test_none_derivation_skipped(self):
        result = MagicMock()
        result.derivation.return_value = None
        assert not type_in_results("t", ["rule"], [result], {})

    def test_empty_results(self):
        assert not type_in_results("t", ["rule"], [], {})

    def test_abstract_rule_matched_via_concrete_descendant(self):
        # a documented abstract rule with no direct instances is matched
        # when a concrete subtype fires in the derivation
        descendants = {"basic-head-comp-phrase": {"hd-cmp_u_c", "hd-cmp_i_c"}}
        deriv = _make_derivation(internals=["hd-cmp_u_c"])
        result = _make_result(deriv)
        assert type_in_results(
            "basic-head-comp-phrase", ["rule"], [result], descendants
        )

    def test_abstract_rule_descendant_absent(self):
        descendants = {"basic-head-comp-phrase": {"hd-cmp_u_c", "hd-cmp_i_c"}}
        deriv = _make_derivation(internals=["other-rule"])
        result = _make_result(deriv)
        assert not type_in_results(
            "basic-head-comp-phrase", ["rule"], [result], descendants
        )


# ── verdict_label ─────────────────────────────────────────────────────────────


def _v(kind, n_parses, type_found):
    ex = Example(i_id=1, text="test", typ="t", wf=1, kind=kind)
    return Verdict(ex, n_parses, type_found)


class TestVerdictLabel:
    # <ex> cases
    def test_ex_pass(self):
        assert verdict_label(_v("ex", 3, True)) == "PASS"

    def test_ex_fail_no_parse(self):
        assert verdict_label(_v("ex", 0, False)) == "FAIL-no-parse"

    def test_ex_fail_type_absent(self):
        assert verdict_label(_v("ex", 2, False)) == "FAIL-type-absent"

    # <mex> cases — same logic as <ex>
    def test_mex_pass(self):
        assert verdict_label(_v("mex", 1, True)) == "PASS"

    def test_mex_fail_no_parse(self):
        assert verdict_label(_v("mex", 0, False)) == "FAIL-no-parse"

    def test_mex_fail_type_absent(self):
        assert verdict_label(_v("mex", 2, False)) == "FAIL-type-absent"

    # <nex> cases — PASS if type absent from all parse trees (parse-or-not is info only)
    def test_nex_pass_no_parse(self):
        assert verdict_label(_v("nex", 0, False)) == "PASS"

    def test_nex_pass_parsed_type_absent(self):
        # sentence parsed but the prohibited type did not appear — still PASS
        assert verdict_label(_v("nex", 2, False)) == "PASS"

    def test_nex_fail_type_in_tree(self):
        assert verdict_label(_v("nex", 1, True)) == "FAIL-type-in-tree"

    def test_nex_fail_type_in_tree_no_parse(self):
        # edge case: type_found implies parse happened, but guard it anyway
        assert verdict_label(_v("nex", 0, True)) == "FAIL-type-in-tree"


# ── run_examples parallelism ──────────────────────────────────────────────────


class _FakeParser:
    """Stands in for ace.ACEParser; counts how many were started."""

    instances = 0

    def __init__(self, dat, executable=None, cmdargs=None):
        type(self).instances += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def process_item(self, text, keys=None):
        response = MagicMock()
        response.results.return_value = []
        return response


class TestRunExamplesJobs:
    def _examples(self, n):
        return [
            Example(i_id=(i + 1) * 10, text=f"s {i}", typ="some-type", wf=1, kind="ex")
            for i in range(n)
        ]

    def test_parallel_matches_serial_and_keeps_order(self, monkeypatch):
        monkeypatch.setattr("parse_examples.ace.ACEParser", _FakeParser)
        exs = self._examples(9)
        serial = run_examples(exs, "g.dat", "ace", {}, {}, jobs=1)
        parallel = run_examples(exs, "g.dat", "ace", {}, {}, jobs=3)
        assert parallel == serial
        assert [v.example.i_id for v in parallel] == [ex.i_id for ex in exs]

    def test_parallel_starts_one_parser_per_worker(self, monkeypatch):
        monkeypatch.setattr("parse_examples.ace.ACEParser", _FakeParser)
        exs = self._examples(9)
        _FakeParser.instances = 0
        run_examples(exs, "g.dat", "ace", {}, {}, jobs=3)
        assert _FakeParser.instances == 3

    def test_jobs_capped_by_example_count(self, monkeypatch):
        monkeypatch.setattr("parse_examples.ace.ACEParser", _FakeParser)
        exs = self._examples(2)
        _FakeParser.instances = 0
        run_examples(exs, "g.dat", "ace", {}, {}, jobs=8)
        assert _FakeParser.instances == 2

    def test_default_jobs_is_positive(self):
        from parse_examples import default_jobs

        jobs = default_jobs()
        assert isinstance(jobs, int)
        assert jobs >= 1
