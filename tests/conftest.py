"""Shared fixtures for ltdb tests."""

import os
import socket
import subprocess
import time

import pytest


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def gunicorn_url():
    """Start a gunicorn server for the session; yield its base URL."""
    port = _free_port()
    env = {**os.environ, "SECRET_KEY": "test-secret-not-for-production"}

    proc = subprocess.Popen(
        [
            ".venv/bin/gunicorn",
            "--workers=4",
            "--worker-class=sync",
            f"--bind=127.0.0.1:{port}",
            "--timeout=60",
            "wsgi:app",
        ],
        cwd=_REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if not _wait_for_port(port, timeout=20):
        proc.terminate()
        stderr = proc.stderr.read().decode()
        pytest.fail(f"gunicorn did not start within 20s:\n{stderr}")

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(gunicorn_url):
    """Override pytest-playwright base_url with our gunicorn server."""
    return gunicorn_url


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Grammar/sentence constants shared across test modules
GRAMMAR = "ERG_2025.db"

_DAT = os.path.join(_REPO_ROOT, "web", "db", GRAMMAR[:-3] + ".dat")
needs_dat = pytest.mark.skipif(
    not os.path.exists(_DAT),
    reason=f"{GRAMMAR[:-3]}.dat not found — run: python scripts/grm2db.py --ace",
)

SENTENCES = [
    "The dog barked.",
    "Dogs bark.",
    "Kim likes Sandy.",
    "It is raining.",
    "Every cat sees a dog.",
    "The old man saw the young woman.",
    "She gave him a book.",
    "The cat sat on the mat.",
    "Abrams knows that Browne left.",
    "The manager hired a new employee.",
]

# A long, syntactically complex sentence to exercise ACE timeouts and
# robustness under heavy parse load.
LONG_SENTENCE = (
    "The distinguished professor of linguistics who had been studying the "
    "intricate syntactic structures of natural language for many decades "
    "argued convincingly that the children who the teachers that the "
    "administrators the school board hired supervised taught were remarkably "
    "talented and would one day make significant contributions to the field."
)
