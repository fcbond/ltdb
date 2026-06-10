"""Tests for scripts/db2grew.py (grew JSON corpus export)."""

import json
import sqlite3
from pathlib import Path

import pytest
from delphin import derivation
from delphin.codecs import dmrsjson, simplemrs
from delphin.dmrs import from_mrs

import db2grew

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

MRS = """[ TOP: h0 INDEX: e2 [ e SF: prop TENSE: past MOOD: indicative PROG: - PERF: - ]
  RELS: < [ _the_q<0:3> LBL: h4 ARG0: x3 [ x PERS: 3 NUM: sg IND: + ] RSTR: h5 BODY: h6 ]
          [ _dog_n_1<4:7> LBL: h7 ARG0: x3 ]
          [ _bark_v_1<8:15> LBL: h1 ARG0: e2 ARG1: x3 ] >
  HCONS: < h0 qeq h1 h5 qeq h7 > ]"""

LEXTYPES = {"the_1": "d_-_the_le", "dog_n1": "n_-_c_le", "bark_v1": "v_-_le"}

META = {"sid": "1", "profile": "mrs", "text": "The dog barked."}


def deriv_json():
    """Return deriv_json exactly as gold2db.py stores it."""
    deriv = derivation.from_string(UDF)
    return json.dumps(deriv.to_dict(fields=["id", "entity", "score", "form", "tokens"]))


def dmrs_json():
    """Return dmrs_json exactly as gold2db.py stores it."""
    return dmrsjson.encode(from_mrs(simplemrs.decode(MRS)))


@pytest.fixture
def gold_db(tmp_path):
    """Create a minimal LTDB database with one parsed sentence."""
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
        ("mrs", 1, "The dog barked.", deriv_json(), dmrs_json()),
        ("mrs", 2, "Broken.", "{}", "{}"),
        ("other", 3, "The dog barked.", deriv_json(), dmrs_json()),
    ]
    conn.executemany(
        """INSERT INTO gold (profile, sid, sent, deriv_json, dmrs_json)
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
    graph = db2grew.deriv_to_grew(deriv_json(), LEXTYPES, META)
    assert_valid_graph(graph)
    assert graph["meta"] == META
    assert graph["nodes"]["n731"] == {"rule": "sb-hd_mc_c"}
    assert graph["nodes"]["n728"] == {"rule": "n_sg_ilr"}
    assert graph["nodes"]["n727"] == {
        "lexid": "dog_n1",
        "lextype": "n_-_c_le",
        "form": "dog",
    }
    assert graph["order"] == ["t0", "t1", "t2"]
    forms = [graph["nodes"][tid]["form"] for tid in graph["order"]]
    assert forms == ["the", "dog", "barked."]
    assert {"src": "n731", "label": "2", "tar": "n730"} in graph["edges"]
    assert {"src": "n727", "label": "1", "tar": "t1"} in graph["edges"]


def test_deriv_root_without_id():
    data = {"entity": "root_strict", "daughters": [json.loads(deriv_json())]}
    graph = db2grew.deriv_to_grew(json.dumps(data), {}, META)
    assert_valid_graph(graph)
    assert graph["nodes"]["x0"] == {"rule": "root_strict"}
    assert {"src": "x0", "label": "1", "tar": "n731"} in graph["edges"]
    # unknown lexids still convert, just without a lextype feature
    assert graph["nodes"]["n727"] == {"lexid": "dog_n1", "form": "dog"}


def test_dmrs_to_grew():
    graph = db2grew.dmrs_to_grew(dmrs_json(), META)
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
    the = next(n for n in nodes if n["pred"] == "_the_q")
    assert "sense" not in the
    # ordered by cfrom: the < dog < bark
    preds = [graph["nodes"][nid]["pred"] for nid in graph["order"]]
    assert preds == ["_the_q", "_dog_n_1", "_bark_v_1"]
    labels = [e["label"] for e in graph["edges"]]
    assert {"1": "RSTR", "post": "H"} in labels
    assert {"1": "ARG1", "post": "NEQ"} in labels


def test_dmrs_property_names_are_sanitized():
    data = json.loads(dmrs_json())
    node = next(n for n in data["nodes"] if n["predicate"] == "_dog_n_1")
    node["sortinfo"]["PNG.PERNUM"] = "3rd"
    node["sortinfo"]["COG-ST"] = "cog-st"
    graph = db2grew.dmrs_to_grew(json.dumps(data), META)
    dog = next(n for n in graph["nodes"].values() if n["pred"] == "_dog_n_1")
    assert dog["PNG_PERNUM"] == "3rd"
    assert dog["COG_ST"] == "cog-st"
    assert "PNG.PERNUM" not in dog


def test_dmrs_undirected_link_becomes_mod():
    data = json.loads(dmrs_json())
    data["links"].append({"from": 10001, "to": 10002, "post": "EQ"})
    graph = db2grew.dmrs_to_grew(json.dumps(data), META)
    assert {"1": "MOD", "post": "EQ"} in [e["label"] for e in graph["edges"]]


@pytest.mark.parametrize("payload", [None, "", "{}", "not json"])
def test_empty_payloads_are_skipped(payload):
    assert db2grew.deriv_to_grew(payload, {}, META) is None
    assert db2grew.dmrs_to_grew(payload, META) is None


def test_main_end_to_end(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    assert [c["id"] for c in corpora] == ["TOY_1_0_trees", "TOY_1_0_dmrs"]
    for corpus in corpora:
        directory = Path(corpus["directory"])
        assert directory.is_dir()
        # the '{}' row is skipped: 2 of the 3 gold rows convert
        assert corpus["files"] == ["mrs__1.json", "other__3.json"]
        assert sorted(p.name for p in directory.iterdir()) == corpus["files"]
        for fname in corpus["files"]:
            graph = json.loads((directory / fname).read_bytes())
            assert_valid_graph(graph)
            assert graph["meta"]["text"] == "The dog barked."


def test_main_profiles_filter(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), "--profiles", "other", str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    assert all(c["files"] == ["other__3.json"] for c in corpora)


def test_main_trees_only(gold_db, tmp_path):
    out = tmp_path / "grew"
    db2grew.main(["--outdir", str(out), "--trees-only", str(gold_db)])
    corpora = json.loads((out / "corpora.json").read_bytes())
    assert [c["id"] for c in corpora] == ["TOY_1_0_trees"]
