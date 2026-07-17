#!/usr/bin/env python3
"""Parse a grammar's TDL docstring examples into a dated itsdb profile.

Extracts the <ex>/<nex>/<mex> examples from the grammar's TDL
docstrings, parses them with ACE, and writes a [incr tsdb()] profile to
<grammar>/tsdb/run/docstring_YYYY-MM-DD (adding -2, -3, ... when that
directory already exists).  Each item's verdict (PASS, FAIL-no-parse,
FAIL-type-absent, FAIL-type-in-tree) is recorded in its i-comment, and
a short per-verdict summary is printed to stdout.

Usage:
    python docstring_profile.py <ace-config> <grammar.dat>
        [--grammar-dir DIR] [--outdir DIR] [--ace-bin PATH] [--jobs N]
"""

import argparse
import datetime
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grm2db import find_ace
from parse_examples import (
    Verdict,
    default_jobs,
    extract_examples,
    make_test_suite,
    run_examples,
    verdict_label,
)
from tdl2db import read_cfg


def find_grammar_dir(config: Path) -> Path:
    """Return the nearest ancestor of *config* containing a tsdb/ directory.

    Falls back to the config file's own directory when no ancestor has one
    (the profile is then created under a fresh tsdb/run/ there).
    """
    for parent in config.resolve().parents:
        if (parent / "tsdb").is_dir():
            return parent
    return config.resolve().parent


def unique_profile_dir(base: Path) -> Path:
    """Return *base*, or the first of base-2, base-3, ... that is unused."""
    if not base.exists():
        return base
    n = 2
    while (candidate := base.with_name(f"{base.name}-{n}")).exists():
        n += 1
    return candidate


def summarize(verdicts: list[Verdict]) -> str:
    """Return a short per-verdict count summary."""
    counts = Counter(verdict_label(v) for v in verdicts)
    lines = [f"{len(verdicts)} docstring example(s)"]
    for label in sorted(counts):
        lines.append(f"  {label:<18} {counts[label]:>5}")
    return "\n".join(lines)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Parse TDL docstring examples into a dated itsdb profile."
    )
    parser.add_argument(
        "config", type=Path, help="ACE config file (.tdl) of the grammar"
    )
    parser.add_argument(
        "dat", type=Path, help="Compiled ACE grammar file (.dat)"
    )
    parser.add_argument(
        "--grammar-dir",
        type=Path,
        metavar="DIR",
        help="Grammar root holding tsdb/ (default: nearest ancestor of the "
             "config file with a tsdb/ directory)",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        metavar="DIR",
        help="Write the profile here instead of "
             "<grammar>/tsdb/run/docstring_YYYY-MM-DD",
    )
    parser.add_argument(
        "--ace-bin",
        metavar="PATH",
        help="Path to ACE binary (default: auto-discover)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=0,
        metavar="N",
        help="Parallel ACE processes; 0 = auto from CPUs and available "
             "memory (default: 0)",
    )
    args = parser.parse_args()

    try:
        ace_bin = find_ace(args.ace_bin)
    except FileNotFoundError as exc:
        sys.exit(str(exc))

    cfg = read_cfg(str(args.config))
    print(f"Reading TDL from {cfg['grammar_file']} …", file=sys.stderr)
    examples, types, lex_ids_for_type = extract_examples(cfg, sys.stderr)
    if not examples:
        print("No docstring examples found.")
        return

    if args.outdir is not None:
        outdir = args.outdir
    else:
        grammar_dir = args.grammar_dir or find_grammar_dir(args.config)
        date = datetime.date.today().isoformat()
        outdir = unique_profile_dir(
            grammar_dir / "tsdb" / "run" / f"docstring_{date}"
        )

    ts = make_test_suite(outdir, examples)
    print(f"Parsing with {args.dat} …", file=sys.stderr)
    verdicts = run_examples(
        examples,
        str(args.dat),
        ace_bin,
        types,
        lex_ids_for_type,
        ts,
        jobs=args.jobs or default_jobs(),
    )

    # record each item's verdict in its i-comment
    example_by_id = {v.example.i_id: v.example for v in verdicts}
    label_by_id = {v.example.i_id: verdict_label(v) for v in verdicts}
    item = ts["item"]
    for i, row in enumerate(item):
        ex = example_by_id[row["i-id"]]
        item.update(
            i,
            {
                "i-comment": f"type={ex.typ} kind={ex.kind} "
                             f"verdict={label_by_id[ex.i_id]}"
            },
        )
    ts.commit()

    print(summarize(verdicts))
    print(f"Profile written to {outdir}")


if __name__ == "__main__":
    main()
