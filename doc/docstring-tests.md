# Docstring tests

LTDB treats the example sentences in TDL docstrings as a test suite:
every tagged sentence is parsed with ACE and checked against the type
it documents.  This page covers how the tests work and the three ways
to run them.

## 1. Writing testable examples

Inside a TDL docstring (see "Docstring format" in the README for the
full tag list), three tags are testable:

```tdl
sb-hd_mc_c := basic_head_subj_phrase & ...
  """
  Subject–head phrase (main clause).

  <ex>The dog barks.
  <nex>Barks the dog.
  <mex>The dog bark.
  """.
```

| Tag | Meaning | Test |
|---|---|---|
| `<ex>` | grammatical example | must parse, and the documented type must appear in at least one derivation |
| `<mex>` | marginal example (handled by a mal-rule) | tested exactly like `<ex>` |
| `<nex>` | negative example | the type must not appear in any derivation; whether the sentence parses at all is informational |

Each tag takes one sentence, on the same line.  Blank examples are
skipped.

## 2. How checking works

`scripts/parse_examples.py` extracts the examples from every TDL file
named by the grammar's ACE config, then parses them with ACE using
`--rooted-derivations --udx=all`:

- `--rooted-derivations` puts the matching root condition at the top of
  each derivation, so examples documenting a *root* type can succeed.
  Root-condition types additionally get their own ACE invocation with
  `-r <root>`, because ACE would otherwise never choose a
  less-preferred root (e.g. `root_frag` when `root_strict` applies).
- `--udx=all` annotates every derivation node with its type: the
  lexical type of each lexeme and the phrase type of each rule.

A documented type counts as *found* if any of three checks succeeds in
any returned derivation:

1. **Entity match** — the type is a node's entity name (rules,
   lexical rules, lexical entries).
2. **Node-type match** — the type is a node's `--udx=all` annotation
   (lexical types and phrase types; this is the only check that can
   find generic/unknown-word types such as the ERG's `*-gen_le` and
   `*-unk_le`, which have no static lexicon entries).
3. **Lex-entry descendant match** — a preterminal is a lexical entry
   that inherits from the type (covers supertypes of the annotated
   lexical type).

### Verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | `<ex>`/`<mex>`: parsed and type found.  `<nex>`: type absent from all parses (including when nothing parsed) |
| `FAIL-no-parse` | `<ex>`/`<mex>`: the sentence did not parse |
| `FAIL-type-absent` | `<ex>`/`<mex>`: parsed, but the type is in no derivation |
| `FAIL-type-in-tree` | `<nex>`: the type appeared in a derivation |

### Parallelism

All runners accept `--jobs N` (`-j N` for the standalone scripts):
each batch is parsed by N ACE processes pulling sentences from a
shared queue.  `--jobs 0` sizes automatically: one process per CPU,
capped by available memory at ~4 GiB per worker (an ERG-sized grammar
needs about 2 GiB to parse plus 2 GiB to unpack).  Verdicts are
identical to a serial run; on the ERG (1,880 examples) 8 workers cut
the run from 80 s to 33 s.

## 3. Running the tests

### As part of a database build: `grm2db.py --doctest`

```bash
python scripts/grm2db.py --outdir web/db --ace --doctest --jobs 0 \
    path/to/METADATA
```

Stores one row per example in the `doctest` table of the grammar
database (`typ`, `sent`, `kind`, `wf`, `n_parses`, `type_found`,
`pass`, `verdict`).  The LTDB browser surfaces it in three places:

- the home page grammar table gains an `<ex>` column with each
  grammar's example count (shown only when some grammar has results);
- **type pages** show a "Docstring Tests" section with per-example
  pass/fail;
- the **"Docstring Tests" nav tab** (`/doctests.html`) lists every
  example, failures first (the tab only appears when the grammar has
  results).

### Standalone with database output: `parse_examples.py`

```bash
python scripts/parse_examples.py ace/config.tdl grammar.dat /tmp/profile \
    --db web/db/grammar.db \  # store results in the doctest table
    --report results.txt \    # also write the full text report
    --no-profile \            # skip the itsdb profile
    -j 0                      # parallel ACE, sized to the machine
```

Positional arguments: the ACE config, the compiled `.dat`, and a
directory for the itsdb profile.  Prints a full per-type report to
stdout.

### Dated profile in the grammar: `docstring_profile.py`

```bash
python scripts/docstring_profile.py ace/config.tdl grammar.dat
```

Writes a `[incr tsdb()]` profile into the grammar itself at

```
<grammar>/tsdb/run/docstring_YYYY-MM-DD
```

and prints a short summary:

```
69 docstring example(s)
  FAIL-no-parse         18
  FAIL-type-absent       5
  FAIL-type-in-tree      4
  PASS                  42
Profile written to .../tsdb/run/docstring_2026-07-17
```

Details:

- The grammar root is taken from the ACE config: it is the directory
  of the `grammar-top` file.  Override with `--grammar-dir DIR`, or
  bypass the whole convention with `--outdir DIR`.
- Rerunning on the same day appends `-2`, `-3`, … instead of
  overwriting an existing profile.
- The profile holds `item`, `parse` and `result` tables; each item's
  verdict is recorded in its `i-comment`, e.g.
  `type=pfv-marker-lex kind=ex verdict=PASS`, so profiles from
  different dates can be compared with the usual itsdb tools.
- `--ace-bin PATH` selects the ACE binary; `-j/--jobs` defaults to `0`
  (auto) for this script.
