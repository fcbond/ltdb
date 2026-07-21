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

(or pass `--grew` to `scripts/grm2db.py` to export while building the
database, with `--ltdb-url` forwarded).

This writes (by default next to the database):

```
ERG_(2020)-grew/
  corpora.json          # grew corpora description
  ERG_2020_trees/       # one grew JSON file per treebank profile
  ERG_2020_dmrs/
```

Each file is a JSON *list* of that profile's graphs rather than one
graph per sentence: grewlib identifies a graph by its own `sent_id`
meta (see `Corpus.item_of_graph` in grewlib), never by the file it
lives in, so a corpus can freely group many graphs per file — and
profiles are large enough (thousands of sentences) that doing so keeps
the export directory to a handful of files instead of one per
sentence, which matters at ERG scale (~195k graphs; large enough to
overflow shell globs like `ls *.json`).

Options: `--outdir DIR`, `--profiles NAME` (repeatable),
`--trees-only`, `--dmrs-only`, `--ltdb-url BASE`, `--jobs N` (parallel
worker processes for graph conversion; `0` = auto from CPU count,
default `1`). `grm2db.py --grew` forwards its own `--jobs` here, and
also uses it to parallelize treebank-to-database processing across
profiles (see `gold2db.process_tsdb`) — each profile is independent,
so it is a natural parallelization unit for both steps; the sqlite
writes themselves stay on the main process, since a single
`Connection` cannot be shared across worker processes.

Conversion failures (unreadable derivations, MRSes pydelphin can't
decode) are logged per profile and collected into
`<db-stem>-grew.log` next to the database (e.g. `ERG_2020-grew.log`
next to `ERG_2020.db`) once the whole export finishes — the file is
only written if there was at least one failure. The live LTDB's
grammar summary page links this log, alongside the ACE compile and
docstring-test logs, for download (see `web/routes.py`'s
`download_log`).

Every graph gets a `url` meta pointing at the LTDB sentence page
`/sent/<profile>/<sid>?grm=<dbfile>`, and grew-match shows a link
button on each match that jumps back into LTDB (sentence with its
tree, DMRS and MRS).  The stored path is *relative*: the (patched)
backend prepends the base from the `LTDB_BASE_URL` environment
variable at serve time, so one export works for any LTDB address —
`run.sh` sets it automatically, and a production deployment sets it
when starting the backend.  Pass `--ltdb-url BASE` only to bake an
absolute base into the export instead (e.g. for corpora served by an
unpatched grew-match).

To serve several grammar databases from one grew-match instance,
export each one and let `./run.sh --grew-match` merge the
`corpora.json` lists (into `web/db/grew_corpora.json`); to do the
same by hand, concatenate the lists into one file.  When there are no
`web/db/*-grew` exports, `./run.sh --grew-match` falls back to an
existing `web/db/grew_corpora.json`, so a build pipeline can install a
pre-merged description there (the graph paths inside are absolute, so
the export directories can live anywhere).

`scripts/setup-grew-match.sh [CORPORA_JSON]` performs the setup ahead
of time: it clones grew_match_quick, the frontend and the patched
backend, builds the backend, and — when given a corpora description —
installs it as the corpusbank and runs `grew compile` over it.  A build
pipeline can call it after exporting so `./run.sh --grew-match` starts
without cloning or compiling anything.  `run.sh` stops any grew-match
already on its ports before starting, so the running instance always
serves the corpora just built.

### Graph encoding

**Trees** are constituency-style graphs built from the derivation:

- surface tokens are leaf nodes with a `form` feature
- lexical entries have `lexid`, `lextype` and `form` features
- internal nodes carry the rule name in a `cat` feature
  (`rule` is a reserved word in grew requests)
- parent→child edges are labelled with the daughter position
  (`1`, `2`, ...)
- every node — tokens, lexical entries, and rules alike — carries an
  explicit linear position (grew's `order` field), assigned in
  postorder: a node is placed right after its own rightmost
  descendant. Grew reads the index of a node in `order` back as its
  `position`, which is what `grew-match`'s dependency-style renderer
  (`dep2pict`, which has no native constituency-tree layout) uses to
  place nodes and draw arcs — postorder happens to give exactly the
  order needed for sibling and ancestor arcs to nest without crossing,
  so the picture reads far closer to a real tree than the arbitrary
  placement grew otherwise gives nodes it has no position for
  (see the "Constituency trees in a dependency-only renderer"
  discussion below for why postorder in particular).
- because constituent nodes are now interleaved between words in
  `order`, grew's own precedence relation between order-adjacent nodes
  no longer means word-to-word adjacency; an explicit `adjacent=y`
  edge is added between every literally-consecutive pair of surface
  tokens instead, so `pattern { X -[adjacent=y]-> Y }` still finds
  immediately-adjacent word pairs (bigrams) directly

**DMRS** are dependency-style graphs:

- one node per predicate, ordered by surface position, with the raw
  `pred` string verbatim, plus `lemma`/`pos`/`sense` whenever
  pydelphin's `predicate.is_surface()` recognises the predicate's
  shape (roughly: underscore-prefixed with a POS-shaped suffix, e.g.
  `_dog_n_1` → lemma `dog`, pos `n`, sense `1`). This is a
  string-shape heuristic, trusted as the grammarian's own naming
  convention as-is: a grammar-specific abstract predicate can use the
  same shape as a genuinely word-anchored one (the ERG's `_the_q` is
  a real determiner; NorSource's `_pronoun_q`/`_def_q` are
  grammar-internal composition markers that happen to look the
  same), so a `lemma` may occasionally not mean much — but that no
  longer costs anything, because the node's displayed name in
  grew-match is always `pred` (patched in, see "Backend patches"
  below), not `lemma`; a not-very-meaningful lemma is just an extra,
  occasionally-unhelpful search key, never something competing for
  the display slot. Predicates that do not fit the shape at all —
  most abstract predicates without a `_..._pos` pattern, e.g. `pron`
  or NorSource's `_1pl-pron` — get no lemma regardless of what they
  mean; search those by `pred` instead. See the `search_lemma`
  snippet and "Regex and anchoring" below.
- other node features: `cvarsort`, the morphosemantic properties
  (`NUM`, `PERS`, `TENSE`, ...), `carg`, `cfrom`/`cto`, and
  `top`/`index` flags; characters that clash with grew syntax in
  property names are replaced by `_` (e.g. `PNG.PERNUM` becomes
  `PNG_PERNUM`)
- links become edges with two label features: `1` (the role, e.g.
  `ARG1`) and `post` (e.g. `NEQ`); undirected `/EQ` links get the
  conventional role `MOD`

### Regex and anchoring

Grew's `re"..."` requires a **full match**, not a substring search:
`pred=re"dog"` matches nothing, since no predicate is literally just
`dog`. To match a prefix (e.g. every sense of a lemma, since surface
predicates follow `_lemma_pos_sense`), anchor with a trailing `.*`:
`pred=re"_dog_.*"` finds `_dog_n_1`, `_dog_n_2`, .... To match
anywhere in the string, wrap both sides: `pred=re".*dog.*"` (broader —
on the ERG DMRS corpus this also catches predicates with "dog"
elsewhere in the name, 184 matches against 169 for the anchored
prefix form).

Every graph carries its `profile`, `sid` and `text` as metadata so
matches can be traced back to LTDB.

### Constituency trees in a dependency-only renderer

Grew-match displays every graph — DMRS *and* trees alike — with
`dep2pict`, which draws exactly one style of picture: a row of nodes
with arcs above connecting them. This is a hard limitation, not a
configuration option:

- Grew's core graph model does have a dedicated subconstituent edge
  kind, and a `phrase_structure_tree`/`of_pst` reader that loads
  bracketed treebank text into it — but there is no writer the other
  way. Nothing in grewlib or `dep2pict` ever draws a subconstituent
  edge as a branch; nothing draws multiple vertical levels at all.
- `void=y`, sometimes suggested as a way to push a node above the
  baseline, does no such thing: tracing it through grewlib's `to_dep`
  shows it only recolours a node's label red. We confirmed this live —
  editing a real exported tree, adding `void=y` to every internal
  node, recompiling, and reloading changed nothing but colour.
- The OCaml package actually doing the drawing, `dep2pictlib`, is
  described by its own metadata as, simply, "Drawing dependency tree".

So grew-match's tree corpora are always going to read as dependency
diagrams, not branching trees — but the *shape* of that diagram is
still ours to control, and a bad one is what motivated this
investigation in the first place: earlier exports left every
constituent node without a linear position, so grewlib laid them out
with its own span-blind fallback (wherever the node happened to land
while folding an unordered map — effectively arbitrary), producing
arcs that frequently crossed.

Every node in a grew graph gets its horizontal position from its index
in the `order` field (see [grew's JSON graph
format](https://grew.fr/doc/graph/)); a node absent from `order` gets
no position and falls back to that arbitrary placement. Giving every
constituent node a position fixes this, provided the positions are
assigned in the right order. Postorder — visiting all of a node's
daughters (recursively) before emitting the node's own position — is
that order: because a derivation tree's spans are contiguous (a
mother's span is exactly the union of its daughters' spans), postorder
guarantees that a node always immediately follows its own rightmost
descendant, which produces properly nested, non-crossing arcs for
constituent structure specifically:

- **Nodes sharing an identical span** (a unary chain, e.g. a lexical
  entry and the unary rule directly above it) come out **deepest
  first** — the descendant is still mid-traversal when the ancestor's
  turn to be emitted arrives.
- **A mother sharing exactly one boundary with a daughter** (the
  common case: every rule's first daughter shares its left boundary
  with the mother, and its last daughter shares the right boundary)
  always comes out **after** that daughter, since the daughter's own
  postorder-complete subtree, including the daughter itself, is
  emitted before the mother's turn.

Both properties fall out of plain postorder without ever comparing
spans explicitly — the tree structure we already have while walking
the derivation is enough.

The trade-off: grew derives its own immediate-precedence relation
(`<<`) from raw adjacency in `order`, and interleaving constituent
nodes into that same list means two adjacent *words* are usually no
longer adjacent *positions* — a rule or lexical-entry node from one
word's own postorder chain typically sits between them. Rather than
lose word-to-word immediate precedence, `deriv_to_grew` adds it back
as an explicit edge (`adjacent=y`) between every literally-consecutive
pair of surface tokens, independent of position entirely — so
`pattern { X -[adjacent=y]-> Y }` still finds bigrams directly, at the
cost of one extra edge per word pair in the exported graph.

## 2. Install grew (once)

Grew is an OCaml program, installed through [opam](https://opam.ocaml.org/).
On a fresh machine install and initialise opam first:

```bash
sudo apt install opam   # or see https://opam.ocaml.org/doc/Install.html
opam init -a
eval $(opam env)
```

then install grew (dune comes with it) and its grew-match dependencies:

```bash
opam remote add grew "https://opam.grew.fr"
opam update
opam install dune dream dep2pictlib grew
```

`run.sh` and `scripts/setup-grew-match.sh` find the opam switch via
`opam` on PATH (or `~/.local/bin/opam`), so no further setup is needed;
"grew/dune not found" means this step has not been done yet.

## 3. Run a local grew-match

The easiest way is the development runner, which starts grew-match
alongside LTDB, compiles the corpora, and links the two:

```bash
./run.sh --grew-match "web/db/ERG_(2020)-grew/corpora.json"
```

(Without the argument, every `web/db/*-grew` export is served — the
corpora of all exported grammars appear in one dropdown.  Restart to
pick up newly exported grammars.)

To run grew-match by hand instead:

```bash
git clone https://github.com/grew-nlp/grew_match_quick
git clone https://github.com/grew-nlp/grew_match.git \
    grew_match_quick/local_files/grew_match
mkdir -p grew_match_quick/local_files/grew_match/instances
python3 grew_match_quick/grew_match_quick.py "ERG_(2020)-grew/corpora.json"
```

(The `mkdir` works around the script assuming an `instances/`
directory that newer `grew_match` checkouts no longer ship.  Clone
`grew_match` *before* creating it: if the directory already exists,
the script takes it for a checkout and never fetches the frontend —
and inside another git repository, its `git pull` there silently hits
the enclosing repo instead of failing.)

JSON corpora are not compiled automatically on startup, so the first
time (and after re-exporting) compile them and make the backend
re-read the corpus descriptions — otherwise the web page shows
"Corpus not compiled":

```bash
grew compile -CORPUSBANK grew_match_quick/local_files/corpusbank
curl -X POST http://localhost:8899/reload
```

(Typing `r` at the grew_match_quick prompt also compiles, but the
upstream script only refreshes the corpus cache, not the compiled
status; our local grew_match_quick clone is patched to POST `/reload`
too, so `r` is enough there.  Reload the browser page afterwards.)

Then open <http://localhost:8000> (ports configurable with
`--frontend_port`/`--backend_port`).

To show a **Grew-match** link in the LTDB navigation bar, set the
environment variable before starting the Flask app:

```bash
export LTDB_GREW_MATCH_URL=http://localhost:8000
```

Without the web UI, you can also search from the command line:

```bash
echo 'pattern { N [pred=re"_dog_.*"] }' > q.req
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
pattern { X -[adjacent=y]-> Y; Y [form="the"] } % word immediately
                                                 % followed by "the"
pattern {                                       % "all" adjacent to "the",
  Pre -[1]-> X; GP -[1]-> Pre;                  % but "the" is not the
  X [form="all"]; X -[adjacent=y]-> Y;          % complement of "all"
  Y [form="the"]
} without { GP [cat="hd-cmp_u_c"] }
```

On the DMRS corpus:

```
pattern { N [pred=re"_dog_.*"] }               % a predicate by word
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
button opens the image on its own; the link button opens the
sentence in LTDB).

The web interface only exports matches as TSV or CoNLL, but the
corpora themselves are JSON: a match's `sent_id` (e.g. `ace/100`)
identifies one graph inside its profile's file in the export
directory — grep the file for that `sent_id` to pull the graph out
directly (files are grouped by profile, not one per sentence; see
"Export the corpora" above). For a JSON list of all matches (sentence
ids plus the matched nodes/edges), use the command line:

```bash
grew grep -request q.req -i OUT/<corpus> > matches.json
```

## 6. Backend patches

The grew_match_dream backend on GitHub lags behind the grew_match
frontend and needs the patches in `etc/grew_match_dream.patch`
(applied to `src/gmd_utils.ml`, then `dune build` and restart;
`run.sh --grew-match` clones and patches it automatically):

- `save_dep`/`save_dot` must encode each item's `meta` as a list of
  `{"key": ..., "value": ..., "sub": {}}` objects, not a plain map —
  otherwise the frontend's result list silently fails to render
  (a `meta.find is not a function` error in the browser console);
- `save_dep` must pass the `url` and `code` metas through (only
  `save_dot` does), or the link button never appears for
  dependency-rendered corpora;
- relative `url` metas are expanded with `$LTDB_BASE_URL` at serve
  time (see section 1);
- `save_dep` must call `Graph.to_dep` with `~main_feat:"pred"`, so
  DMRS nodes are drawn labelled with their `pred` feature rather than
  grewlib's hardcoded default priority (`form`, then `lemma`, then
  `gpred`, ...). Without this, a node with both `lemma` and `pred` set
  displays its `lemma` — fine for a genuinely word-anchored predicate,
  misleading for a grammar-internal one reusing the same surface shape
  (see "Graph encoding" above). `main_feat` only picks which *existing*
  feature is shown as the node's name; it does not add or hide data, so
  `lemma`/`pos`/`sense` stay searchable either way.

The first three are worth filing upstream at
<https://github.com/grew-nlp/grew_match_dream>.

Corpus ids match the `.db` stem exactly (e.g. `ERG_2025_trees`), not
`SHORT_GRAMMAR_NAME_Version` — that pair duplicates the grammar name
(the ERG's `Version` metadatum is itself `"ERG (2025)"`, so the old
scheme sanitized to `ERG_ERG_2025_trees`). Each corpus also carries a
`grammar_url` meta (relative, like the graph-level `url` metas —
`get_corpora_desc` expands both the same way with `$LTDB_BASE_URL`)
pointing at that grammar's LTDB page.

The frontend (`etc/grew_match.patch`, applied to `grew_match` the same
way as the backend patch above) uses `grammar_url` for two links: an
external-link icon next to each corpus in the dropdown, and a
persistent "*corpus* grammar page" link in the navbar for whichever
corpus is currently active. `run.sh` additionally rewrites the
frontend's generated `config.json`/`instances/gmq_instance.json` after
each start (the same way it already points `snippets_url` at
`etc/grew_snippets/`) to set the corpus-dropdown label to "DELPH-IN
Grammary Corpora" and point `top_project` (grew_match's own generic
branding slot) at the DELPH-IN wiki — neither needs a frontend patch,
since both are read from JSON grew_match_quick.py itself writes.

### Query snippets

The snippet pane on the right of the grew-match UI is populated from
`etc/grew_snippets/` (served by the frontend; `run.sh` points
`config.json`'s `snippets_url` there at each start).  It has tabs for
the DMRS corpora (predicate search by `pred`, by exact `lemma`, or by
regex; a regex-escaping example (`ad+hoc`); a particle verb whose
particle lands in the sense slot (`knock_v_up`); `ARG1` links,
reflexive-like configurations, quantifier restrictions, `post=EQ`
modification), the derivation-tree corpora (`cat`, `lextype`, `lexid`,
`form`, `n`-th daughter, adjacency combined with a `without` clause
excluding a specific construction), and graph metadata (sentence text,
treebank profile). Clicking a snippet loads the query into the request
box; edit the quoted values to taste.

`_default.html` also carries a small inline `<script>` that keeps the
DMRS/Trees tab and the active corpus in sync, in both directions, with
no frontend patch: it re-runs on every corpus change (the pane is
re-fetched and re-injected each time — see `update_corpus()` in
grew_match's `js/main.js`), so it activates whichever tab matches the
`_dmrs`/`_trees` suffix of `current_corpus_id` at that moment; and it
adds a second click handler on every `.inter` snippet link that, for a
snippet of the *other* kind, switches to the sibling corpus from the
same grammar if one exists, or otherwise shows a warning. It reaches
the frontend's Vue instance as the bare identifier `app`, not
`window.app` — `js/main.js` declares it with a top-level `let`, which
(unlike `var`) does not become a `window` property, though it is still
visible from any other plain `<script>` sharing the page (confirmed
live: `typeof window.app` is `"object"` — some unrelated browser
global — while `app` is the real Vue instance).
