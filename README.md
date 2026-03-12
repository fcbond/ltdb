# Linguistic Type Data-Base (ltdb)

The Linguistic Type Database (LTDB, née Lextype DB), describes types and
rules of a DELPH-IN grammar with frequency information from the
treebank. Lexical types can be seen as detailed parts-of-speech.
Information about the types are constructed from the linguists
documentation in the grammar, a kind of literate programming.

## Development setup

```bash
uv sync --extra dev   # installs app + ruff
uv run ruff check .   # lint
uv run ruff format .  # format
```

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

- `<ex>text` — grammatical example
- `<nex>text` — ungrammatical example (prefixed ∗)
- `<mex>text` — marginal example (prefixed ⊛)
- `<name lang='xx'>Name</name>` — name of the type in language `xx`

There is `more documentation <http://moin.delph-in.net/LkbLtdb>`__ at
the DELPH-IN Wiki.

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
