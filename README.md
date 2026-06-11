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
their `.db` appear in the demo page.  Generate (`/generate`) additionally
requires generation roots in the ACE config; grammars without them return a
friendly error rather than failing silently.

**TDL rendering** — `web/ltdb.py` handles docstring parsing (`munge_desc`)
and Markdown-to-HTML conversion (`docstring2html`).  `web/routes.py` handles
TDL syntax highlighting with clickable type links (`tdl2html`) using
`pygments` and `pydelphin`'s TDL lexer.

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
| `EXAMPLES` | list of strings | | Example sentences shown in the parse demo and used to seed input history |

The `EXAMPLES` field is especially useful for the demo page: sentences are pre-loaded
into the input box and the browser history list, so users can try the grammar immediately.

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

## Docstring testing

The `<ex>`, `<nex>`, and `<mex>` tags are testable: `parse_examples.py`
extracts every tagged sentence, parses it through ACE, and checks whether
the documented type appears in the derivation tree:

```bash
python scripts/parse_examples.py ace/config.tdl grammar.dat /tmp/profile \
    --db web/db/grammar.db     # store results in the grammar database
    --report results.txt       # also write a text summary
    --no-profile               # skip writing the itsdb profile
```

Results are stored in the `doctest` table of the grammar database and
surfaced in the LTDB browser:

- **Type pages** show a "Docstring Tests" section with per-example pass/fail.
- **"Docstring Tests" nav page** (`/doctests.html`) lists all examples for the
  grammar in a sortable table, with failures sorted first.

The `--doctest` flag on `grm2db.py` runs this automatically after building:

```bash
python scripts/grm2db.py --outdir web/db --ace --doctest path/to/METADATA
```

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
