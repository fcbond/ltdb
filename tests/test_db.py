"""Tests for web/db.py database query functions."""

from __future__ import annotations

import sqlite3

import pytest

from web.db import (
    calculate_offset_limit,
    get_gold,
    get_ltypes,
    get_phenomena_by_cx,
    get_phenomena_by_lexids,
    get_lxid,
    get_lxids,
    get_md,
    get_rules,
    get_sents,
    get_short_summary,
    get_summary,
    get_tb_summary,
    get_type,
    get_wrds_by_lexids,
    get_wrds_by_ltypes,
    holders,
    search_for,
)


class TestHolders:
    def test_single(self):
        assert holders([1]) == "?"

    def test_multiple(self):
        assert holders([1, 2, 3]) == "?,?,?"

    def test_empty(self):
        assert holders([]) == ""


class TestCalculateOffsetLimit:
    def test_want_more_than_exist(self):
        offset, limit = calculate_offset_limit(5, 10)
        assert offset == 0
        assert limit == 5

    def test_want_exactly_available(self):
        offset, limit = calculate_offset_limit(8, 8)
        assert offset == 0
        assert limit == 8

    def test_skip_first_20_percent(self):
        offset, limit = calculate_offset_limit(100, 8)
        assert offset == 20
        assert limit == 8

    def test_offset_adjusted_when_too_few_remain(self):
        # N=10, L=8 → 20% offset=2, remaining=8 ≥ 8, so offset stays
        offset, limit = calculate_offset_limit(10, 8)
        assert offset == 2
        assert limit == 8

    def test_offset_clamped_when_remainder_too_small(self):
        # N=9, L=8 → 20% offset=2 (round), remaining=7 < 8, so offset=9-8=1
        offset, limit = calculate_offset_limit(9, 8)
        assert offset == 1
        assert limit == 8


class TestGetMd:
    def test_returns_dict(self, mem_conn):
        md = get_md(mem_conn)
        assert isinstance(md, dict)

    def test_grammar_name(self, mem_conn):
        md = get_md(mem_conn)
        assert md["GRAMMAR_NAME"] == "Test Grammar"

    def test_website(self, mem_conn):
        md = get_md(mem_conn)
        assert md["WEBSITE"] == "https://example.com"

    def test_examples_stored_as_json(self, mem_conn):
        import json

        md = get_md(mem_conn)
        examples = json.loads(md["EXAMPLES"])
        assert isinstance(examples, list)
        assert len(examples) == 2


class TestGetRules:
    def test_returns_list(self, mem_conn):
        results = get_rules(mem_conn)
        assert isinstance(results, list)

    def test_rule_present(self, mem_conn):
        results = get_rules(mem_conn)
        types = [r[0] for r in results]
        assert "hd-cmp_c" in types

    def test_root_present(self, mem_conn):
        results = get_rules(mem_conn)
        types = [r[0] for r in results]
        assert "root" in types

    def test_lex_type_excluded(self, mem_conn):
        results = get_rules(mem_conn)
        statuses = [r[3] for r in results]
        assert "lex-type" not in statuses


class TestGetLtypes:
    def test_returns_list(self, mem_conn):
        results = get_ltypes(mem_conn)
        assert isinstance(results, list)

    def test_noun_le_present(self, mem_conn):
        results = get_ltypes(mem_conn)
        types = [r[0] for r in results]
        assert "noun-le" in types

    def test_verb_le_present(self, mem_conn):
        results = get_ltypes(mem_conn)
        types = [r[0] for r in results]
        assert "verb-le" in types


class TestSearchFor:
    def test_find_by_orth(self, mem_conn):
        results = search_for(mem_conn, "dog")
        assert "lemmas" in results

    def test_find_by_type_glob(self, mem_conn):
        results = search_for(mem_conn, "noun*")
        assert any(results.values())

    def test_no_results_unknown(self, mem_conn):
        results = search_for(mem_conn, "zzznomatch")
        assert all(len(v) == 0 for v in results.values())

    def test_find_predicate(self, mem_conn):
        results = search_for(mem_conn, "_dog_n_1")
        assert "predicates" in results


class TestGetType:
    def test_existing_type(self, mem_conn):
        info = get_type(mem_conn, "noun-le")
        assert info
        assert info["status"] == "lex-type"

    def test_missing_type_returns_empty(self, mem_conn):
        info = get_type(mem_conn, "nonexistent-type")
        assert info == {}

    def test_type_has_tdl(self, mem_conn):
        info = get_type(mem_conn, "noun-le")
        assert info.get("tdl") == "noun-le := noun."

    def test_verb_le(self, mem_conn):
        info = get_type(mem_conn, "verb-le")
        assert info["status"] == "lex-type"
        assert info.get("docstring") == "A verb lexical type."

    def test_rule_type(self, mem_conn):
        info = get_type(mem_conn, "hd-cmp_c")
        assert info["status"] == "rule"


class TestGetLxids:
    def test_noun_le_has_dog(self, mem_conn):
        result = get_lxids(mem_conn, "noun-le")
        assert "dog_n1" in result

    def test_verb_le_has_bark(self, mem_conn):
        result = get_lxids(mem_conn, "verb-le")
        assert "bark_v1" in result

    def test_nonexistent_type_returns_empty(self, mem_conn):
        result = get_lxids(mem_conn, "no-such-type")
        assert result == {}

    def test_returns_orth_and_freq(self, mem_conn):
        result = get_lxids(mem_conn, "noun-le")
        orth, freq = result["dog_n1"]
        assert orth == "dog"
        assert freq >= 0


class TestGetLxid:
    def test_dog_n1_has_words(self, mem_conn):
        result = get_lxid(mem_conn, "dog_n1")
        assert "dog_n1" in result

    def test_unknown_lexid_returns_empty(self, mem_conn):
        result = get_lxid(mem_conn, "zzz_unknown")
        assert result == {}


class TestGetWrdsByLexids:
    def test_dog_words(self, mem_conn):
        words = get_wrds_by_lexids(mem_conn, ["dog_n1"])
        assert "dog" in words["dog_n1"]

    def test_empty_lexids(self, mem_conn):
        words = get_wrds_by_lexids(mem_conn, [])
        assert dict(words) == {}


class TestGetWrdsByLtypes:
    def test_returns_words_for_types(self, mem_conn):
        words = get_wrds_by_ltypes(mem_conn)
        assert "noun-le" in words or "verb-le" in words


class TestGetSents:
    def test_empty_psids(self, mem_conn):
        result = get_sents(mem_conn, [])
        assert dict(result) == {}

    def test_known_sentence(self, mem_conn):
        result = get_sents(mem_conn, [("gold", 1)])
        assert ("gold", 1) in result
        sent = result["gold", 1]
        assert sent[1] == "dog"

    def test_unknown_psid_returns_empty(self, mem_conn):
        result = get_sents(mem_conn, [("nosuchprofile", 999)])
        assert dict(result) == {}


class TestGetGold:
    def test_empty_psids(self, mem_conn):
        result = get_gold(mem_conn, [])
        assert dict(result) == {}

    def test_no_gold_data_for_seed(self, mem_conn):
        result = get_gold(mem_conn, [("gold", 1)])
        assert dict(result) == {}


class TestGetSummary:
    def test_returns_dict(self, mem_conn):
        result = get_summary(mem_conn)
        assert isinstance(result, dict)

    def test_lex_type_counted(self, mem_conn):
        result = get_summary(mem_conn)
        assert "lex-type" in result

    def test_rule_counted(self, mem_conn):
        result = get_summary(mem_conn)
        assert "rule" in result


class TestGetTbSummary:
    def test_returns_dict_with_keys(self, mem_conn):
        result = get_tb_summary(mem_conn)
        assert "Profiles" in result
        assert "Sents" in result
        assert "Tokens" in result

    def test_sentence_count(self, mem_conn):
        result = get_tb_summary(mem_conn)
        assert result["Sents"] == 1


class TestGetPhenomenaByLexids:
    def test_no_sentences_returns_zero(self, mem_conn):
        maxp, phenom = get_phenomena_by_lexids(mem_conn, ["zzz_unknown"])
        assert maxp == 0
        assert dict(phenom) == {}

    def test_known_lexid_finds_sentence(self, mem_conn):
        maxp, phenom = get_phenomena_by_lexids(mem_conn, ["dog_n1"])
        assert maxp == 1
        assert ("gold", 1) in phenom

    def test_multiple_lexids(self, mem_conn):
        maxp, phenom = get_phenomena_by_lexids(mem_conn, ["dog_n1", "bark_v1"])
        assert maxp == 1

    def test_empty_lexids_returns_zero(self, mem_conn):
        maxp, phenom = get_phenomena_by_lexids(mem_conn, [])
        assert maxp == 0

    def test_phenomena_contains_word_positions(self, mem_conn):
        _, phenom = get_phenomena_by_lexids(mem_conn, ["dog_n1"])
        positions = phenom["gold", 1]
        assert len(positions) >= 1
        assert all(isinstance(p, tuple) and len(p) == 2 for p in positions)


class TestGetPhenomenaByCx:
    def _seed_typind(self, conn):
        conn.execute(
            "INSERT INTO typind VALUES ('hd-cmp_c', 'gold', 1, 0, 3)"
        )
        conn.commit()

    def test_no_matches_returns_zero(self, mem_conn):
        maxp, phenom = get_phenomena_by_cx(mem_conn, "no-such-cx")
        assert maxp == 0
        assert dict(phenom) == {}

    def test_known_cx_finds_sentence(self, mem_conn):
        self._seed_typind(mem_conn)
        maxp, phenom = get_phenomena_by_cx(mem_conn, "hd-cmp_c")
        assert maxp == 1
        assert ("gold", 1) in phenom

    def test_phenomena_contains_span(self, mem_conn):
        self._seed_typind(mem_conn)
        _, phenom = get_phenomena_by_cx(mem_conn, "hd-cmp_c")
        spans = phenom["gold", 1]
        assert len(spans) >= 1
        assert all(isinstance(s, tuple) and len(s) == 2 for s in spans)


class TestGetShortSummary:
    def _make_grammar_db(self, base, name, doctests=0):
        """(Re)create a minimal on-disk grammar db under base/db/."""
        db_dir = base / "db"
        db_dir.mkdir(exist_ok=True)
        (db_dir / name).unlink(missing_ok=True)
        conn = sqlite3.connect(db_dir / name)
        conn.executescript("""
            CREATE TABLE meta  (att TEXT, val TEXT);
            CREATE TABLE types (typ TEXT, status TEXT);
            CREATE TABLE sent  (sid INTEGER, profile TEXT);
        """)
        conn.execute("INSERT INTO meta VALUES ('GRAMMAR_NAME', 'Testish')")
        conn.execute("INSERT INTO types VALUES ('noun-le', 'lex-entry')")
        if doctests:
            conn.execute("CREATE TABLE doctest (typ TEXT)")
            conn.executemany(
                "INSERT INTO doctest VALUES (?)", [("noun-le",)] * doctests
            )
        conn.commit()
        conn.close()

    def test_doctests_zero_without_table(self, tmp_path):
        self._make_grammar_db(tmp_path, "old_1.0.db")
        summ = get_short_summary(str(tmp_path), ["old_1.0.db"])
        assert summ["old_1.0.db"]["DOCTESTS"] == 0

    def test_doctests_counted(self, tmp_path):
        self._make_grammar_db(tmp_path, "doc_1.0.db", doctests=3)
        summ = get_short_summary(str(tmp_path), ["doc_1.0.db"])
        assert summ["doc_1.0.db"]["DOCTESTS"] == 3
        assert summ["doc_1.0.db"]["LEXICON"] == 1

    def test_rebuilt_db_is_reread(self, tmp_path):
        """A rebuilt db file must not be served stale from the cache."""
        self._make_grammar_db(tmp_path, "re_1.0.db")
        summ = get_short_summary(str(tmp_path), ["re_1.0.db"])
        assert summ["re_1.0.db"]["DOCTESTS"] == 0
        self._make_grammar_db(tmp_path, "re_1.0.db", doctests=2)
        summ = get_short_summary(str(tmp_path), ["re_1.0.db"])
        assert summ["re_1.0.db"]["DOCTESTS"] == 2
