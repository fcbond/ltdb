# ESD phenomena as grew queries

`phenomena.toml` catalogues the semantic phenomena from the [ERG
Semantics Documentation
inventory](https://delph-in.github.io/docs/erg/ErgSemantics_Inventory/),
one table per phenomenon, with:

- `description` — a short characterization, after the ESD page;
- `fingerprint` — the ERS fingerprint, verbatim from the ESD page;
- `grew-query` — the fingerprint expressed as a
  [grew](https://grew.fr/) request over the DMRS corpora exported by
  `scripts/db2grew.py` (see [doc/grew-match.md](../grew-match.md)),
  so each phenomenon can be searched, counted and visualized in
  grew-match;
- `url` — the ESD page.

Paste a `grew-query` into grew-match, or count them all:

```bash
python check_phenomena.py ERG_ERG_2025_dmrs
```

## Translation notes

- DMRS (via pydelphin) renames the coordination and number-sequence
  roles `L-INDEX`/`R-INDEX` to `ARG1`/`ARG2`.
- MRS handle arguments restricted by qeq appear as edges with
  `post=H`; label sharing appears as `post=EQ` (or `HEQ`).
- Abstract predicates ("abstract_c", "quant", "ARG1+") are rendered
  with grew regular expressions or label alternations
  (`-[1=ARG1|ARG2]->`).
- grew feature regexes use OCaml `Str` syntax: alternation is `\|`
  and groups are `\(...\)`; plain `|` and `(...)` match literally
  and silently find nothing.
- The relational-nouns page has no fingerprint; its query is a rough
  approximation (any noun with an ARG1).

This catalogue is intended to migrate to the ERG repository
eventually; it is self-contained (the TOML plus this README and the
checker script) to make that move easy.
