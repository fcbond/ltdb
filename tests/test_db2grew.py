"""Tests for scripts/db2grew.py (grew JSON corpus export)."""

import json
import sqlite3
from pathlib import Path

import db2grew
import pytest

TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "tables.sql"

UDF = (
    "(731 sb-hd_mc_c 0.0 0 3"
    " (729 sp-hd_n_c 0.0 0 2"
    '  (726 the_1 0.0 0 1 ("the"))'
    "  (728 n_sg_ilr 0.0 1 2"
    '   (727 dog_n1 0.0 1 2 ("dog"))))'
    " (730 v_pst_olr 0.0 2 3"
    '  (724 bark_v1 0.0 2 3 ("barked."))))'
)

MRS = """[ TOP: h0 INDEX: e2 [ e SF: prop TENSE: past MOOD: indicative ]
  RELS: < [ _the_q<0:3> LBL: h4 ARG0: x3 [ x PERS: 3 NUM: sg IND: + ]
            RSTR: h5 BODY: h6 ]
          [ _dog_n_1<4:7> LBL: h7 ARG0: x3 ]
          [ _bark_v_1<8:15> LBL: h1 ARG0: e2 ARG1: x3 ] >
  HCONS: < h0 qeq h1 h5 qeq h7 > ]"""

LEXTYPES = {"the_1": "d_-_the_le", "dog_n1": "n_-_c_le", "bark_v1": "v_-_le"}

META = {"sid": "1", "profile": "mrs", "text": "The dog barked."}


@pytest.fixture
def gold_db(tmp_path):
    """Create a minimal LTDB database with parsed sentences."""
    db_path = tmp_path / "toy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(TABLES_SQL.read_text())
    conn.executemany(
        "INSERT INTO meta (att, val) VALUES (?, ?)",
        [("SHORT_GRAMMAR_NAME", "TOY"), ("Version", "1.0")],
    )
    conn.executemany(
        "INSERT INTO lex (lexid, typ) VALUES (?, ?)", sorted(LEXTYPES.items())
    )
    rows = [
        ("mrs", 1, "The dog barked.", UDF, MRS),
        ("mrs", 2, "Broken.", "", None),
        ("other", 3, "The dog barked.", UDF, MRS),
    ]
    conn.executemany(
        """INSERT INTO gold (profile, sid, sent, deriv, mrs)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def assert_valid_graph(graph):
    """Check grew JSON structural invariants."""
    assert set(graph["nodes"])
    for edge in graph["edges"]:
        assert edge["src"] in graph["nodes"]
        assert edge["tar"] in graph["nodes"]
    assert set(graph["order"]) <= set(graph["nodes"])


def test_deriv_to_grew():
    # internal nodes are numbered in pre-order:
    # n0 sb-hd_mc_c, n1 sp-hd_n_c, n2 the_1, n3 n_sg_ilr,
    # n4 dog_n1, n5 v_pst_olr, n6 bark_v1
    graph = db2grew.deriv_to_grew(UDF, LEXTYPES, META)
    assert_valid_graph(graph)
    assert graph["meta"] == META
    assert graph["nodes"]["n0"] == {"cat": "sb-hd_mc_c"}
    assert graph["nodes"]["n3"] == {"cat": "n_sg_ilr"}
    assert graph["nodes"]["n4"] == {
        "lexid": "dog_n1",
        "lextype": "n_-_c_le",
        "form": "dog",
    }
    # every node is ordered, in postorder: a node is placed right after
    # its rightmost descendant, so e.g. n4 (dog_n1, span 1-2) precedes
    # its unary-chain mother n3 (n_sg_ilr, span 1-2) -- same span,
    # deepest first -- and n3 precedes n1 (sp-hd_n_c, span 0-2), which
    # shares n3's right boundary -- narrower span first
    assert graph["order"] == ["t0", "n2", "t1", "n4", "n3", "n1", "t2", "n6", "n5", "n0"]
    terminal_ids = [nid for nid in graph["order"] if nid.startswith("t")]
    forms = [graph["nodes"][tid]["form"] for tid in terminal_ids]
    assert forms == ["the", "dog", "barked."]
    assert {"src": "n0", "label": "2", "tar": "n5"} in graph["edges"]
    assert {"src": "n4", "label": "1", "tar": "t1"} in graph["edges"]
    # word-to-word immediate precedence is no longer implicit in "order"
    # (constituent nodes are interleaved between words), so it is added
    # as an explicit edge between literally-consecutive surface tokens
    assert {"src": "t0", "label": {"adjacent": "y"}, "tar": "t1"} in graph["edges"]
    assert {"src": "t1", "label": {"adjacent": "y"}, "tar": "t2"} in graph["edges"]
    assert not any(
        e["label"] == {"adjacent": "y"} and e["src"] == "t0" and e["tar"] == "t2"
        for e in graph["edges"]
    )


def test_deriv_with_root_and_zero_ids():
    """ACE writes id 0 on every node and may add an id-less root."""
    udf = (
        "(root_strict "
        + UDF.replace("(731 ", "(0 ")
        .replace("(729 ", "(0 ")
        .replace("(726 ", "(0 ")
        .replace("(728 ", "(0 ")
        .replace("(727 ", "(0 ")
        .replace("(730 ", "(0 ")
        .replace("(724 ", "(0 ")
        + ")"
    )
    graph = db2grew.deriv_to_grew(udf, {}, META)
    assert_valid_graph(graph)
    # 8 derivation nodes plus 3 tokens, no id collisions
    assert len(graph["nodes"]) == 11
    assert graph["nodes"]["n0"] == {"cat": "root_strict"}
    assert {"src": "n0", "label": "1", "tar": "n1"} in graph["edges"]
    # unknown lexids still convert, just without a lextype feature
    assert graph["nodes"]["n5"] == {"lexid": "dog_n1", "form": "dog"}


def test_dmrs_to_grew():
    graph = db2grew.dmrs_to_grew(MRS, META)
    assert_valid_graph(graph)
    assert graph["meta"] == META
    nodes = list(graph["nodes"].values())
    dog = next(n for n in nodes if n["pred"] == "_dog_n_1")
    assert dog["lemma"] == "dog"
    assert dog["pos"] == "n"
    assert dog["sense"] == "1"
    assert dog["cvarsort"] == "x"
    assert dog["NUM"] == "sg"
    assert dog["cfrom"] == "4"
    bark = next(n for n in nodes if n["pred"] == "_bark_v_1")
    assert bark["TENSE"] == "past"
    assert bark["top"] == "yes"
    assert bark["index"] == "yes"
    # quantifiers are still surface-shaped and get no pos exception
    # (see dmrs_to_grew docstring / doc/grew-match.md)
    the = next(n for n in nodes if n["pred"] == "_the_q")
    assert the["lemma"] == "the"
    assert the["pos"] == "q"
    assert "sense" not in the
    # ordered by cfrom: the < dog < bark
    preds = [graph["nodes"][nid]["pred"] for nid in graph["order"]]
    assert preds == ["_the_q", "_dog_n_1", "_bark_v_1"]
    labels = [e["label"] for e in graph["edges"]]
    assert {"1": "RSTR", "post": "H"} in labels
    assert {"1": "ARG1", "post": "NEQ"} in labels


def test_dmrs_property_names_are_sanitized():
    mrs = MRS.replace("PERS: 3", "PERS: 3 PNG.PERNUM: 3rd COG-ST: cog-st")
    graph = db2grew.dmrs_to_grew(mrs, META)
    dog = next(n for n in graph["nodes"].values() if n["pred"] == "_dog_n_1")
    assert dog["PNG_PERNUM"] == "3rd"
    assert dog["COG_ST"] == "cog-st"
    assert "PNG.PERNUM" not in dog


def test_dmrs_null_lnk_is_tolerated():
    """simplemrs.encode writes <-1:-1> spans that decode rejects."""
    mrs = MRS.replace("_bark_v_1<8:15>", "_bark_v_1<-1:-1>")
    graph = db2grew.dmrs_to_grew(mrs, META)
    bark = next(n for n in graph["nodes"].values() if n["pred"] == "_bark_v_1")
    assert "cfrom" not in bark


def test_dmrs_nonstandard_predicate_is_tolerated():
    """Predicates like INDRA's _and_coord break pydelphin's lexer."""
    mrs = MRS.replace("_bark_v_1<8:15>", "_bark_coord<8:15>")
    graph = db2grew.dmrs_to_grew(mrs, META)
    assert any(n["pred"] == "_bark_coord" for n in graph["nodes"].values())


def test_dmrs_undirected_link_becomes_mod():
    # _loud_a shares the verb's label without an argument link to it
    mrs = """[ TOP: h0 INDEX: e2
  RELS: < [ _bark_v_1<0:6> LBL: h1 ARG0: e2 ]
          [ _loud_a_1<7:13> LBL: h1 ARG0: e3 ] >
  HCONS: < h0 qeq h1 > ]"""
    graph = db2grew.dmrs_to_grew(mrs, META)
    assert {"1": "MOD", "post": "EQ"} in [e["label"] for e in graph["edges"]]


@pytest.mark.parametrize("payload", [None, "", "not a derivation"])
def test_bad_payloads_are_skipped(payload):
    assert db2grew.deriv_to_grew(payload, {}, META) is None
    assert db2grew.dmrs_to_grew(payload, META) is None


def test_main_end_to_end(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    assert [c["id"] for c in corpora] == ["TOY_1_0_trees", "TOY_1_0_dmrs"]
    for corpus in corpora:
        assert corpus["kind"] == "json"
        directory = Path(corpus["directory"])
        assert directory.is_dir()
        # one file per profile, each a JSON list of that profile's
        # graphs; the empty "mrs" row is skipped, leaving one graph in
        # each of the two profiles' files
        assert corpus["files"] == ["mrs.json", "other.json"]
        assert sorted(p.name for p in directory.iterdir()) == corpus["files"]
        for fname in corpus["files"]:
            graphs = json.loads((directory / fname).read_bytes())
            assert len(graphs) == 1
            assert_valid_graph(graphs[0])
            assert graphs[0]["meta"]["text"] == "The dog barked."


def test_export_merges_multiple_sentences_into_one_profile_file(tmp_path):
    """Every graph identifies itself via meta.sent_id (grewlib reads
    that, not the filename -- see doc/grew-match.md), so a profile
    with several sentences can share one file."""
    db_path = tmp_path / "toy2.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(TABLES_SQL.read_text())
    conn.executemany(
        "INSERT INTO meta (att, val) VALUES (?, ?)",
        [("SHORT_GRAMMAR_NAME", "TOY"), ("Version", "1.0")],
    )
    conn.executemany(
        """INSERT INTO gold (profile, sid, sent, deriv, mrs)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("mrs", 1, "The dog barked.", UDF, MRS),
            ("mrs", 2, "The dog barked.", UDF, MRS),
        ],
    )
    conn.commit()
    conn.close()

    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), str(db_path)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    for corpus in corpora:
        assert corpus["files"] == ["mrs.json"]
        graphs = json.loads((Path(corpus["directory"]) / "mrs.json").read_bytes())
        assert {g["meta"]["sid"] for g in graphs} == {"1", "2"}


def test_export_writes_grew_log_on_conversion_failure(tmp_path):
    """Conversion failures logged by deriv_to_grew are collected into
    <db-stem>-grew.log next to the database."""
    db_path = tmp_path / "toy3.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(TABLES_SQL.read_text())
    conn.executemany(
        "INSERT INTO meta (att, val) VALUES (?, ?)",
        [("SHORT_GRAMMAR_NAME", "TOY"), ("Version", "1.0")],
    )
    conn.execute(
        """INSERT INTO gold (profile, sid, sent, deriv, mrs)
           VALUES (?, ?, ?, ?, ?)""",
        ("mrs", 1, "bad", "not a derivation", MRS),
    )
    conn.commit()
    conn.close()

    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), str(db_path)])
    log_path = tmp_path / "toy3-grew.log"
    assert log_path.is_file()
    assert "unreadable" in log_path.read_text()


def test_main_profiles_filter(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), "--profiles", "other", str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    assert all(c["files"] == ["other.json"] for c in corpora)


def test_main_ltdb_url(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(
        ["--outdir", str(out), "--ltdb-url", "http://localhost:5000/", str(gold_db)]
    )
    corpora = json.loads((out / "corpora.json").read_bytes())
    graphs = json.loads((Path(corpora[0]["directory"]) / "mrs.json").read_bytes())
    assert graphs[0]["meta"]["url"] == "http://localhost:5000/sent/mrs/1?grm=toy.db"


def test_main_relative_url_by_default(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    graphs = json.loads((Path(corpora[0]["directory"]) / "mrs.json").read_bytes())
    assert graphs[0]["meta"]["url"] == "/sent/mrs/1?grm=toy.db"


def test_main_trees_only(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), "--trees-only", str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    assert [c["id"] for c in corpora] == ["TOY_1_0_trees"]
