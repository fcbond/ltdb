"""Tests for on-the-fly derivation/MRS/DMRS conversion in web/ltdb.py."""

import pytest

from web.ltdb import deriv_to_dict, mrs_to_dicts

# Minimal valid UDF derivation string (two terminals)
_VALID_DERIV = (
    "(42 hpsg_rule 0.5 0 2 "
    "(1 word_a 0.9 0 1 (\"the\")) "
    "(2 word_b 0.8 1 2 (\"cat\")))"
)

# Minimal valid simplemrs string
_VALID_MRS = (
    "[ TOP: h0\n"
    "  INDEX: e2 [ e SF: prop ]\n"
    "  RELS: < [ _cat_n_1 LBL: h4 ARG0: x3 ] >\n"
    "  HCONS: < h0 qeq h4 > ]"
)


class TestDerivToDict:
    def test_valid_deriv_returns_dict(self):
        result = deriv_to_dict(_VALID_DERIV)
        assert isinstance(result, dict)
        assert "entity" in result

    def test_empty_string_returns_none(self):
        assert deriv_to_dict("") is None

    def test_none_returns_none(self):
        assert deriv_to_dict(None) is None

    def test_invalid_udf_returns_none_not_exception(self):
        assert deriv_to_dict("this is not a valid UDF string!!!") is None

    def test_invalid_udf_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="web.ltdb"):
            deriv_to_dict("not a UDF")
        assert any("deriv parse failed" in r.message for r in caplog.records)


class TestMrsToDicts:
    def test_valid_mrs_returns_dicts(self):
        mrs_d, dmrs_d = mrs_to_dicts(_VALID_MRS)
        assert isinstance(mrs_d, dict)
        assert isinstance(dmrs_d, dict)

    def test_empty_string_returns_none_pair(self):
        mrs_d, dmrs_d = mrs_to_dicts("")
        assert mrs_d is None
        assert dmrs_d is None

    def test_none_returns_none_pair(self):
        mrs_d, dmrs_d = mrs_to_dicts(None)
        assert mrs_d is None
        assert dmrs_d is None

    def test_invalid_mrs_returns_none_pair_not_exception(self):
        mrs_d, dmrs_d = mrs_to_dicts("not an MRS [ broken }")
        assert mrs_d is None
        assert dmrs_d is None

    def test_invalid_mrs_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="web.ltdb"):
            mrs_to_dicts("not an MRS")
        assert any("MRS parse failed" in r.message for r in caplog.records)
