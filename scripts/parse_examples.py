"""
parse_examples.py — Parse TDL docstring examples through ACE.

For each typed example tag in a grammar's TDL docstrings:
  <ex>  : type must appear in at least one parse-tree derivation
  <nex> : sentence should not parse; type must not appear in any tree
  <mex> : same check as <ex> (grammatical for the grammar via a mal-rule)

Usage:
    python parse_examples.py <ace-config> <grammar.dat> <output-dir>
        [--ace-bin PATH] [--no-profile]
"""
import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from delphin import ace, itsdb
from delphin import tsdb as _tsdb

sys.path.insert(0, str(Path(__file__).parent))
from grm2db import find_ace
from tdl2db import read_cfg, read_grm

_log = logging.getLogger(__name__)

# ── Standard itsdb schema ─────────────────────────────────────────────────────

_SCHEMA = """\
item:
  i-id :integer :key
  i-origin :string
  i-register :string
  i-format :string
  i-difficulty :integer
  i-category :string
  i-input :string
  i-tokens :string
  i-gloss :string
  i-translation :string
  i-wf :integer
  i-length :integer
  i-comment :string
  i-author :string
  i-date :date

run:
  run-id :integer :key
  run-comment :string
  platform :string
  protocol :integer
  tsdb :string
  application :string
  environment :string
  grammar :string
  avms :integer
  sorts :integer
  templates :integer
  lexicon :integer
  lrules :integer
  rules :integer
  user :string
  host :string
  os :string
  start :date
  end :date
  items :integer
  status :string

parse:
  parse-id :integer :key
  run-id :integer :key
  i-id :integer :key
  ninputs :integer
  p-input :string
  ntokens :integer
  p-tokens :string
  readings :integer
  first :integer
  total :integer
  tcpu :integer
  tgc :integer
  treal :integer
  words :integer
  l-stasks :integer
  p-ctasks :integer
  p-ftasks :integer
  p-etasks :integer
  p-stasks :integer
  aedges :integer
  pedges :integer
  raedges :integer
  rpedges :integer
  tedges :integer
  eedges :integer
  ledges :integer
  sedges :integer
  redges :integer
  unifications :integer
  copies :integer
  conses :integer
  symbols :integer
  others :integer
  gcs :integer
  i-load :integer
  a-load :integer
  date :date
  error :string
  comment :string

result:
  parse-id :integer :key
  result-id :integer
  time :integer
  r-ctasks :integer
  r-ftasks :integer
  r-etasks :integer
  r-stasks :integer
  size :integer
  r-aedges :integer
  r-pedges :integer
  derivation :string
  surface :string
  tree :string
  mrs :string
  flags :string

rule:
  parse-id :integer :key
  rule :string
  filtered :integer
  executed :integer
  successes :integer
  actives :integer
  passives :integer

output:
  i-id :integer :key
  o-application :string
  o-grammar :string
  o-ignore :string
  o-wf :integer
  o-gc :integer
  o-derivation :string
  o-surface :string
  o-tree :string
  o-mrs :string
  o-edges :integer
  o-user :string
  o-date :date

edge:
  e-id :integer :key
  parse-id :integer :key
  e-label :string
  e-type :integer
  e-status :integer
  e-start :integer
  e-end :integer
  e-score :string
  e-daughters :string
  e-parents :string
  e-alternates :string

tree:
  parse-id :integer :key
  t-version :integer
  t-active :integer :key
  t-confidence :integer
  t-author :string
  t-start :date
  t-end :date
  t-comment :string

decision:
  parse-id :integer :key
  t-version :integer
  d-state :integer
  d-type :integer
  d-key :string
  d-value :string
  d-start :integer
  d-end :integer
  d-date :date

preference:
  parse-id :integer :key
  t-version :integer
  result-id :integer

update:
  parse-id :integer :key
  t-version :integer
  u-matches :integer
  u-mismatches :integer
  u-new :integer
  u-gin :integer
  u-gout :integer
  u-pin :integer
  u-pout :integer
  u-in :integer
  u-out :integer

fold:
  f-id :integer :key
  f-train :integer
  f-trains :string
  f-test :integer
  f-tests :string
  f-events :integer
  f-features :integer
  f-environment :string
  f-iterations :integer
  f-etime :integer
  f-estimation :string
  f-accuracy :string
  f-extras :string
  f-user :string
  f-host :string
  f-start :date
  f-end :date
  f-comment :string

score:
  parse-id :integer :key
  result-id :integer
  score-start :integer
  score-end :integer
  score-id :integer
  learner :string
  rank :integer
  score :string
"""

# ── Data types ────────────────────────────────────────────────────────────────


class Example(NamedTuple):
    """A single example extracted from a TDL docstring."""

    i_id: int
    text: str
    typ: str
    wf: int
    kind: str  # 'ex' | 'nex' | 'mex'


class Verdict(NamedTuple):
    """The parse outcome for one example."""

    example: Example
    n_parses: int
    type_found: bool


# ── Example extraction ────────────────────────────────────────────────────────

_TAG_MAP: dict[str, tuple[str, int, int]] = {
    "<ex>":  ("ex",  1, 4),
    "<nex>": ("nex", 0, 5),
    "<mex>": ("mex", 1, 5),
}


def _parse_doc(typ: str, docstring: str) -> list[tuple[str, str, int, str]]:
    """Extract (text, typ, wf, kind) tuples from a single TDL docstring."""
    out = []
    for line in docstring.splitlines():
        line = line.strip()
        for tag, (kind, wf, strip_len) in _TAG_MAP.items():
            if line.startswith(tag):
                text = line[strip_len:].strip()
                if text:
                    out.append((text, typ, wf, kind))
                break
    return out


def _build_lex_ids_for_type(
    les: dict, hierarchy: list[tuple[str, str]]
) -> dict[str, set[str]]:
    """
    Map every type to the set of lex-entry ids that inherit from it.

    Uses a BFS upward through the type hierarchy so that lex entries reached
    via multi-level inheritance are still attributed to their ancestor types.
    """
    parents_of: dict[str, set[str]] = defaultdict(set)
    for child, parent in hierarchy:
        parents_of[child].add(parent)

    lex_ids_for_type: dict[str, set[str]] = defaultdict(set)
    for lexid in les:
        visited: set[str] = set()
        queue = [lexid]
        while queue:
            t = queue.pop()
            if t in visited:
                continue
            visited.add(t)
            lex_ids_for_type[t].add(lexid)
            queue.extend(parents_of.get(t, set()))
    return dict(lex_ids_for_type)


def extract_examples(
    cfg: dict,
    log,
) -> tuple[list[Example], dict[str, list[str]], dict[str, set[str]]]:
    """
    Read TDL files and return all examples plus type metadata.

    Args:
        cfg: grammar config dict from read_cfg()
        log: writable log stream

    Returns:
        (examples, types, lex_ids_for_type) where:
          examples        — ordered list of Example objects
          types           — maps type identifier → list of TDL environment statuses
          lex_ids_for_type — maps type → all lex-entry ids that inherit from it
                             (transitively, for detecting lex-type usage in trees)
    """
    tdls, types, hierarchy, les = read_grm(cfg, log)

    lex_ids_for_type = _build_lex_ids_for_type(les, hierarchy)

    examples: list[Example] = []
    seen: set[tuple[str, str, str]] = set()
    i_id = 0
    for typ, _src, _line, _kind, _tdl, docstring in tdls:
        if not docstring:
            continue
        for text, t, wf, kind in _parse_doc(typ, docstring):
            key = (text, t, kind)
            if key in seen:
                continue
            seen.add(key)
            i_id += 1
            examples.append(Example(i_id, text, t, wf, kind))

    return examples, dict(types), lex_ids_for_type


# ── Type-in-derivation check ─────────────────────────────────────────────────


def _entities(deriv) -> tuple[set[str], set[str], set[str]]:
    """Return (internal entities, preterminal entities, node types).

    Node types are the ``@type`` annotations ACE adds under ``--udx=all``:
    the lexical type of each preterminal and the phrase type of each
    internal node.
    """
    internals = list(deriv.internals())
    preterminals = list(deriv.preterminals())
    node_types = {
        t for n in internals + preterminals if (t := getattr(n, "type", None))
    }
    return (
        {n.entity for n in internals},
        {n.entity for n in preterminals},
        node_types,
    )


def type_in_results(
    typ: str,
    type_statuses: list[str],
    results: list,
    lex_ids_for_type: dict[str, set[str]],
) -> bool:
    """
    Return True if *typ* appears in any parse result's derivation.

    Three checks are tried for each derivation and any is sufficient:

    1. Direct entity match — *typ* appears as an entity name in an internal
       or preterminal node.  This covers rules and lexical rules.
    2. Node-type match — *typ* is the ``@type`` annotation of a node
       (``--udx=all``): the lexical type of a lexeme or the phrase type
       of a rule.
    3. Lex-entry descendant match — a preterminal entity is a lex-entry id
       that inherits from *typ* (via *lex_ids_for_type*).  This covers
       supertypes of the annotated lexical type.

    ``type_statuses`` is retained for API compatibility but is no longer used
    to distinguish rule vs. lex-type; the presence of lex-entry descendants
    in *lex_ids_for_type* drives that decision instead.
    """
    lex_ids = lex_ids_for_type.get(typ, set())

    for result in results:
        try:
            deriv = result.derivation()
        except Exception:
            continue
        if deriv is None:
            continue
        internals, preterminals, node_types = _entities(deriv)
        if typ in internals or typ in preterminals or typ in node_types:
            return True
        if lex_ids and lex_ids & preterminals:
            return True
    return False


# ── Verdict label ─────────────────────────────────────────────────────────────


def verdict_label(v: Verdict) -> str:
    """Return a short PASS/FAIL string for a verdict.

    <ex>/<mex>: PASS if the type appears in at least one parse tree.
    <nex>:      PASS if the type does NOT appear in any parse tree
                (whether the sentence parsed or not is informational only).
    """
    kind = v.example.kind
    if kind in ("ex", "mex"):
        if v.type_found:
            return "PASS"
        return "FAIL-no-parse" if v.n_parses == 0 else "FAIL-type-absent"
    # nex: only failure is the prohibited type appearing in a parse tree
    return "FAIL-type-in-tree" if v.type_found else "PASS"


# ── itsdb profile ─────────────────────────────────────────────────────────────


def make_test_suite(
    output_dir: Path, examples: list[Example]
) -> itsdb.TestSuite:
    """
    Create an itsdb TestSuite at *output_dir* and populate the item table.

    Args:
        output_dir: directory for the profile (created if absent)
        examples:   list of Example objects

    Returns:
        A committed TestSuite with items written to disk.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rel_path = output_dir / "relations"
    if not rel_path.exists():
        rel_path.write_text(_SCHEMA)

    ts = itsdb.TestSuite(output_dir)
    fields = ts.schema["item"]
    for ex in examples:
        record = _tsdb.make_record(
            {
                "i-id": ex.i_id,
                "i-input": ex.text,
                "i-wf": ex.wf,
                "i-comment": f"type={ex.typ} kind={ex.kind}",
            },
            fields,
        )
        ts["item"].append(record)
    ts.commit()
    return ts


# ── Parsing ───────────────────────────────────────────────────────────────────


def run_examples(
    examples: list[Example],
    dat: str,
    ace_bin: str,
    types: dict[str, list[str]],
    lex_ids_for_type: dict[str, set[str]],
    ts: itsdb.TestSuite | None = None,
) -> list[Verdict]:
    """
    Parse every example with ACE and return verdicts.

    Root-condition types (TDL status 'root') are tested in separate ACE
    batches using ``-r <root_type>``, so that ACE is forced to apply that
    specific root and the type therefore appears in the derivation when it
    succeeds.  All other types are parsed in a single ACE batch using
    ``--rooted-derivations``.

    If *ts* is provided, parse and result tables are written to it.

    Args:
        examples:         list of Example objects (already in *ts* if provided)
        dat:              path to compiled ACE grammar (.dat)
        ace_bin:          path to ACE binary
        types:            maps type name → list of TDL environment statuses
        lex_ids_for_type: maps type → all lex-entry ids that inherit from it
        ts:               optional TestSuite to write parse results into

    Returns:
        list of Verdict objects in the same order as *examples*.
    """
    verdicts_by_id: dict[int, Verdict] = {}
    fm = itsdb.FieldMapper() if ts is not None else None
    # --udx=all annotates nodes with their types so lex-types and phrase
    # types can be matched directly in the derivation
    base_cmdargs = ["--rooted-derivations", "--udx=all"]

    # Root-condition types need a separate ACE invocation with -r <root>
    # so that ACE is forced to use that root; without it root_gen, root_frag
    # etc. are never picked when a more-preferred root (root_strict) applies.
    normal: list[Example] = []
    root_groups: dict[str, list[Example]] = {}
    for ex in examples:
        if "root" in types.get(ex.typ, []):
            root_groups.setdefault(ex.typ, []).append(ex)
        else:
            normal.append(ex)

    def _run_batch(exs: list[Example], cmdargs: list[str]) -> None:
        # Pass a copy: ACEParser mutates its cmdargs list in-place (appending
        # tsdb flags), which would corrupt the caller's list on reuse.
        with ace.ACEParser(dat, executable=ace_bin, cmdargs=list(cmdargs)) as parser:
            for ex in exs:
                response = parser.process_item(ex.text, keys={"i-id": ex.i_id})
                results = response.results()
                found = type_in_results(
                    ex.typ, types.get(ex.typ, ["type"]), results, lex_ids_for_type
                )
                verdicts_by_id[ex.i_id] = Verdict(ex, len(results), found)
                if fm is not None:
                    for tablename, data in fm.map(response):
                        ts[tablename].append(data)

    _run_batch(normal, base_cmdargs)

    for root_typ, exs in sorted(root_groups.items()):
        print(
            f"  testing root {root_typ} ({len(exs)} example(s)) …",
            file=sys.stderr,
        )
        _run_batch(exs, base_cmdargs + ["-r", root_typ])

    if fm is not None:
        for tablename, data in fm.cleanup():
            ts[tablename].append(data)
        ts.commit()

    return [verdicts_by_id[ex.i_id] for ex in examples]


# ── Report ────────────────────────────────────────────────────────────────────


def print_report(
    verdicts: list[Verdict],
    cfg: dict,
    config_path: str,
    report_path: Path | None = None,
) -> None:
    """Write a human-readable pass/fail summary to stdout and optionally a file."""
    lines: list[str] = []
    L = lines.append

    ex_mex = [v for v in verdicts if v.example.kind in ("ex", "mex")]
    nex = [v for v in verdicts if v.example.kind == "nex"]

    total = len(verdicts)
    n_ex = sum(1 for v in verdicts if v.example.kind == "ex")
    n_nex = len(nex)
    n_mex = sum(1 for v in verdicts if v.example.kind == "mex")

    ver = cfg.get("ver", "unknown")
    L(f"Grammar: {ver}  Config: {config_path}")
    L(f"Examples: {total} total  (<ex>: {n_ex}  <nex>: {n_nex}  <mex>: {n_mex})")
    L("")

    # ── <ex> / <mex> table ─────────────────────────────────────────────
    if ex_mex:
        em_pass = sum(1 for v in ex_mex if verdict_label(v) == "PASS")
        em_no_parse = sum(
            1 for v in ex_mex if verdict_label(v) == "FAIL-no-parse"
        )
        em_absent = sum(
            1 for v in ex_mex if verdict_label(v) == "FAIL-type-absent"
        )
        hdr = (
            f"{'<ex> / <mex>':<12}  {'Total':>6}  {'PASS':>6}"
            f"  {'FAIL-no-parse':>14}  {'FAIL-type-absent':>16}"
        )
        L(hdr)
        L("-" * len(hdr))
        L(
            f"{'':12}  {len(ex_mex):>6}  {em_pass:>6}"
            f"  {em_no_parse:>14}  {em_absent:>16}"
        )
        L("")

    # ── <nex> table ────────────────────────────────────────────────────
    if nex:
        nex_pass = sum(1 for v in nex if verdict_label(v) == "PASS")
        nex_parsed_ok = sum(
            1 for v in nex if verdict_label(v) == "PASS" and v.n_parses > 0
        )
        nex_in_tree = sum(
            1 for v in nex if verdict_label(v) == "FAIL-type-in-tree"
        )
        hdr2 = (
            f"{'<nex>':<12}  {'Total':>6}  {'PASS':>6}"
            f"  {'parsed-ok':>10}  {'FAIL-type-in-tree':>17}"
        )
        L(hdr2)
        L("-" * len(hdr2))
        L(
            f"{'':12}  {len(nex):>6}  {nex_pass:>6}"
            f"  {nex_parsed_ok:>10}  {nex_in_tree:>17}"
        )
        L("  (parsed-ok = sentence parsed but type correctly absent)")
        L("")

    # ── Failure detail ─────────────────────────────────────────────────
    em_failures: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for v in ex_mex:
        lbl = verdict_label(v)
        if lbl != "PASS":
            em_failures[v.example.typ][lbl] += 1

    nex_failures: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for v in nex:
        if verdict_label(v) == "FAIL-type-in-tree":
            nex_failures[v.example.typ]["FAIL-type-in-tree"] += 1

    if em_failures:
        L("Failed <ex> / <mex> types:")
        for typ, counts in sorted(em_failures.items()):
            detail = "  ".join(
                f"{lbl}: {n}" for lbl, n in sorted(counts.items())
            )
            L(f"  {typ:<40}  {detail}")
        L("")

    if nex_failures:
        L("Failed <nex> types:")
        for typ, counts in sorted(nex_failures.items()):
            detail = "  ".join(
                f"{lbl}: {n}" for lbl, n in sorted(counts.items())
            )
            L(f"  {typ:<40}  {detail}")
        L("")

    text = "\n".join(lines)
    print(text)
    if report_path is not None:
        report_path.write_text(text, encoding="utf-8")
        print(f"Report written to {report_path}", file=sys.stderr)


# ── Database output ──────────────────────────────────────────────────────────


_DOCTEST_TABLE_DDL = """\
CREATE TABLE IF NOT EXISTS doctest (
    typ     TEXT NOT NULL,
    sent    TEXT NOT NULL,
    kind    TEXT NOT NULL,
    wf      INTEGER NOT NULL,
    n_parses   INTEGER,
    type_found INTEGER,
    pass    INTEGER NOT NULL,
    verdict TEXT NOT NULL
)"""

_DOCTEST_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_doctest_typ ON doctest(typ)"
)


def write_to_db(verdicts: list[Verdict], db_path: Path) -> None:
    """
    Insert doctest results into the *doctest* table of a grammar DB.

    Creates the table if it does not yet exist (so it works against databases
    built before the table was added to tables.sql).  Clears any previous
    doctest rows so the table always reflects the most recent run.

    Args:
        verdicts:  list of Verdict objects from run_examples()
        db_path:   path to the SQLite grammar database
    """
    import sqlite3

    rows = [
        (
            v.example.typ,
            v.example.text,
            v.example.kind,
            v.example.wf,
            v.n_parses,
            int(v.type_found),
            int(verdict_label(v) == "PASS"),
            verdict_label(v),
        )
        for v in verdicts
    ]
    with sqlite3.connect(db_path) as conn:
        conn.execute(_DOCTEST_TABLE_DDL)
        conn.execute(_DOCTEST_INDEX_DDL)
        conn.execute("DELETE FROM doctest")
        conn.executemany(
            """INSERT INTO doctest
               (typ, sent, kind, wf, n_parses, type_found, pass, verdict)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    print(f"  {len(rows)} doctest rows written to {db_path}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Parse TDL docstring examples through ACE and report."
    )
    parser.add_argument(
        "config",
        type=Path,
        help="ACE config file (.tdl) used to locate TDL sources",
    )
    parser.add_argument(
        "dat",
        type=Path,
        help="Compiled ACE grammar file (.dat)",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory for the itsdb output profile",
    )
    parser.add_argument(
        "--ace-bin",
        metavar="PATH",
        help="Path to ACE binary (default: auto-discover)",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Skip writing the itsdb profile; print summary only",
    )
    parser.add_argument(
        "--report",
        type=Path,
        metavar="FILE",
        help="Also write the report to this file",
    )
    parser.add_argument(
        "--db",
        type=Path,
        metavar="FILE",
        help="Write results into the doctest table of this grammar SQLite DB",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Log TDL parsing warnings"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    try:
        ace_bin = find_ace(args.ace_bin)
    except FileNotFoundError as exc:
        sys.exit(str(exc))

    cfg = read_cfg(str(args.config))

    print(f"Reading TDL from {cfg['grammar_file']} …", file=sys.stderr)
    examples, types, lex_ids_for_type = extract_examples(cfg, sys.stderr)
    print(f"  {len(examples)} examples extracted.", file=sys.stderr)

    ts = None if args.no_profile else make_test_suite(args.output_dir, examples)

    print(f"Parsing with {args.dat} …", file=sys.stderr)
    verdicts = run_examples(
        examples, str(args.dat), ace_bin, types, lex_ids_for_type, ts
    )

    if ts is not None:
        print(f"itsdb profile written to {args.output_dir}", file=sys.stderr)

    if args.db is not None:
        write_to_db(verdicts, args.db)

    print()
    print_report(verdicts, cfg, str(args.config), report_path=args.report)


if __name__ == "__main__":
    main()
