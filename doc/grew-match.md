# Searching trees and DMRS with grew-match

LTDB can export the gold trees and DMRS from a grammar database as
[Grew](https://grew.fr/) JSON corpora, so that they can be searched by
structure with [grew-match](https://grew.fr/grew_match/) — for
example, "every sentence where rule X immediately dominates lexical
type Y" or "every predicate whose ARG1 is plural".

This is entirely optional: LTDB itself works without grew installed.

## 1. Export the corpora

```bash
python scripts/db2grew.py "web/db/ERG_(2020).db"
```

This writes (by default next to the database):

```
ERG_(2020)-grew/
  corpora.json          # grew corpora description
  ERG_2020_trees/       # one grew JSON graph per sentence
  ERG_2020_dmrs/
```

Options: `--outdir DIR`, `--profiles NAME` (repeatable),
`--trees-only`, `--dmrs-only`, `--ltdb-url BASE`.

With `--ltdb-url` (e.g. `--ltdb-url http://localhost:5000`), every
graph gets a `url` meta pointing at the LTDB sentence page
`/sent/<profile>/<sid>?grm=<dbfile>`, and grew-match shows a link
button on each match that jumps back into LTDB (sentence with its
tree, DMRS and MRS).  Re-export (and recompile) if the LTDB address
changes.

To serve several grammar databases from one grew-match instance, run
the script once per database with the same `--outdir` parent and merge
the `corpora.json` lists into one file.

### Graph encoding

**Trees** are constituency-style graphs built from the derivation:

- surface tokens are ordered leaf nodes with a `form` feature
- lexical entries have `lexid`, `lextype` and `form` features
- internal nodes carry the rule name in a `cat` feature
  (`rule` is a reserved word in grew requests)
- parent→child edges are labelled with the daughter position
  (`1`, `2`, ...)

**DMRS** are dependency-style graphs:

- one node per predicate, ordered by surface position, with features
  `pred`, `lemma`/`pos`/`sense` (surface predicates only), `cvarsort`,
  the morphosemantic properties (`NUM`, `PERS`, `TENSE`, ...),
  `carg`, `cfrom`/`cto`, and `top`/`index` flags; characters that
  clash with grew syntax in property names are replaced by `_`
  (e.g. `PNG.PERNUM` becomes `PNG_PERNUM`)
- links become edges with two label features: `1` (the role, e.g.
  `ARG1`) and `post` (e.g. `NEQ`); undirected `/EQ` links get the
  conventional role `MOD`

Every graph carries its `profile`, `sid` and `text` as metadata so
matches can be traced back to LTDB.

## 2. Install grew (once)

Grew is an OCaml program, installed through [opam](https://opam.ocaml.org/):

```bash
opam remote add grew "https://opam.grew.fr"
opam update
opam install dream dep2pictlib grew
```

## 3. Run a local grew-match

```bash
git clone https://github.com/grew-nlp/grew_match_quick
mkdir -p grew_match_quick/local_files/grew_match/instances
python3 grew_match_quick/grew_match_quick.py "ERG_(2020)-grew/corpora.json"
```

(The `mkdir` works around the script assuming an `instances/`
directory that newer `grew_match` checkouts no longer ship.)

JSON corpora are not compiled automatically on startup, so the first
time (and after re-exporting) compile them and make the backend
re-read the corpus descriptions — otherwise the web page shows
"Corpus not compiled":

```bash
grew compile -CORPUSBANK grew_match_quick/local_files/corpusbank
curl -X POST http://localhost:8899/reload
```

(Typing `r` at the grew_match_quick prompt also compiles, but it does
not refresh the compiled status; the `reload` call above does.)

Then open <http://localhost:8000> (ports configurable with
`--frontend_port`/`--backend_port`).

To show a **Grew-match** link in the LTDB navigation bar, set the
environment variable before starting the Flask app:

```bash
export LTDB_GREW_MATCH_URL=http://localhost:8000
```

Without the web UI, you can also search from the command line:

```bash
echo 'pattern { N [lemma="dog"] }' > q.req
grew grep -request q.req -i "ERG_(2020)-grew/ERG_2020_dmrs"
```

(`-i` takes a single file or a directory.)

Scale: the full ERG 2025 treebank (97,650 sentences, ~195k graph
files, 2 GB) compiles in about 100 seconds; the backend then uses
roughly 6 GB of RAM with both ERG corpora loaded and answers
searches in a couple of seconds.

## 4. Example requests

On the trees corpus:

```
pattern { N [cat="sb-hd_mc_c"] }              % a rule
pattern { L [lextype="d_-_the_le"] }           % a lexical type
pattern { T [form="dog"] }                     % a surface token
pattern { P [cat="sp-hd_n_c"]; P -[2]-> C;
          C [cat="n_sg_ilr"] }                % second daughter of a rule
```

On the DMRS corpus:

```
pattern { N [lemma="dog", pos="n"] }           % a predicate by lemma
pattern { G -[1=ARG1, post=NEQ]-> D }          % a link by role and post
pattern { Q -[1=RSTR]-> N; N [NUM="sg"] }      % quantifier of a singular
pattern { N [top="yes"] }                      % the TOP node
pattern { V -[1=ARG1]-> X; V -[1=ARG2]-> X }   % reflexive-ish structure
```

See the [grew request documentation](https://grew.fr/doc/request/) for
the full pattern language (negative conditions, `without`, regular
expressions over feature values, ...).

## 5. Working with the matches

In the grew-match web page, click a `sent_id` in the results list to
see the rendered graph with the matched nodes highlighted (the SVG
button opens the image on its own; the link button — with
`--ltdb-url` — opens the sentence in LTDB).

The web interface only exports matches as TSV or CoNLL, but the
corpora themselves are JSON: a match `ace/100` *is* the graph file
`<corpus>/ace__100.json` in the export directory.  For a JSON list of
all matches (sentence ids plus the matched nodes/edges), use the
command line:

```bash
grew grep -request q.req -i OUT/<corpus> > matches.json
```

Note (2026-06-11): the grew_match_dream backend on GitHub lags
behind the grew_match frontend and needs two patches to
`src/gmd_utils.ml` (then `dune build` and restart):

- `save_dep`/`save_dot` must encode each item's `meta` as a list of
  `{"key": ..., "value": ..., "sub": {}}` objects, not a plain map —
  otherwise the frontend's result list silently fails to render
  (a `meta.find is not a function` error in the browser console);
- `save_dep` must pass the `url` and `code` metas through (only
  `save_dot` does), or the link button never appears for
  dependency-rendered corpora.
