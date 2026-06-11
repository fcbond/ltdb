"""Tests for the ESD phenomena catalogue (doc/esd-phenomena/)."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "doc" / "esd-phenomena")
)

import check_phenomena

REQUIRED_KEYS = {"description", "fingerprint", "grew-query", "url"}


@pytest.fixture(scope="module")
def phenomena():
    return check_phenomena.load_phenomena()


def test_catalogue_structure(phenomena):
    assert len(phenomena) == 26
    for name, entry in phenomena.items():
        assert set(entry) == REQUIRED_KEYS, name
        assert entry["grew-query"].startswith("pattern {"), name
        assert entry["url"].startswith("https://delph-in.github.io/docs/erg/"), name
        assert entry["description"], name


def test_queries_use_str_regex_syntax(phenomena):
    """grew regexes are OCaml Str: bare | or (...) match literally."""
    for name, entry in phenomena.items():
        for fragment in entry["grew-query"].split('re"'):
            if fragment is entry["grew-query"]:
                continue
            regex = fragment.split('"')[0]
            assert "|" not in regex.replace("\\|", ""), name
            assert "(" not in regex.replace("\\(", ""), name


def test_count_query_against_stub_backend():
    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            reply = {"status": "OK", "data": {"nb_solutions": len(body["request"])}}
            payload = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        n = check_phenomena.count_query(url, "toy", "pattern { N [] }")
        assert n == len("pattern { N [] }")
    finally:
        server.shutdown()
