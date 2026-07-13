"""Unit tests for parse_examples.py.

All ACE parsing is mocked; no grammar binary or .dat file is needed.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from parse_examples import (
    Example,
    Verdict,
    _build_lex_ids_for_type,
    _build_subtypes_for_type,
    _parse_doc,
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


def _make_derivation(internals=(), preterminals=()):
    """Build a mock derivation with given entity names."""
    deriv = MagicMock()
    deriv.internals.return_value = [
        MagicMock(entity=e) for e in internals
    ]
    deriv.preterminals.return_value = [
        MagicMock(entity=e) for e in preterminals
    ]
    return deriv


def _make_result(deriv):
    result = MagicMock()
    result.derivation.return_value = deriv
    return result


# ── _build_lex_ids_for_type ───────────────────────────────────────────────────


class TestBuildLexIdsForType:
    def test_direct_parent(self):
        les = {"sleep_v1": ("verb-lxm", None, None, None, None, None, None)}
        hierarchy = [("sleep_v1", "verb-lxm"), ("verb-lxm", "sign")]
        result = _build_lex_ids_for_type(les, hierarchy)
        assert "sleep_v1" in result["verb-lxm"]
        assert "sleep_v1" in result["sign"]

    def test_indirect_ancestor(self):
        les = {"run_v1": ("intrans-verb-lxm", None, None, None, None, None, None)}
        hierarchy = [
            ("run_v1", "intrans-verb-lxm"),
            ("intrans-verb-lxm", "verb-lxm"),
            ("verb-lxm", "word"),
        ]
        result = _build_lex_ids_for_type(les, hierarchy)
        assert "run_v1" in result["intrans-verb-lxm"]
        assert "run_v1" in result["verb-lxm"]
        assert "run_v1" in result["word"]

    def test_empty_lexicon(self):
        assert _build_lex_ids_for_type({}, []) == {}


# ── _build_subtypes_for_type ──────────────────────────────────────────────────


class TestBuildSubtypesForType:
    def test_direct_child(self):
        hierarchy = [("conc-rule", "abs-rule")]
        result = _build_subtypes_for_type({"abs-rule"}, hierarchy)
        assert "conc-rule" in result["abs-rule"]

    def test_transitive_descendant(self):
        hierarchy = [
            ("leaf-rule", "mid-rule"),
            ("mid-rule", "abs-rule"),
        ]
        result = _build_subtypes_for_type({"abs-rule"}, hierarchy)
        assert "mid-rule" in result["abs-rule"]
        assert "leaf-rule" in result["abs-rule"]

    def test_self_not_included(self):
        hierarchy = [("child", "parent")]
        result = _build_subtypes_for_type({"parent"}, hierarchy)
        assert "parent" not in result["parent"]

    def test_leaf_type_has_empty_subtypes(self):
        hierarchy = [("leaf", "root")]
        result = _build_subtypes_for_type({"leaf"}, hierarchy)
        assert result["leaf"] == set()

    def test_only_computes_for_requested_types(self):
        hierarchy = [("child", "parent"), ("grandchild", "child")]
        result = _build_subtypes_for_type({"child"}, hierarchy)
        assert "parent" not in result
        assert "grandchild" in result["child"]

    def test_empty_hierarchy(self):
        result = _build_subtypes_for_type({"some-type"}, [])
        assert result["some-type"] == set()


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

    def test_lex_type_via_lex_ids_for_type(self):
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

    def test_abstract_rule_passes_via_subtype_in_internals(self):
        subtypes = {"abs-rule": {"conc-rule"}}
        deriv = _make_derivation(internals=["conc-rule"])
        result = _make_result(deriv)
        assert type_in_results("abs-rule", ["rule"], [result], {}, subtypes)

    def test_abstract_rule_fails_when_no_subtype_in_tree(self):
        subtypes = {"abs-rule": {"conc-rule"}}
        deriv = _make_derivation(internals=["other-rule"])
        result = _make_result(deriv)
        assert not type_in_results("abs-rule", ["rule"], [result], {}, subtypes)

    def test_abstract_lex_rule_passes_via_subtype_in_preterminals(self):
        subtypes = {"abs-lr": {"v_pst_olr"}}
        deriv = _make_derivation(preterminals=["v_pst_olr"])
        result = _make_result(deriv)
        assert type_in_results("abs-lr", ["lex-rule"], [result], {}, subtypes)

    def test_subtype_not_provided_does_not_raise(self):
        deriv = _make_derivation(internals=["conc-rule"])
        result = _make_result(deriv)
        assert not type_in_results("abs-rule", ["rule"], [result], {}, None)

    def test_transitive_subtype_passes(self):
        # abs → mid → leaf; leaf fires in tree; abs should pass
        subtypes = {"abs-rule": {"mid-rule", "leaf-rule"}}
        deriv = _make_derivation(internals=["leaf-rule"])
        result = _make_result(deriv)
        assert type_in_results("abs-rule", ["rule"], [result], {}, subtypes)


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
