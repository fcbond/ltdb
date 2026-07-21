"""Tests for doc/esd-phenomena/gen_snippets.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "doc" / "esd-phenomena")
)

import gen_snippets

ENTRY = {
    "description": "A full NP is followed by another nominal phrase.",
    "fingerprint": "appos[ARG1 x1, ARG2 x2]\n[ARG0 x1]\n[ARG0 x2]\n",
    "grew-query": 'pattern { A [pred="appos"] }',
    "url": "https://delph-in.github.io/docs/erg/ErgSemantics_Apposition/",
}


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point the module at a throwaway snippets tree, not the real one."""
    default_html = tmp_path / "_default.html"
    default_html.write_text(
        "<ul>\n"
        f"      {gen_snippets.BEGIN}\n"
        f"      {gen_snippets.END}\n"
        "</ul>\n"
    )
    monkeypatch.setattr(gen_snippets, "SNIPPETS_DIR", tmp_path)
    monkeypatch.setattr(gen_snippets, "ERS_DIR", tmp_path / "ers")
    monkeypatch.setattr(gen_snippets, "DEFAULT_HTML", default_html)
    return tmp_path, default_html


def test_write_req_includes_description_fingerprint_and_query(isolated_dirs):
    tmp_path, _ = isolated_dirs
    gen_snippets.write_req("apposition", ENTRY)
    text = (tmp_path / "ers" / "apposition.req").read_text()
    assert "A full NP is followed" in text
    assert "appos[ARG1 x1, ARG2 x2]" in text
    assert ENTRY["url"] in text
    assert text.rstrip().endswith(ENTRY["grew-query"])


def test_snippet_list_html_is_sorted_and_links_to_ers_dir():
    html = gen_snippets.snippet_list_html({"vocatives": ENTRY, "apposition": ENTRY})
    apposition_pos = html.index("apposition")
    vocatives_pos = html.index("vocatives")
    assert apposition_pos < vocatives_pos
    assert 'snippet-file="ers/apposition.req"' in html
    assert 'class="inter"' in html


def test_main_writes_snippets_and_updates_markers(isolated_dirs, monkeypatch):
    tmp_path, default_html = isolated_dirs
    monkeypatch.setattr(
        gen_snippets, "load_phenomena", lambda: {"apposition": ENTRY}
    )
    gen_snippets.main()
    assert (tmp_path / "ers" / "apposition.req").is_file()
    html = default_html.read_text()
    assert gen_snippets.BEGIN in html and gen_snippets.END in html
    assert 'snippet-file="ers/apposition.req"' in html


def test_main_errors_without_markers(isolated_dirs, monkeypatch):
    tmp_path, default_html = isolated_dirs
    default_html.write_text("<ul></ul>\n")
    monkeypatch.setattr(
        gen_snippets, "load_phenomena", lambda: {"apposition": ENTRY}
    )
    with pytest.raises(SystemExit):
        gen_snippets.main()
