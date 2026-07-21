###
### Export an LTDB grammar database to Grew JSON corpora
### (https://grew.fr/doc/json/) so the trees and DMRS can be
### searched with grew-match (see doc/grew-match.md).
###
import argparse
import io
import logging
import multiprocessing as mp
import re
import sqlite3
import sys
from functools import lru_cache
from itertools import count
from pathlib import Path
from urllib.parse import quote

import orjson
from delphin import derivation, predicate
from delphin.codecs import simplemrs
from delphin.dmrs import from_mrs

from gold2db import cpu_jobs

log = logging.getLogger("db2grew")

# pydelphin's simplemrs encoder writes unknown spans as <-1:-1>,
# which its own decoder rejects; strip them before decoding
NULL_LNK = re.compile(r"<-1:-1>")
# its lexer also rejects unquoted surface predicates that do not fit
# the _lemma_pos(_sense) shape (e.g. INDRA's _and_coord); quote them
SURFACE_PRED = re.compile(r'(\[\s+)(_[^\s"<]+)')


def sanitize(name):
    """Return name with runs of non-word characters replaced by '_'.

    Args:
        name: Arbitrary string (grammar name, profile name, ...)

    Returns:
        A string safe to use in file and corpus names
    """
    return re.sub(r"\W+", "_", name).strip("_")


def get_meta(conn):
    """Return the meta table as a dictionary.

    Args:
        conn: Connection to an LTDB SQLite database

    Returns:
        Dictionary mapping attribute to value
    """
    c = conn.cursor()
    c.execute("SELECT att, val FROM meta")
    return dict(c.fetchall())


def get_lextypes(conn):
    """Return a mapping from lexical-entry id to its lexical type.

    Args:
        conn: Connection to an LTDB SQLite database

    Returns:
        Dictionary mapping lexid to typ
    """
    c = conn.cursor()
    c.execute("SELECT lexid, typ FROM lex")
    return dict(c.fetchall())


def iter_gold(conn, profiles=None):
    """Yield gold rows: (profile, sid, sent, deriv, mrs).

    The deriv column holds the raw UDF derivation string and the mrs
    column the SimpleMRS string, as stored by gold2db.py.

    Args:
        conn: Connection to an LTDB SQLite database
        profiles: Optional list of profile names to restrict to

    Yields:
        One tuple per sentence, ordered by profile then sid
    """
    c = conn.cursor()
    query = "SELECT profile, sid, sent, deriv, mrs FROM gold"
    params = []
    if profiles:
        query += f" WHERE profile IN ({','.join(['?'] * len(profiles))})"
        params = list(profiles)
    query += " ORDER BY profile, sid"
    yield from c.execute(query, params)


def _convert_deriv_node(node, graph, lextypes, ids, tids):
    """Recursively add a derivation node (and its daughters) to graph.

    Every node -- terminal, preterminal, and internal -- is appended to
    graph["order"] in postorder (after all of its daughters), which grew
    reads back as each node's linear position (see grewlib G_graph.of_json:
    position = index in the "order" list; a node absent from "order" is
    laid out by grew's own, span-blind heuristic instead).  Postorder
    places a node immediately after its rightmost descendant, which for a
    span-contiguous derivation tree happens to satisfy exactly the
    ordering grew-match needs to draw nested, non-crossing arcs: nodes
    sharing an entire span (a unary chain) come out deepest-first, and a
    mother sharing just one boundary with a daughter (the common case --
    every rule's first and last daughter share a boundary with it) always
    comes out after that daughter.  The trade-off is that adjacent words
    are no longer adjacent positions once constituent nodes are
    interleaved between them, so a `precedes` test between two words no
    longer means string-adjacency; searching by tree configuration
    (dominance, sisterhood, span containment) is what this buys instead.

    Args:
        node: a pydelphin UDFNode
        graph: the grew graph dict being built (nodes/edges/order)
        lextypes: mapping from lexid to lexical type
        ids: counter assigning node ids in pre-order
             (derivation ids cannot be used: ACE leaves them all 0)
        tids: counter assigning surface-token ids, independent of ids so
              that t0, t1, ... stay sequential regardless of how many
              constituent nodes are interleaved into "order"

    Returns:
        The grew node id assigned to node
    """
    nid = f"n{next(ids)}"
    daughters = node.daughters or []
    if daughters and isinstance(daughters[0], derivation.UDFTerminal):
        # preterminal: a lexical entry over surface token(s)
        feats = {"lexid": node.entity}
        if node.entity in lextypes:
            feats["lextype"] = lextypes[node.entity]
        feats["form"] = " ".join(t.form for t in daughters)
        graph["nodes"][nid] = feats
        for i, terminal in enumerate(daughters, 1):
            tid = f"t{next(tids)}"
            graph["nodes"][tid] = {"form": terminal.form}
            graph["order"].append(tid)
            graph["edges"].append({"src": nid, "label": str(i), "tar": tid})
    else:
        # 'cat' follows grew constituency convention
        # ('rule' is a reserved word in grew requests)
        graph["nodes"][nid] = {"cat": node.entity}
        for i, daughter in enumerate(daughters, 1):
            did = _convert_deriv_node(daughter, graph, lextypes, ids, tids)
            graph["edges"].append({"src": nid, "label": str(i), "tar": did})
    graph["order"].append(nid)
    return nid


def deriv_to_grew(deriv_str, lextypes, meta):
    """Convert a UDF derivation string to a constituency-style grew graph.

    Every node -- surface tokens (t0, t1, ...), lexical entries, and
    rules -- is ordered, in postorder (see _convert_deriv_node); parent
    -> child edges are labelled with the daughter position ("1", "2", ...).

    Grew derives its own immediate-precedence relation from raw
    adjacency in the "order" list, which now interleaves constituent
    nodes between words, so it no longer means word-to-word adjacency.
    An explicit `adjacent=y` edge between literally-consecutive surface
    tokens is added to keep that queryable regardless -- see
    doc/grew-match.md.

    Args:
        deriv_str: raw UDF derivation from gold.deriv
        lextypes: mapping from lexid to lexical type
        meta: graph-level metadata (sid, profile, text)

    Returns:
        A grew graph dictionary, or None if conversion fails
    """
    if not deriv_str:
        return None
    try:
        root = derivation.from_string(deriv_str)
    except Exception as err:
        log.error(
            "derivation %s:%s unreadable: %s",
            meta["profile"],
            meta["sid"],
            err,
        )
        return None
    graph = {"meta": meta, "nodes": {}, "edges": [], "order": []}
    _convert_deriv_node(root, graph, lextypes, count(), count())
    terminal_ids = [nid for nid in graph["order"] if nid.startswith("t")]
    for src, tar in zip(terminal_ids, terminal_ids[1:]):
        graph["edges"].append({"src": src, "label": {"adjacent": "y"}, "tar": tar})
    return graph


@lru_cache(maxsize=None)
def _predicate_parts(pred):
    """Return (lemma, pos, sense) for a surface predicate, else None.

    predicate.is_surface()/predicate.split() each reparse the string;
    caching by predicate is worthwhile because the same handful of
    predicates (e.g. "_the_q") recur constantly across a treebank.
    """
    if not predicate.is_surface(pred):
        return None
    return predicate.split(pred)


def dmrs_to_grew(mrs_str, meta):
    """Convert a SimpleMRS string to a dependency-style grew DMRS graph.

    Predicate nodes are ordered by surface position (cfrom) so that
    grew-match renders the links as dependency arcs.  Edge labels are
    feature structures {"1": role, "post": post}; undirected /EQ links
    (no role) get the conventional role "MOD".

    Every node keeps the raw `pred` string verbatim.  Predicates that
    pydelphin's predicate.is_surface() judges "surface" additionally
    get lemma/pos/sense via predicate.split(), trusted as-is with no
    part-of-speech exceptions -- see doc/grew-match.md ("Graph
    encoding" and "6. Backend patches") for why a not-always-meaningful
    lemma is safe to keep.

    Args:
        mrs_str: raw SimpleMRS from gold.mrs
        meta: graph-level metadata (sid, profile, text)

    Returns:
        A grew graph dictionary, or None if conversion fails
    """
    if not mrs_str:
        return None
    cleaned = SURFACE_PRED.sub(r'\1"\2"', NULL_LNK.sub("", mrs_str))
    try:
        d = from_mrs(simplemrs.decode(cleaned))
    except Exception as err:
        log.error(
            "DMRS %s:%s unconvertible: %s",
            meta["profile"],
            meta["sid"],
            err,
        )
        return None
    nodes = {}
    for node in d.nodes:
        feats = {"pred": node.predicate}
        parts = _predicate_parts(node.predicate)
        if parts:
            lemma, pos, sense = parts
            for att, val in (("lemma", lemma), ("pos", pos), ("sense", sense)):
                if val:
                    feats[att] = val
        if node.type:
            feats["cvarsort"] = node.type
        # grammars may use property names like PNG.PERNUM or COG-ST,
        # but '.' and '-' clash with grew request syntax
        feats.update((sanitize(att), val) for att, val in node.properties.items())
        if node.carg:
            feats["carg"] = node.carg
        if node.cfrom is not None and node.cfrom >= 0:
            feats["cfrom"] = str(node.cfrom)
            feats["cto"] = str(node.cto)
        if node.id == d.top:
            feats["top"] = "yes"
        if node.id == d.index:
            feats["index"] = "yes"
        nodes[f"n{node.id}"] = feats
    linked = [n for n in d.nodes if n.cfrom is not None and n.cfrom >= 0]
    linked.sort(key=lambda n: (n.cfrom, n.cto, n.id))
    order = [f"n{n.id}" for n in linked]
    edges = [
        {
            "src": f"n{link.start}",
            "label": {"1": link.role or "MOD", "post": link.post},
            "tar": f"n{link.end}",
        }
        for link in d.links
    ]
    return {"meta": meta, "nodes": nodes, "edges": edges, "order": order}


def write_graph(directory, fname, graph_or_graphs):
    """Write one grew graph, or a list of them, as JSON under directory.

    Grew's JSON corpus reader accepts either shape per file: a single
    graph object, or a list of graph objects (each identified by its
    own "sent_id" meta, not by the file it lives in -- see
    doc/grew-match.md).
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / fname).write_bytes(
        orjson.dumps(graph_or_graphs, option=orjson.OPT_INDENT_2)
    )


# Set once per worker process by _init_worker(), instead of re-pickling
# lextypes and the export settings on every profile.
_worker_ctx = {}


def _init_worker(lextypes, do_trees, do_dmrs, trees_dir, dmrs_dir, url_base, db_name):
    # A per-worker log buffer: conversion failures go through the
    # module logger (see deriv_to_grew/dmrs_to_grew), and each worker
    # process needs its own handler since a file handle can't be
    # shared across processes. _export_profile() drains it after each
    # profile so lines are attributed correctly. Drop any handler this
    # function attached in an earlier call in the same process (e.g. a
    # prior export() call, or state a forked worker inherited), so
    # handlers don't accumulate.
    for handler in list(log.handlers):
        log.removeHandler(handler)
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    _worker_ctx.update(
        lextypes=lextypes,
        do_trees=do_trees,
        do_dmrs=do_dmrs,
        trees_dir=trees_dir,
        dmrs_dir=dmrs_dir,
        url_base=url_base,
        db_name=db_name,
        log_buffer=buffer,
    )


def _export_profile(item):
    """Convert one profile's gold rows to a tree/DMRS graph file each.

    Runs either directly (jobs=1) or in a worker process set up by
    _init_worker(); returns ((tree_fname, n_trees), (dmrs_fname,
    n_dmrs), log_lines) -- a filename is None if that graph type was
    skipped, not requested, or every row in the profile failed to
    convert (n_* is then 0).
    """
    profile, rows = item
    ctx = _worker_ctx
    buffer = ctx["log_buffer"]
    buffer.seek(0)
    buffer.truncate(0)

    tree_graphs = []
    dmrs_graphs = []
    for sid, sent, deriv_str, mrs_str in rows:
        meta = {
            "sent_id": f"{profile}/{sid}",
            "sid": str(sid),
            "profile": profile,
            "text": sent or "",
        }
        meta["url"] = (
            f"{ctx['url_base']}/sent/{quote(profile, safe='')}/{sid}"
            f"?grm={quote(ctx['db_name'], safe='')}"
        )
        if ctx["do_trees"]:
            graph = deriv_to_grew(deriv_str, ctx["lextypes"], meta)
            if graph:
                tree_graphs.append(graph)
        if ctx["do_dmrs"]:
            graph = dmrs_to_grew(mrs_str, meta)
            if graph:
                dmrs_graphs.append(graph)

    fname = f"{sanitize(profile)}.json"
    tree_fname = dmrs_fname = None
    if tree_graphs:
        write_graph(ctx["trees_dir"], fname, tree_graphs)
        tree_fname = fname
    if dmrs_graphs:
        write_graph(ctx["dmrs_dir"], fname, dmrs_graphs)
        dmrs_fname = fname

    return (
        (tree_fname, len(tree_graphs)),
        (dmrs_fname, len(dmrs_graphs)),
        buffer.getvalue().splitlines(keepends=True),
    )


def export(conn, out_dir, grm, args):
    """Export the gold table to grew corpora under out_dir.

    Profiles are independent (one profile -> one tree file and one
    DMRS file, each a JSON list of that profile's graphs), so with
    args.jobs > 1 they are converted by a pool of worker processes
    instead of one at a time; jobs=1 (the default) stays a plain loop.
    Conversion failures logged by deriv_to_grew/dmrs_to_grew are
    collected from every profile and written to
    "<db-stem>-grew.log" next to the database.

    Args:
        conn: Connection to an LTDB SQLite database
        out_dir: Output directory (created if needed)
        grm: Sanitized grammar name used in corpus ids
        args: Parsed command-line arguments

    Returns:
        The list of corpora written (as corpora.json dictionaries)
    """
    do_trees = not args.dmrs_only
    do_dmrs = not args.trees_only
    # url metas are relative by default: the serving backend prepends
    # the LTDB base URL (LTDB_BASE_URL), so exports survive address
    # changes; --ltdb-url bakes an absolute base in instead
    url_base = args.ltdb_url.rstrip("/") if args.ltdb_url else ""
    lextypes = get_lextypes(conn) if do_trees else {}
    trees_dir = out_dir / f"{grm}_trees"
    dmrs_dir = out_dir / f"{grm}_dmrs"
    ctx_args = (lextypes, do_trees, do_dmrs, trees_dir, dmrs_dir, url_base, args.db.name)

    profiles = {}
    for profile, sid, sent, deriv_str, mrs_str in iter_gold(conn, args.profiles):
        profiles.setdefault(profile, []).append((sid, sent, deriv_str, mrs_str))
    items = list(profiles.items())

    n_workers = min(getattr(args, "jobs", 1) or 1, len(items)) if items else 1
    if n_workers > 1:
        with mp.Pool(n_workers, initializer=_init_worker, initargs=ctx_args) as pool:
            results = pool.map(_export_profile, items)
    else:
        _init_worker(*ctx_args)
        results = [_export_profile(item) for item in items]

    tree_files = []
    dmrs_files = []
    n_trees = n_dmrs = 0
    log_lines = []
    for (tree_fname, tree_count), (dmrs_fname, dmrs_count), lines in results:
        if tree_fname:
            tree_files.append(tree_fname)
            n_trees += tree_count
        if dmrs_fname:
            dmrs_files.append(dmrs_fname)
            n_dmrs += dmrs_count
        log_lines.extend(lines)

    if log_lines:
        log_path = args.db.parent / f"{args.db.stem}-grew.log"
        log_path.write_text("".join(log_lines))

    corpora = []
    for cid, directory, files, n_graphs in (
        (f"{grm}_trees", trees_dir, tree_files, n_trees),
        (f"{grm}_dmrs", dmrs_dir, dmrs_files, n_dmrs),
    ):
        if files:
            corpora.append(
                {
                    "id": cid,
                    # kind tells grew to read the files as grew JSON
                    # graphs (the default reader is CoNLL)
                    "kind": "json",
                    "directory": str(directory.resolve()),
                    "files": sorted(files),
                    "n_graphs": n_graphs,
                }
            )
    return corpora


def main(argv=None):
    """Export an LTDB database to grew JSON corpora (command line)."""
    parser = argparse.ArgumentParser(
        prog="db2grew",
        description="Export LTDB trees and DMRS as grew JSON corpora "
        "searchable with grew-match (see doc/grew-match.md)",
    )
    parser.add_argument("--outdir", type=Path, help="Output directory")
    parser.add_argument(
        "--profiles",
        action="append",
        help="Only export this profile (repeat the option for several)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--trees-only", action="store_true", help="Only export derivation trees"
    )
    group.add_argument("--dmrs-only", action="store_true", help="Only export DMRS")
    parser.add_argument(
        "--ltdb-url",
        help="Bake this absolute LTDB base URL into the exported link "
        "metas; by default links are relative and the grew-match "
        "backend fills in the base from $LTDB_BASE_URL at serve time",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="Parallel worker processes for graph conversion; "
        "0 = auto from CPUs (default: 1)",
    )
    parser.add_argument("db", type=Path, help="LTDB SQLite database")
    args = parser.parse_args(argv)
    args.jobs = args.jobs or cpu_jobs()

    logging.basicConfig(level=logging.INFO)
    if not args.db.is_file():
        sys.exit(f"No database at {args.db}")
    out_dir = args.outdir or args.db.parent / f"{args.db.stem}-grew"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True)
    md = get_meta(conn)
    grm = sanitize(
        f"{md.get('SHORT_GRAMMAR_NAME', '')}_{md.get('Version', '')}"
    ) or sanitize(args.db.stem)
    corpora = export(conn, out_dir, grm, args)
    conn.close()

    if not corpora:
        sys.exit(f"No usable gold trees or DMRS found in {args.db}")
    corpora_path = out_dir / "corpora.json"
    corpora_path.write_bytes(orjson.dumps(corpora, option=orjson.OPT_INDENT_2))
    for corpus in corpora:
        print(
            f"{corpus['id']}: {corpus['n_graphs']} graphs"
            f" in {len(corpus['files'])} files"
        )
    print(f"Wrote {corpora_path}")
    print("Search them with: grew_match_quick.py", corpora_path)


if __name__ == "__main__":
    main()
