"""Unit tests for web/static/js/ltdb-tree.js, run under node.

Covers the dict-derivation import (fromDict): pydelphin flattens the
surface token into `form` on the preterminal, and fromDict must rebuild
the lex-type > lex-entry > form chain so lexical entries and their
types stay visible in the demo tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not available")

TREE_JS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "web", "static", "js", "ltdb-tree.js")
)


def run_js(expr: str):
    """Evaluate *expr* with LTDBTree loaded as T and return it as JSON."""
    script = (
        f"const T = require({json.dumps(TREE_JS)});"
        f"console.log(JSON.stringify({expr}));"
    )
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


class TestFromDictLexicalChain:
    def test_preterminal_expands_to_type_entry_form(self):
        tree = run_js(
            "T.fromDict({entity: 'dog_n1', type: 'n_-_c_le', form: 'dog'})"
        )
        assert tree["name"] == "n_-_c_le"
        entry = tree["children"][0]
        assert entry["name"] == "dog_n1"
        leaf = entry["children"][0]
        assert leaf["form"] == "dog"
        assert leaf["leaf"] is True

    def test_entity_same_as_form_skips_entry_level(self):
        tree = run_js(
            "T.fromDict({entity: '\\u72d7', type: 'common-noun-lex', form: '\\u72d7'})"
        )
        assert tree["name"] == "common-noun-lex"
        assert tree["children"][0]["leaf"] is True

    def test_no_type_keeps_entity_over_form(self):
        # pre-udx derivations have no type annotation
        tree = run_js("T.fromDict({entity: 'dog_n1', form: 'dog'})")
        assert tree["name"] == "dog_n1"
        assert tree["children"][0]["form"] == "dog"

    def test_internal_node_keeps_type(self):
        tree = run_js(
            "T.fromDict({entity: 'sb-hd_mc_c', type: 'subjh_mc_rule',"
            " daughters: [{entity: 'dog_n1', type: 'n_-_c_le', form: 'dog'}]})"
        )
        assert tree["entity"] == "sb-hd_mc_c"
        assert tree["type"] == "subjh_mc_rule"
        assert tree["children"][0]["name"] == "n_-_c_le"

    def test_chain_node_classes(self):
        classes = run_js(
            "(function () {"
            " const t = T.fromDict({entity: 'dog_n1', type: 'n_-_c_le', form: 'dog'});"
            " return [T.classifyNode(t), T.classifyNode(t.children[0]),"
            "         T.classifyNode(t.children[0].children[0])];"
            "}())"
        )
        assert classes == ["lex-type", "lex-entry", "lemma"]

    def test_inserted_type_node_counts_as_label(self):
        # demo.html decides whether to show the label toggle by looking
        # for a node with `type` anywhere in the tree
        has_type = run_js(
            "(function () {"
            " const t = T.fromDict({entity: 'dog_n1', type: 'n_-_c_le', form: 'dog'});"
            " return (function check(n) {"
            "   return Boolean(n.type) || (n.children || []).some(check);"
            " }(t));"
            "}())"
        )
        assert has_type is True
