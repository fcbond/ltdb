"""Merge grew corpora descriptions into one file.

Each input is a corpora.json list as written by db2grew.py; the output
is the concatenation of all of them, suitable for grew_match_quick or
`run.sh --grew-match` (see doc/grew-match.md).

Usage:
    python merge_grew_corpora.py MERGED_OUT CORPORA_JSON [CORPORA_JSON ...]
"""

import json
import sys


def merge(merged_path: str, corpora_paths: list[str]) -> None:
    """Concatenate the corpora lists in *corpora_paths* into *merged_path*."""
    corpora = []
    for path in corpora_paths:
        with open(path) as f:
            corpora.extend(json.load(f))
    with open(merged_path, "w") as f:
        json.dump(corpora, f, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: merge_grew_corpora.py MERGED_OUT CORPORA_JSON...")
    merge(sys.argv[1], sys.argv[2:])
