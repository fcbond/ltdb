"""Security regression tests for route input validation."""

import os

import pytest

from web import create_app
from web.db import get_grammar_names
from web.ltdb import docstring2html


@pytest.fixture(scope="module")
def client():
    os.environ["SECRET_KEY"] = "test-secret-not-for-production"
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def grammar():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
    grammars = get_grammar_names(root)
    if not grammars:
        pytest.skip("No grammar DBs available for route validation tests")
    return grammars[0]


def test_home_rejects_unknown_grammar(client):
    response = client.post("/", data={"grm": "../../etc/passwd"})

    assert response.status_code == 400


@pytest.mark.parametrize("endpoint", ["/parse", "/generate"])
def test_api_rejects_unknown_grammar(client, endpoint):
    response = client.post(endpoint, data={"grm": "../../etc/passwd"})

    assert response.status_code == 400


def test_parse_rejects_invalid_results_before_ace(client, grammar, monkeypatch):
    from web import routes

    monkeypatch.setattr(routes, "dat_path_for", lambda grm: "/tmp/fake.dat")
    response = client.post(
        "/parse",
        data={"grm": grammar, "input": "Dogs bark.", "results": "many"},
    )

    assert response.status_code == 400
    assert "Results must be" in response.get_json()["error"]


def test_parse_rejects_oversized_input_before_ace(client, grammar, monkeypatch):
    from web import routes

    monkeypatch.setattr(routes, "dat_path_for", lambda grm: "/tmp/fake.dat")
    response = client.post(
        "/parse",
        data={
            "grm": grammar,
            "input": "x" * (routes.MAX_PARSE_CHARS + 1),
            "results": "1",
        },
    )

    assert response.status_code == 400
    assert "Input is too long" in response.get_json()["error"]


def test_generate_rejects_oversized_mrs_before_ace(client, grammar, monkeypatch):
    from web import routes

    monkeypatch.setattr(routes, "dat_path_for", lambda grm: "/tmp/fake.dat")
    response = client.post(
        "/generate",
        data={"grm": grammar, "mrs": "x" * (routes.MAX_GENERATE_MRS_CHARS + 1)},
    )

    assert response.status_code == 400
    assert "MRS is too large" in response.get_json()["error"]


def test_parse_returns_busy_when_ace_slots_are_exhausted(client, grammar, monkeypatch):
    from web import routes

    monkeypatch.setattr(routes, "dat_path_for", lambda grm: "/tmp/fake.dat")
    acquired = []
    for _ in range(routes.ACE_CONCURRENCY):
        assert routes._ace_slots.acquire(blocking=False)
        acquired.append(True)
    try:
        response = client.post(
            "/parse",
            data={"grm": grammar, "input": "Dogs bark.", "results": "1"},
        )
    finally:
        for _ in acquired:
            routes._ace_slots.release()

    assert response.status_code == 503
    assert "ACE is busy" in response.get_json()["error"]


def test_docstring_markdown_escapes_raw_html():
    html = docstring2html("x", "Safe **markdown** <script>alert(1)</script>")

    assert "<strong>markdown</strong>" in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


@pytest.mark.parametrize(
    ("tag", "heading"),
    [
        ("description", "Description"),
        ("features", "Features"),
        ("history", "History"),
        ("notes", "Notes"),
        ("todo", "Todo"),
    ],
)
def test_docstring_section_tags_become_headers(tag, heading):
    html = docstring2html("x", f"<{tag}>Section body")

    assert f"<h3>{heading}</h3>" in html
    assert "<p>Section body</p>" in html


def test_docstring_unknown_tags_are_displayed_literally():
    html = docstring2html("x", "Use <math/> or <native> safely.")

    assert "&lt;math/&gt;" in html
    assert "&lt;native&gt;" in html
