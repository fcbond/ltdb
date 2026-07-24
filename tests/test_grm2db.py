"""Tests for scripts/grm2db.py database creation."""

from __future__ import annotations

from grm2db import make_db, meta_to_db


def test_make_db_creates_schema(tmp_path):
    conn = make_db(str(tmp_path), "g_1.0.db")
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert {"meta", "types"}.issubset(tables)


def test_make_db_replaces_existing_db(tmp_path):
    """A rerun must rebuild from scratch, not fail on existing tables."""
    conn = make_db(str(tmp_path), "g_1.0.db")
    conn.execute("INSERT INTO meta (att, val) VALUES ('stale', 'yes')")
    conn.commit()
    conn.close()

    conn = make_db(str(tmp_path), "g_1.0.db")
    rows = conn.execute("SELECT count(*) FROM meta").fetchone()[0]
    conn.close()
    assert rows == 0


def test_meta_to_db_stores_non_ascii_list_values_unescaped(tmp_path):
    """grammar.html's meta-data table prints att/val pairs as plain text
    without running them through json.loads, so a list-valued field
    (e.g. EXAMPLES) must be stored with literal UTF-8 characters rather
    than "\\uXXXX" escapes, or non-Latin-script examples show up as
    escape codes instead of the actual characters (as happened for
    Zhong's Chinese-script EXAMPLES)."""
    conn = make_db(str(tmp_path), "g_1.0.db")
    meta_to_db(conn, {"EXAMPLES": ["狗 跑"]})
    val = conn.execute(
        "SELECT val FROM meta WHERE att = 'EXAMPLES'"
    ).fetchone()[0]
    conn.close()
    assert val == '["狗 跑"]'
