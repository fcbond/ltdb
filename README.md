# Linguistic Type Data-Base (ltdb)

The Linguistic Type Database (LTDB, née Lextype DB), describes types and
rules of a DELPH-IN grammar with frequency information from the
treebank. Lexical types can be seen as detailed parts-of-speech.
Information about the types are constructed from the linguists
documentation in the grammar, a kind of literate programming.

## Development setup

```bash
uv sync --extra dev        # installs app + dev dependencies (ruff, pytest, playwright)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pytest              # unit + integration tests (no browser required)
playwright install         # download browser binaries (first time only)
uv run pytest tests/test_ui.py  # Playwright UI tests
```

## Architecture notes

**Grammar databases** — each grammar is a single SQLite file in `web/db/`.
The app discovers available grammars at runtime by listing that directory, so
dropping in or removing a `.db` file takes effect immediately without a
restart.

**Home page summary cache** — loading the home page would normally open every
`.db` file to read its name, rule count, lexicon size, and tree count (one
query per grammar).  Instead, `home()` computes a fingerprint of the `db/`
directory — a frozenset of `(filename, mtime, size)` for every `.db` file —
and caches the query results alongside it.  The cache is invalidated
automatically whenever a grammar is added, removed, or replaced (size or
modification time changes).  Each gunicorn worker maintains its own in-process
cache; a fresh worker recomputes on its first request.

**Grammar selection** — the active grammar is stored in the Flask session
(`session["grm"]`).  A `@before_request` hook also accepts a `?grm=` query
parameter on any URL, which updates the session and is transparent to all
routes.

**Parse demo** — only grammars that have a compiled `.dat` file alongside
their `.db` appear in the demo page.  The Preprocess toggle (see
"Morphological analyzers" below) only appears for grammars with an analyzer
actually installed, not just configured.  Generate (`/generate`) additionally
requires generation roots in the ACE config, but the demo doesn't reliably
distinguish that from other causes of zero realisations -- ACE's "unknown in
the semantic index" diagnostic isn't captured in `response.get("NOTES")`, so
the friendly-error path that's meant to catch it rarely fires in practice.
`generate_sentence()` sends ACE its own untouched SimpleMRS string (not a
value round-tripped through pydelphin's mrsjson, which normalises away each
predicate's "_rel" suffix -- some grammars' compiled semantic index needs it
verbatim) via `parse_sentence()`'s `mrs_raw` field.

**TDL rendering** — `web/ltdb.py` handles docstring parsing (`munge_desc`)
and Markdown-to-HTML conversion (`docstring2html`).  `web/routes.py` handles
TDL syntax highlighting with clickable type links (`tdl2html`) using
`pygments` and `pydelphin`'s TDL lexer.

## Morphological analyzers

Some grammars delegate tokenization or morphology to an external analyzer
and can't parse raw orthographic text in the demo.  `web/preprocess.py` is a
small pluggable registry that runs one before ACE, matched by a grammar's
`ISO_CODE` metadata field (falling back to `SHORT_GRAMMAR_NAME` for a few
hardcoded cases) — see `_ISO_ALIASES`/`_SHORTNAME_ISO` in that module for the
exact matching rules.  It's entirely optional: a grammar with no registered
analyzer (e.g. the ERG) is unaffected, and one whose tool isn't installed
degrades to parsing the raw input, with a note in the response explaining
why.

| ISO    | Analyzer | Install                                            | Config |
|--------|----------|-----------------------------------------------------|--------|
| `jpn`  | MeCab    | `apt install mecab mecab-ipadic-utf8`                | `MECAB_BIN` (default `mecab`) |
| `cmn`  | jieba    | `pip install jieba` into the app's own venv          | — |
| `kal`  | KARMA    | `pip install git+https://github.com/alexhsu-nlp/karma.git` into the app's own venv | — |
| `spa`  | FreeLing | separate, heavier install; see `scripts/install_freeling.sh` in a grammary checkout | `SRG_YY_CMD` (shell command reading a sentence on stdin, writing ACE's `-y --yy-rules` YY lattice format on stdout) |

Set `LTDB_ANALYZERS` to a comma-separated list of ISO codes to restrict which
analyzers are active (e.g. `jpn,cmn,kal` to disable Spanish without
uninstalling anything); unset means all registered analyzers are enabled
(individually still gated on their tool actually being installed).  The
demo's Preprocess toggle only appears for a grammar whose analyzer is both
registered *and* available — see `_installed_analyzer()` in `web/routes.py`.

## Quick Start

A separate database is made for each grammar.  The description for the grammar is read from the METADATA, a single project may have multiple grammars.

Compile a database with:

```
$ python scripts/grm2db.py --outdir web/db path/to/METADATA
```

Add `--ace` to also compile an ACE `.dat` file (required for the parse demo):

```
$ python scripts/grm2db.py --outdir web/db --ace path/to/METADATA
```

Run `python scripts/setup_ace.py` first to download the ACE binary if it is
not already on your PATH.

Options:
- `--checkgrm` only includes treebanks made by the same grammar version
- `--outdir`   output directory (a temporary directory is used otherwise)
- `--ace`      also compile a `.dat` file for the parse/generate demo
- `--ace-bin`  path to ACE binary (default: search PATH then `etc/ace-*/ace`)
- `--doctest`  parse all TDL docstring examples through ACE and store results
               in the `doctest` table of the grammar database (requires `--ace`
               or a pre-existing `.dat` in the output directory)
- `--jobs`     with `--doctest`: number of parallel ACE processes
               (0 = auto-sized from CPUs and available memory)
- `--grew`     also export the gold trees and DMRS as grew JSON corpora next
               to the database, ready for `./run.sh --grew-match`; results
               link back to LTDB via relative URLs that the grew-match
               backend expands with `$LTDB_BASE_URL` at serve time

The grammars are read by a web application written using Flask.
See [Install.md](Install.md) for deployment instructions.

## METADATA best practices

Each grammar needs a TOML-formatted `METADATA` file. The fields recognised by ltdb are:

| Field | Type | Required | Description |
|---|---|---|---|
| `GRAMMAR_NAME` | string | yes | Full grammar name shown in the UI |
| `SHORT_GRAMMAR_NAME` | string | yes | Short name used for the database filename |
| `WEBSITE` | string | | Grammar project homepage URL |
| `LICENSE` | string | | License name or URL |
| `ACE_CONFIG_FILE` | string | yes | Path to the ACE config file (relative to METADATA) |
| `TSDB_ROOTS` | list of strings | | Directories containing treebank profiles (default: `["tsdb/gold/"]`) |
| `PROFILES` | list of strings | | Specific profile names to include (default: all found under `TSDB_ROOTS`) |
| `EXAMPLES` | list of strings | | Example sentences shown in the parse demo and always available in its history dropdown |
| `DESCRIPTION` | string (Markdown) | | Free-form prose shown at the top of the grammar page, above the metadata table |

`DESCRIPTION` is rendered with the same Markdown-to-HTML pipeline as docstrings
(`web/ltdb.py`'s `render_markdown`) and kept out of the generic metadata table (a raw-text
table row is a poor fit for prose, especially anything multi-paragraph); see
`_grammar_description`/`_table_meta` in `web/routes.py`.

The `EXAMPLES` field is especially useful for the demo page: the most recent one is
pre-loaded into the input box, and the full list stays available via the input's native
`<datalist>` suggestion popup every time that grammar is selected -- merged in fresh
client-side (not stored in `localStorage`), so it can never get evicted as the user tries
their own sentences, and a METADATA change takes effect immediately. A browser filters that
popup to options matching whatever's already typed, so the input box's clear button doubles
as a hint that there's more to see: a down-caret (rather than the usual "x") when the box is
empty but there's a non-empty history/examples list for the selected grammar -- clicking it
clears the box (an empty value matches everything, so the full list shows) and focuses it.

Example `METADATA`:

```toml
GRAMMAR_NAME = "English Resource Grammar"
SHORT_GRAMMAR_NAME = "erg"
WEBSITE = "https://delph-in.github.io/docs/erg/"
LICENSE = "MIT"
ACE_CONFIG_FILE = "ace/config.tdl"
TSDB_ROOTS = ["tsdb/gold/"]
EXAMPLES = [
  "Abrams hired two competent programmers.",
  "The dog chases the cat.",
  "Kim arrived.",
]
DESCRIPTION = """
A broad-coverage, linguistically precise grammar of English, developed since
1993 within the LinGO Lab at Stanford's CSLI. See the [ERG
docs](https://delph-in.github.io/docs/erg/HomePage/) for background.
"""
```

## URL grammar selection

Any page accepts a `?grm=` query parameter to select a grammar directly,
without going through the home page form:

```
/ltdb?grm=yue_2023.01.10          → selects grammar, redirects to grammar page
/ltdb/demo?grm=yue_2023.01.10     → opens demo with that grammar active
/ltdb/grammar.html?grm=erg_2025   → opens grammar summary for the ERG
/ltdb/type/noun?grm=erg_2025      → opens type page with the ERG selected
```

The `.db` extension is optional. The grammar name must match the stem of a
`.db` file in `web/db/`; unrecognised names are silently ignored and the
current session grammar is preserved.

## Docstring format

TDL docstrings are rendered as Markdown. Standard Markdown formatting
(headings, bold, italic, lists, code) is supported. The following ltdb-specific
tags are also recognised:

- `<ex>text` — grammatical example: the type should appear in the derivation tree
- `<nex>text` — negative example (prefixed ∗): the type should be absent from all parses
- `<mex>text` — marginal example (prefixed ⊛): handled by a mal-rule; tested like `<ex>`
- `<name lang='xx'>Name</name>` — name of the type in language `xx`
- `<description>text` — starts a Description section
- `<features>` — starts a Features section
- `<history>` — starts a History section
- `<notes>` — starts a Notes section
- `<todo>` — starts a Todo section

Raw HTML in docstrings is escaped. Tags that are not listed above are displayed
literally until they are explicitly supported.

There is `more documentation <http://moin.delph-in.net/LkbLtdb>`__ at
the DELPH-IN Wiki.

## Searching with grew-match

The trees and DMRS in a compiled database can be searched by structure
with [grew-match](https://grew.fr/grew_match/).  Export them with:

```
$ python scripts/db2grew.py web/db/GRAMMAR.db
```

(or build and export in one go with `grm2db.py --grew`), then serve
the exported corpora with a local grew-match instance and set
`LTDB_GREW_MATCH_URL` to add a link to it in the LTDB navigation bar.
In development, `./run.sh --grew-match` does all of this and starts
both servers together, serving the corpora of every exported grammar.
See [doc/grew-match.md](doc/grew-match.md) for setup and example
queries.

## Docstring testing

The `<ex>`, `<nex>`, and `<mex>` tags are testable: every tagged
sentence is parsed through ACE and the documented type is checked
against the resulting derivations (as node entity, `--udx=all` type
annotation, or inheriting lexical entry), giving one verdict per
example: `PASS`, `FAIL-no-parse`, `FAIL-type-absent`, or
`FAIL-type-in-tree`.  There are three ways to run them:

```bash
# while building the database — results go to the doctest table and
# are shown on type pages and the "Docstring Tests" tab
python scripts/grm2db.py --outdir web/db --ace --doctest --jobs 0 \
    path/to/METADATA

# standalone — writes an itsdb profile of the results to /tmp/profile
# (skip with --no-profile) and a per-type report to stdout; --db and
# --report additionally store the verdicts
python scripts/parse_examples.py ace/config.tdl grammar.dat /tmp/profile \
    --db web/db/grammar.db --report results.txt -j 0

# dated itsdb profile inside the grammar, verdicts in i-comment
python scripts/docstring_profile.py ace/config.tdl grammar.dat
```

All runners can parse with multiple ACE processes (`--jobs 0` sizes
the worker count to the machine).  See
[doc/docstring-tests.md](doc/docstring-tests.md) for the tag
semantics, verdict definitions, matching rules, and full option
reference.

Types, instances in the same table, distinguished by status.


+----------+------------------------------------+-------------------+------+
|status    |thing                               | source            |  end |
+==========+====================================+===================+======+
|type      |normal type                         |                   |      |
+----------+------------------------------------+-------------------+------+
|lex-type  |lexical type                        |type + in lexicon  | _lt  |
+----------+------------------------------------+-------------------+------+
|lex-entry |lexical entry                       |                   | _le  |   
+----------+------------------------------------+-------------------+------+
|rule      |syntactic construction/grammar rule | LKB:\*RULES       | _c   |
+----------+------------------------------------+-------------------+------+
|lex-rule  | lexical rule                       | LKB:\*LRULES      | lr   |
+----------+------------------------------------+-------------------+------+
|inf-rule  |inflectional rule                   | LKB:\*LRULES +    | ilr  | 
+----------+------------------------------------+-------------------+------+
|          |            (inflectional-rule-pid )|                   |      |
+----------+------------------------------------+-------------------+------+
|          |orth-invariant inflectional rule    |                   | _ilr |
+----------+------------------------------------+-------------------+------+
|          |orth-changing inflectional rule     |                   | _olr |
+----------+------------------------------------+-------------------+------+
|          |orth-invariant derivational rule    |                   | _dlr | 
+----------+------------------------------------+-------------------+------+
|          |orth-changing derivation rule       |                   |_odlr |
+----------+------------------------------------+-------------------+------+
|          |punctuation affixation rule         |                   | _plr |
+----------+------------------------------------+-------------------+------+
|root      |root                                |                   |      |
+----------+------------------------------------+-------------------+------+


+--------+--------------------------------------+
| Symbol | Explanation                          |
+========+======================================+
|  ▲     | Unary, Headed                        |
+--------+--------------------------------------+
|  △	 | Unary, Non-Headed                    |
+--------+--------------------------------------+
|  ◭    | Binary, Left-Headed                  |
+--------+--------------------------------------+
|  ◮    | Binary, Right-Headed                 |
+--------+--------------------------------------+
|  ◬    | Binary, Non-Headed                   |
+--------+--------------------------------------+
