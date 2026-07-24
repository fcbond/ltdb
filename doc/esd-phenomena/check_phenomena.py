"""Run the ESD phenomena grew queries against a grew-match corpus.

Counts each phenomenon's grew-query in a corpus served by a grew-match
backend (see doc/grew-match.md for setting one up):

    python check_phenomena.py ERG_ERG_2025_dmrs
    python check_phenomena.py --backend http://localhost:8899 ERG_ERG_2025_dmrs

Only the standard library is required (Python >= 3.11 for tomllib).
"""

import argparse
import json
import sys
import tomllib
import urllib.request
from pathlib import Path

PHENOMENA_TOML = Path(__file__).resolve().parent / "phenomena.toml"


def load_phenomena(path=PHENOMENA_TOML):
    """Return the phenomena dictionary from the TOML file.

    Args:
        path: the phenomena TOML file

    Returns:
        Dictionary mapping phenomenon name to its description,
        fingerprint, grew-query and url
    """
    with open(path, "rb") as f:
        return tomllib.load(f)


def count_query(backend, corpus, request, timeout=300):
    """Count the matches of one grew request in a grew-match corpus.

    Args:
        backend: base URL of the grew-match backend
        corpus: corpus identifier in the backend's corpusbank
        request: the grew request to count
        timeout: seconds to wait for the backend

    Returns:
        The number of matches

    Raises:
        RuntimeError: if the backend reports an error
    """
    body = json.dumps({"corpus": corpus, "request": request, "clust": {}})
    req = urllib.request.Request(
        f"{backend.rstrip('/')}/count", data=body.encode(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        reply = json.load(response)
    if reply.get("status") != "OK":
        raise RuntimeError(json.dumps(reply.get("message", reply)))
    return reply["data"]["nb_solutions"]


def main(argv=None):
    """Count every phenomenon's grew-query in a corpus (command line)."""
    parser = argparse.ArgumentParser(
        prog="check_phenomena",
        description="Count ESD phenomena in a grew-match corpus",
    )
    parser.add_argument(
        "--backend",
        default="http://localhost:8899",
        help="grew-match backend URL (default: %(default)s)",
    )
    parser.add_argument("corpus", help="corpus id, e.g. ERG_ERG_2025_dmrs")
    args = parser.parse_args(argv)

    phenomena = load_phenomena()
    width = max(map(len, phenomena))
    failures = 0
    for name, entry in phenomena.items():
        try:
            n = count_query(args.backend, args.corpus, entry["grew-query"])
            print(f"{name:{width}}  {n:>8}")
        except Exception as err:
            failures += 1
            print(f"{name:{width}}  ERROR: {err}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
