"""Unit tests for scripts/tdl2db.py."""

from __future__ import annotations

from tdl2db import read_cfg


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
