"""Playwright checks for the generated static LTDB mirror."""

import os
import socket
import subprocess
import time

import pytest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOCS = os.path.join(ROOT, "docs")

# these tests exercise the frozen mirror in the enclosing grammary
# checkout; skip when it has not been generated
pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(DOCS, "ltdb", "type.html")),
    reason="static mirror not generated (run scripts/freeze_ltdb.py)",
)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def static_url():
    """Serve docs/ for static mirror browser tests."""
    port = _free_port()
    proc = subprocess.Popen(
        ["python", "-m", "http.server", "-d", DOCS, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not _wait_for_port(port):
        proc.terminate()
        stderr = proc.stderr.read().decode()
        pytest.fail(f"static server did not start:\n{stderr}")

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.slow
def test_static_tree_shift_click_stays_in_current_grammar(page, static_url):
    """Shift-clicking a tree node should open the same grammar's type page."""
    page.goto(f"{static_url}/ltdb/type.html?grammar=ERG_2025&type=root_robust")
    page.wait_for_selector(".ltdb-examples li", timeout=10_000)
    page.locator(".ltdb-tree-details summary").nth(1).click()
    page.wait_for_selector(".ltdb-tree svg", timeout=10_000)

    node = page.locator(".ltdb-tree-node", has_text="root_robust").first
    assert node.count() == 1

    with page.expect_navigation():
        node.click(modifiers=["Shift"])

    assert page.url == f"{static_url}/ltdb/type.html?grammar=ERG_2025&type=root_robust"
