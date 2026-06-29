"""Compare old (length-ordered) vs. new (GDEX-scored) example ranking.

Runs both queries against a real grammar DB, computes automatic GDEX
criterion statistics for each result set, and prints a side-by-side
comparison table suitable for inclusion in the paper.

Usage:
    uv run scripts/compare_gdex.py [--db web/db/ERG_2025.db] [--types TYPE ...]
                                   [--n 8] [--show N]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict as dd
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SENTLIM = 8  # default display limit


def holders(xs: list) -> str:
    return ",".join(["?"] * len(xs))


def gdex_score_sql(kw_pos_expr: str, len_expr: str, sent_expr: str) -> str:
    """GDEX SQL scoring expression (product of three soft criteria)."""
    return f"""
        CASE
            WHEN {len_expr} < 4                      THEN 0.0
            WHEN {len_expr} BETWEEN 10 AND 25         THEN 1.0
            WHEN {len_expr} < 10
                THEN CAST({len_expr} AS REAL) / 10.0
            ELSE 25.0 / CAST({len_expr} AS REAL)
        END
        *
        CASE WHEN SUBSTR({sent_expr}, -1) IN ('.', '!', '?') THEN 1.0
             ELSE 0.7
        END
        *
        CASE
            WHEN {len_expr} = 0 THEN 0.8
            WHEN CAST({kw_pos_expr} AS REAL) / {len_expr} > 0.1 THEN 1.0
            ELSE 0.8
        END"""


# ---------------------------------------------------------------------------
# Old approach: length-ordered with 20 % offset
# ---------------------------------------------------------------------------

def _offset_limit(n: int, lim: int) -> tuple[int, int]:
    if lim >= n:
        return 0, n
    offset = round(n * 0.2)
    if n - offset < lim:
        offset = n - lim
    return offset, lim


def old_cx(conn: sqlite3.Connection, cx: str, lim: int) -> list[str]:
    """Old get_phenomena_by_cx query (length order + 20 % offset)."""
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT profile, sid FROM typind WHERE typ = ?)",
        (cx,),
    )
    row = c.fetchone()
    maxp = row[0] if row else 0
    offset, limit = _offset_limit(maxp, lim)

    c.execute(
        """SELECT a.profile, a.sid, g.sent
           FROM typind AS a
           LEFT JOIN sent AS b ON a.profile=b.profile AND a.sid=b.sid
           LEFT JOIN gold AS g ON a.profile=g.profile AND a.sid=g.sid
           WHERE a.typ = ?
           GROUP BY b.profile, b.sid
           ORDER BY MAX(b.wid)
           LIMIT ? OFFSET ?""",
        (cx, limit, offset),
    )
    return [r[2] for r in c if r[2]]


def new_cx(conn: sqlite3.Connection, cx: str, lim: int) -> list[str]:
    """New get_phenomena_by_cx query (GDEX score)."""
    gdex = gdex_score_sql(
        kw_pos_expr="MIN(COALESCE(a.kara, 0))",
        len_expr="MAX(b.wid)",
        sent_expr="g.sent",
    )
    c = conn.cursor()
    c.execute(
        f"""SELECT a.profile, a.sid, g.sent,
               {gdex} AS gdex_score
           FROM typind AS a
           LEFT JOIN sent AS b ON a.profile=b.profile AND a.sid=b.sid
           LEFT JOIN gold AS g ON a.profile=g.profile AND a.sid=g.sid
           WHERE a.typ = ?
           GROUP BY a.profile, a.sid
           ORDER BY gdex_score DESC
           LIMIT ?""",
        (cx, lim),
    )
    return [r[2] for r in c if r[2]]


def old_lexid(conn: sqlite3.Connection, lexid: str, lim: int) -> list[str]:
    """Old get_phenomena_by_lexids for a single lexid."""
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT profile, sid FROM sent WHERE lexid = ?)",
        (lexid,),
    )
    row = c.fetchone()
    maxp = row[0] if row else 0
    offset, limit = _offset_limit(maxp, lim)

    c.execute(
        """SELECT a.profile, a.sid, g.sent
           FROM sent AS a
           LEFT JOIN sent AS b ON a.profile=b.profile AND a.sid=b.sid
           LEFT JOIN gold AS g ON a.profile=g.profile AND a.sid=g.sid
           WHERE a.lexid = ?
           GROUP BY b.profile, b.sid
           ORDER BY MAX(b.wid)
           LIMIT ? OFFSET ?""",
        (lexid, limit, offset),
    )
    return [r[2] for r in c if r[2]]


def new_lexid(conn: sqlite3.Connection, lexid: str, lim: int) -> list[str]:
    """New get_phenomena_by_lexids for a single lexid (GDEX score)."""
    gdex = gdex_score_sql(
        kw_pos_expr="MIN(a.wid)",
        len_expr="MAX(b.wid)",
        sent_expr="g.sent",
    )
    c = conn.cursor()
    c.execute(
        f"""SELECT a.profile, a.sid, g.sent,
               {gdex} AS gdex_score
           FROM sent AS a
           LEFT JOIN sent AS b ON a.profile=b.profile AND a.sid=b.sid
           LEFT JOIN gold AS g ON a.profile=g.profile AND a.sid=g.sid
           WHERE a.lexid = ?
           GROUP BY a.profile, a.sid
           ORDER BY gdex_score DESC
           LIMIT ?""",
        (lexid, lim),
    )
    return [r[2] for r in c if r[2]]


# ---------------------------------------------------------------------------
# Automatic GDEX metrics
# ---------------------------------------------------------------------------

def is_terminal(sent: str) -> bool:
    return sent.strip()[-1:] in {".", "!", "?"} if sent.strip() else False


def word_count(sent: str) -> int:
    return len(sent.split())


def score_set(sents: list[str]) -> dict:
    """Compute aggregate GDEX criterion statistics for a set of sentences."""
    if not sents:
        return {"n": 0, "pct_terminal": 0.0, "pct_optimal_len": 0.0,
                "mean_len": 0.0, "mean_gdex": 0.0}
    terminal = sum(1 for s in sents if is_terminal(s))
    wcs = [word_count(s) for s in sents]
    optimal = sum(1 for w in wcs if 10 <= w <= 25)
    gdex_scores = []
    for s, wc in zip(sents, wcs):
        if wc < 4:
            ls = 0.0
        elif 10 <= wc <= 25:
            ls = 1.0
        elif wc < 10:
            ls = wc / 10.0
        else:
            ls = 25.0 / wc
        ss = 1.0 if is_terminal(s) else 0.7
        gdex_scores.append(ls * ss)  # position score omitted (no wid here)
    return {
        "n": len(sents),
        "pct_terminal": 100 * terminal / len(sents),
        "pct_optimal_len": 100 * optimal / len(sents),
        "mean_len": sum(wcs) / len(wcs),
        "mean_gdex": sum(gdex_scores) / len(gdex_scores),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def truncate(s: str, n: int = 80) -> str:
    s = s.strip()
    return s[:n - 1] + "…" if len(s) > n else s


def print_comparison(
    label: str,
    old: list[str],
    new: list[str],
    show: int = 3,
) -> None:
    old_stats = score_set(old)
    new_stats = score_set(new)

    print(f"\n{'=' * 72}")
    print(f"TYPE: {label}")
    print(f"{'=' * 72}")
    print(f"{'Metric':<28}  {'Old (length+offset)':>20}  {'New (GDEX)':>20}")
    print(f"{'-' * 72}")
    for key, label_str in [
        ("n", "sentences returned"),
        ("pct_terminal", "% terminal punct"),
        ("pct_optimal_len", "% optimal length (10-25)"),
        ("mean_len", "mean word count"),
        ("mean_gdex", "mean GDEX score (approx)"),
    ]:
        oval = old_stats[key]
        nval = new_stats[key]
        fmt = ".1f" if isinstance(oval, float) else "d"
        print(f"  {label_str:<26}  {oval:>20{fmt}}  {nval:>20{fmt}}")

    only_new = [s for s in new[:show] if s not in old[:show]]
    if only_new:
        print(f"\n  Top-{show} examples UNIQUE to new ranking:")
        for s in only_new:
            print(f"    + {truncate(s)}")

    print(f"\n  Top-{show} OLD:")
    for s in old[:show]:
        marker = "  " if s in new[:show] else "✗ "
        print(f"    {marker}{truncate(s)}")

    print(f"\n  Top-{show} NEW:")
    for s in new[:show]:
        marker = "  " if s in old[:show] else "✓ "
        print(f"    {marker}{truncate(s)}")


def latex_table_row(typ: str, old: list[str], new: list[str]) -> str:
    """One LaTeX table row comparing old vs. new aggregate statistics."""
    os_ = score_set(old)
    ns_ = score_set(new)
    return (
        f"\\texttt{{{typ.replace('_', r'\textunderscore ')}}}"
        f" & {os_['pct_terminal']:.0f}\\%"
        f" & {os_['pct_optimal_len']:.0f}\\%"
        f" & {os_['mean_gdex']:.2f}"
        f" & {ns_['pct_terminal']:.0f}\\%"
        f" & {ns_['pct_optimal_len']:.0f}\\%"
        f" & {ns_['mean_gdex']:.2f}"
        r" \\"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_CX_TYPES = [
    "hd-cmp_u_c",       # head-complement (very high freq, many diverse sents)
    "sb-hd_mc_c",       # subject-head main clause
    "cl_rc-fin-modgap_c",  # finite relative clause
    "pp_frg_c",         # PP fragment
    "hd-aj_int-unsl_c", # head-adjunct intransitive
]

DEFAULT_LEXIDS = [
    "arrive_v1",
    "believe_v1",
    "problem_n1",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--db",
        default="web/db/ERG_2025.db",
        help="Path to grammar SQLite DB",
    )
    ap.add_argument(
        "--cx", nargs="*", default=DEFAULT_CX_TYPES,
        help="Construction types to compare",
    )
    ap.add_argument(
        "--lexids", nargs="*", default=DEFAULT_LEXIDS,
        help="Lexids to compare",
    )
    ap.add_argument(
        "--n", type=int, default=SENTLIM,
        help="Number of sentences to retrieve (default: 8)",
    )
    ap.add_argument(
        "--show", type=int, default=3,
        help="Number of example sentences to display per type (default: 3)",
    )
    ap.add_argument(
        "--latex", action="store_true",
        help="Also print a LaTeX table of aggregate statistics",
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))

    all_rows: list[tuple[str, list[str], list[str]]] = []

    for cx in args.cx:
        o = old_cx(conn, cx, args.n)
        n = new_cx(conn, cx, args.n)
        if not o and not n:
            print(f"\n[skipping {cx}: no sentences in DB]")
            continue
        print_comparison(cx, o, n, show=args.show)
        all_rows.append((cx, o, n))

    for lexid in args.lexids:
        o = old_lexid(conn, lexid, args.n)
        n = new_lexid(conn, lexid, args.n)
        if not o and not n:
            print(f"\n[skipping lexid {lexid}: not found]")
            continue
        print_comparison(f"lexid:{lexid}", o, n, show=args.show)
        all_rows.append((f"lexid:{lexid}", o, n))

    conn.close()

    if args.latex and all_rows:
        print("\n\n% --- LaTeX table ---")
        print(r"\begin{tabular}{lrrr|rrr}")
        print(r"\hline")
        print(r"Type & \multicolumn{3}{c|}{Old (length+offset)} & \multicolumn{3}{c}{New (GDEX)} \\")
        print(r" & Term.\% & Opt.len\% & Score & Term.\% & Opt.len\% & Score \\")
        print(r"\hline")
        for typ, o, n in all_rows:
            print(latex_table_row(typ, o, n))
        print(r"\hline")
        print(r"\end{tabular}")


if __name__ == "__main__":
    main()
