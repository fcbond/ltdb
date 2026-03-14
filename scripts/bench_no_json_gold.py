"""Benchmark on-the-fly JSON conversion vs pre-stored JSON in the gold table.

Usage:
    python scripts/bench_no_json_gold.py web/db/ERG_\(2025\).db [N]

N is the number of rows to sample (default 200, matching typical type page usage).
"""

import sqlite3
import sys
import time

from web.ltdb import deriv_to_dict, mrs_to_dicts




def bench(db_path: str, n: int) -> None:
    conn = sqlite3.connect(db_path)

    # Sample N rows that have all data populated
    rows = conn.execute(
        f"""SELECT deriv, mrs, deriv_json, mrs_json, dmrs_json
            FROM gold
            WHERE deriv IS NOT NULL AND mrs IS NOT NULL
              AND deriv_json IS NOT NULL AND mrs_json IS NOT NULL
            LIMIT {n}"""
    ).fetchall()

    if not rows:
        print("No rows with full data found — is this an old-style DB?")
        sys.exit(1)

    actual_n = len(rows)
    print(f"Sampled {actual_n} rows from {db_path}")

    # --- Baseline: read pre-stored JSON (just parse to confirm it's valid) ---
    t0 = time.perf_counter()
    for deriv, mrs, deriv_json, mrs_json, dmrs_json in rows:
        _ = deriv_json
        _ = mrs_json
        _ = dmrs_json
    t_baseline = time.perf_counter() - t0

    # --- On-the-fly conversion ---
    errors = 0
    t0 = time.perf_counter()
    for deriv, mrs, *_ in rows:
        d = deriv_to_dict(deriv)
        m, dm = mrs_to_dicts(mrs)
        if d is None or m is None:
            errors += 1
    t_convert = time.perf_counter() - t0

    conn.close()

    print(f"\nRows processed : {actual_n}")
    print(f"Conversion errors: {errors}")
    print(f"\nBaseline (read pre-stored JSON) : {t_baseline*1000:.1f} ms total, "
          f"{t_baseline/actual_n*1000:.2f} ms/row")
    print(f"On-the-fly conversion            : {t_convert*1000:.1f} ms total, "
          f"{t_convert/actual_n*1000:.2f} ms/row")
    print(f"Overhead per row                 : "
          f"{(t_convert-t_baseline)/actual_n*1000:.2f} ms")
    print(f"Overhead for 8 rows (type page)  : "
          f"{(t_convert-t_baseline)/actual_n*8*1000:.1f} ms")

    # Column size summary
    conn2 = sqlite3.connect(db_path)
    row = conn2.execute("""
        SELECT
          COUNT(*) as n,
          SUM(LENGTH(COALESCE(deriv_json,''))) / 1e6 as deriv_json_mb,
          SUM(LENGTH(COALESCE(mrs_json,'')))   / 1e6 as mrs_json_mb,
          SUM(LENGTH(COALESCE(dmrs_json,'')))  / 1e6 as dmrs_json_mb,
          SUM(LENGTH(COALESCE(deriv,'')))      / 1e6 as deriv_mb,
          SUM(LENGTH(COALESCE(mrs,'')))        / 1e6 as mrs_mb
        FROM gold
    """).fetchone()
    conn2.close()
    n_rows, deriv_json_mb, mrs_json_mb, dmrs_json_mb, deriv_mb, mrs_mb = row
    json_total = deriv_json_mb + mrs_json_mb + dmrs_json_mb
    print(f"\n--- Column sizes across all {int(n_rows)} rows ---")
    print(f"deriv_json : {deriv_json_mb:.0f} MB")
    print(f"mrs_json   : {mrs_json_mb:.0f} MB")
    print(f"dmrs_json  : {dmrs_json_mb:.0f} MB")
    print(f"  -> JSON total dropped : {json_total:.0f} MB")
    print(f"deriv (kept): {deriv_mb:.0f} MB")
    print(f"mrs   (kept): {mrs_mb:.0f} MB")
    print(f"  -> raw total kept     : {deriv_mb+mrs_mb:.0f} MB")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "web/db/ERG_(2025).db"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    bench(db_path, n)
