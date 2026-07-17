"""Unit tests for scripts/docstring_profile.py helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from docstring_profile import summarize, unique_profile_dir
from parse_examples import Example, Verdict


class TestUniqueProfileDir:
    def test_unused_name_kept(self, tmp_path):
        base = tmp_path / "docstring_2026-07-17"
        assert unique_profile_dir(base) == base

    def test_numeric_suffix_added_when_taken(self, tmp_path):
        base = tmp_path / "docstring_2026-07-17"
        base.mkdir()
        second = unique_profile_dir(base)
        assert second.name == "docstring_2026-07-17-2"
        second.mkdir()
        assert unique_profile_dir(base).name == "docstring_2026-07-17-3"


class TestSummarize:
    def _verdict(self, i_id, n_parses, found):
        return Verdict(Example(i_id, "s", "t", 1, "ex"), n_parses, found)

    def test_counts_by_verdict(self):
        verdicts = [
            self._verdict(1, 1, True),    # PASS
            self._verdict(2, 0, False),   # FAIL-no-parse
            self._verdict(3, 1, False),   # FAIL-type-absent
            self._verdict(4, 1, True),    # PASS
        ]
        out = summarize(verdicts)
        assert "4 docstring example(s)" in out
        assert "PASS" in out and "2" in out
        assert "FAIL-no-parse" in out
        assert "FAIL-type-absent" in out
