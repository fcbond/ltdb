"""End-to-end tests for the ltdb demo (parse/MRS/DMRS).

Run with:
    uv run pytest tests/test_demo.py -v

The gunicorn_url fixture (conftest.py) starts a 4-worker gunicorn server for
the session so tests run against the real WSGI stack, not Flask's dev server.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import requests

from .conftest import GRAMMAR, LONG_SENTENCE, SENTENCES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DAT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "web", "db", GRAMMAR[:-3] + ".dat",
)
needs_dat = pytest.mark.skipif(
    not os.path.exists(_DAT),
    reason=f"{GRAMMAR[:-3]}.dat not found — run: python scripts/grm2db.py --ace",
)


def _parse(base_url, sentence, *, n=1, tree=True, mrs=True, dmrs=True):
    """POST to /parse and return the response object."""
    return requests.post(
        f"{base_url}/parse",
        data={
            "input": sentence,
            "grm": GRAMMAR,
            "results": n,
            "derivation": "json" if tree else "null",
            "mrs": "json" if mrs else "null",
            "dmrs": "json" if dmrs else "null",
        },
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Basic connectivity
# ---------------------------------------------------------------------------


def test_home_page(gunicorn_url):
    # Home page queries every .db file for its summary — allow extra time
    r = requests.get(gunicorn_url + "/", timeout=60)
    assert r.status_code == 200


def test_demo_page_loads(gunicorn_url):
    r = requests.get(gunicorn_url + "/demo", timeout=10)
    assert r.status_code == 200
    assert "Parse Demo" in r.text


# ---------------------------------------------------------------------------
# Parse API — correctness
# ---------------------------------------------------------------------------


@needs_dat
def test_parse_returns_readings(gunicorn_url):
    r = _parse(gunicorn_url, "Dogs bark.")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "error" not in data, data.get("error")
    assert data["readings"] > 0


@needs_dat
@pytest.mark.parametrize("sentence", SENTENCES)
def test_parse_sentence(gunicorn_url, sentence):
    """Each sentence should parse without a 500 and return at least one reading."""
    r = _parse(gunicorn_url, sentence)
    assert r.status_code == 200, f"HTTP {r.status_code} for {sentence!r}: {r.text[:200]}"
    data = r.json()
    assert "error" not in data, f"ACE error for {sentence!r}: {data['error']}"
    assert data["readings"] > 0, f"No parses for {sentence!r}"


@needs_dat
def test_parse_result_has_tree_mrs_dmrs(gunicorn_url):
    """Regression: MRS and DMRS must be non-null alongside the derivation tree.

    Previously ace.parse() used next(generator), leaving ACEParser context
    managers open until GC.  Under load, exhausted file descriptors caused
    result.mrs() to fail silently, returning null MRS/DMRS in the response
    while the derivation (already buffered) still appeared.
    """
    r = _parse(gunicorn_url, "The dog barked.", n=3)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["readings"] > 0
    first = data["results"][0]
    assert first.get("derivation") is not None, "derivation (tree) is null"
    assert first.get("mrs") is not None, "MRS is null — ACE subprocess may not be closing cleanly"
    assert first.get("dmrs") is not None, "DMRS is null"


# ---------------------------------------------------------------------------
# Concurrency / file-descriptor leak regression
# ---------------------------------------------------------------------------


@needs_dat
def test_concurrent_parses_no_errors(gunicorn_url):
    """Regression: 30 concurrent parse requests must all return 200 with valid data.

    The old ace.parse() → next(generator) pattern left ACE subprocesses open
    until GC, accumulating file descriptors.  With 4 gunicorn workers each
    holding open ~5 fds per ACE process, ~30 concurrent requests would exhaust
    the default fd limit (1024) and cause 'too many files open' 500 errors.
    """
    n_requests = 30
    inputs = [SENTENCES[i % len(SENTENCES)] for i in range(n_requests)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_parse, gunicorn_url, s): s for s in inputs}
        responses = {fut: (s, fut.result()) for fut, s in futures.items()}

    failures = [
        f"[{s!r}] HTTP {r.status_code}: {r.text[:150]}"
        for _, (s, r) in responses.items()
        if r.status_code != 200
    ]
    assert not failures, f"{len(failures)}/{n_requests} requests failed:\n" + "\n".join(failures[:5])

    missing_mrs = [
        s for _, (s, r) in responses.items()
        if r.status_code == 200
        and r.json().get("readings", 0) > 0
        and r.json()["results"][0].get("mrs") is None
    ]
    assert not missing_mrs, f"MRS null in {len(missing_mrs)} responses (fd leak?): {missing_mrs[:3]}"


@needs_dat
def test_long_sentence_does_not_crash(gunicorn_url):
    """A pathologically long/complex sentence must return 200 (possibly 0 readings).

    ACE should time out gracefully rather than hanging the worker or returning
    a 500.  The gunicorn worker timeout is 60 s; the request timeout here is
    shorter so a stuck worker surfaces as a test failure, not a hang.
    """
    r = _parse(gunicorn_url, LONG_SENTENCE, n=1)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    data = r.json()
    # Either parses (unlikely for this sentence) or returns 0 readings — either is fine
    assert "error" not in data or "too many" not in data.get("error", ""), \
        f"Resource exhaustion error: {data.get('error')}"
