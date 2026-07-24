"""Unit tests for scripts/tdl2db.py."""

from __future__ import annotations

import io

from tdl2db import read_cfg, read_grm


def _write_config(tmp_path, extra_lines=()):
    """Write a minimal ACE config + version file under tmp_path."""
    (tmp_path / "version.tdl").write_text('*grammar-version* "1.0".\n')
    lines = [
        'version := "version.tdl".',
        'grammar-top := "grammar.tdl".',
        'orth-path := "SYNSEM.LKEYS.KEYREL.PRED".',
        *extra_lines,
    ]
    config_file = tmp_path / "config.tdl"
    config_file.write_text("\n".join(lines) + "\n")
    return config_file


class TestReadCfgGenerationRoots:
    def test_generation_roots_present(self, tmp_path):
        cfg_file = _write_config(tmp_path, ["generation-roots := root."])
        cfg = read_cfg(str(cfg_file))
        assert cfg.get("generation-roots") == "root"

    def test_generation_roots_absent(self, tmp_path):
        cfg_file = _write_config(tmp_path)
        cfg = read_cfg(str(cfg_file))
        assert "generation-roots" not in cfg

    def test_generation_roots_commented_out_is_ignored(self, tmp_path):
        cfg_file = _write_config(tmp_path, [";generation-roots := root."])
        cfg = read_cfg(str(cfg_file))
        assert "generation-roots" not in cfg

    def test_generation_roots_unquoted_multiple_values(self, tmp_path):
        cfg_file = _write_config(tmp_path, ["generation-roots := root root_frag."])
        cfg = read_cfg(str(cfg_file))
        assert cfg.get("generation-roots") == "root root_frag"

    def test_active_line_after_commented_alternative(self, tmp_path):
        # mirrors real configs that keep a commented-out fallback root
        cfg_file = _write_config(
            tmp_path,
            [
                "generation-roots := root.",
                ";generation-roots := root_strict.",
            ],
        )
        cfg = read_cfg(str(cfg_file))
        assert cfg.get("generation-roots") == "root"


class TestReadCfgOrthPath:
    def test_space_separated_path_is_dotted(self, tmp_path):
        # ACE config syntax separates path segments with whitespace (e.g.
        # GG's "MORPH LIST FIRST STEM"), but Conjunction.get() expects a
        # dot-separated path
        cfg_file = _write_config(tmp_path, ["orth-path := MORPH LIST FIRST STEM."])
        cfg = read_cfg(str(cfg_file))
        assert cfg["orth-path"] == "MORPH.LIST.FIRST.STEM"

    def test_single_segment_path_is_unaffected(self, tmp_path):
        cfg_file = _write_config(tmp_path, ["orth-path := STEM."])
        cfg = read_cfg(str(cfg_file))
        assert cfg["orth-path"] == "STEM"

    def test_already_dotted_quoted_path_is_unaffected(self, tmp_path):
        cfg_file = _write_config(
            tmp_path, ['orth-path := "SYNSEM.LKEYS.KEYREL.PRED".']
        )
        cfg = read_cfg(str(cfg_file))
        assert cfg["orth-path"] == "SYNSEM.LKEYS.KEYREL.PRED"


class TestReadGrmRecursion:
    """Regression tests for the GG bug: types/lexemes silently dropped.

    GG's grammar-top file (german.tdl) pulls in the bulk of the grammar
    via a bare ":include" that is *not* wrapped in a :begin/:end block,
    and that included file is itself just a router of further :include
    statements with no type definitions of its own. Both levels of
    indirection must be followed for any of it to reach the database.
    """

    def test_bare_top_level_include_is_followed(self, tmp_path):
        # german.tdl-style: an :include with no enclosing :begin/:end
        (tmp_path / "grammar.tdl").write_text(':include "router".\n')
        # common.tdl-style: no direct type defs, just routes to leaves
        (tmp_path / "router.tdl").write_text(
            ':begin :type.\n:include "leaf".\n:end :type.\n'
        )
        (tmp_path / "leaf.tdl").write_text("foo := *top*.\n")

        cfg_file = _write_config(tmp_path)
        cfg = read_cfg(str(cfg_file))
        _, types, _, _ = read_grm(cfg, io.StringIO())

        assert "foo" in types

    def test_include_inside_environment_still_works(self, tmp_path):
        # sanity check: the common case (e.g. ERG) isn't broken by the fix
        (tmp_path / "grammar.tdl").write_text(
            ':begin :type.\n:include "leaf".\n:end :type.\n'
        )
        (tmp_path / "leaf.tdl").write_text("foo := *top*.\n")

        cfg_file = _write_config(tmp_path)
        cfg = read_cfg(str(cfg_file))
        _, types, _, _ = read_grm(cfg, io.StringIO())

        assert "foo" in types

    def test_shared_include_is_only_processed_once(self, tmp_path):
        # a file reachable via two different paths shouldn't be double-counted
        (tmp_path / "grammar.tdl").write_text(
            ':include "leaf".\n'
            ":begin :instance.\n"
            ':include "leaf".\n'
            ":end :instance.\n"
        )
        (tmp_path / "leaf.tdl").write_text("foo := *top*.\n")

        cfg_file = _write_config(tmp_path)
        cfg = read_cfg(str(cfg_file))
        tdls, types, hierarchy, _ = read_grm(cfg, io.StringIO())

        assert len(types["foo"]) == 1
        assert len(tdls) == 1

    def test_lex_entry_with_string_valued_keyrel_does_not_crash(self, tmp_path):
        # GG's lexicon stores the pred directly as a string under KEYREL
        # (SYNSEM.LKEYS.KEYREL "_foo_v_rel") rather than nesting it under
        # a PRED sub-feature (SYNSEM.LKEYS.KEYREL.PRED), unlike the ERG
        # convention the PRED/CARG extraction assumes. Descending further
        # into that string used to raise TypeError and, since the whole
        # file shared one try/except, silently discard every other entry
        # in the file too.
        (tmp_path / "grammar.tdl").write_text(
            ":begin :instance :status lex-entry.\n"
            ':include "lex".\n'
            ":end :instance.\n"
        )
        (tmp_path / "lex.tdl").write_text(
            "foo_le := word &\n"
            ' [ STEM < "foo" >,\n'
            '   SYNSEM.LKEYS.KEYREL "_foo_v_rel" ].\n'
            "bar_le := word &\n"
            ' [ STEM < "bar" >,\n'
            '   SYNSEM.LKEYS.KEYREL "_bar_v_rel" ].\n'
        )

        cfg_file = _write_config(tmp_path, ['orth-path := "STEM".'])
        cfg = read_cfg(str(cfg_file))
        _, _, _, les = read_grm(cfg, io.StringIO())

        assert set(les) == {"foo_le", "bar_le"}
        # the malformed PRED path resolves to None rather than crashing
        assert les["foo_le"][2] is None
