"""Unit tests for route helpers that don't need a live server or ACE."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# App fixture — creates the Flask app and pushes a context so routes.py
# can be imported and its module-level decorators can execute.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    from web import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    ctx = _app.app_context()
    ctx.push()
    yield _app
    ctx.pop()


# ---------------------------------------------------------------------------
# dat_path_for — zero-size and missing file handling
# ---------------------------------------------------------------------------

class TestDatPathFor:
    def test_missing_dat_returns_none(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        (tmp_path / "db").mkdir()
        assert routes.dat_path_for("ERG_2025.db") is None

    def test_zero_size_dat_returns_none(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        (tmp_path / "db").mkdir()
        (tmp_path / "db" / "ERG_2025.dat").touch()          # 0 bytes
        assert routes.dat_path_for("ERG_2025.db") is None

    def test_non_empty_dat_returns_path(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        dat = db_dir / "ERG_2025.dat"
        dat.write_bytes(b"\x00" * 1024)
        assert routes.dat_path_for("ERG_2025.db") == str(dat)

    def test_strips_db_suffix(self, app, tmp_path, monkeypatch):
        import web.routes as routes
        monkeypatch.setattr(routes, "current_directory", str(tmp_path))
        (tmp_path / "db").mkdir()
        (tmp_path / "db" / "GG.dat").write_bytes(b"data")
        assert routes.dat_path_for("GG.db") is not None


# ---------------------------------------------------------------------------
# MRS raw-string fallback when pydelphin cannot parse ACE's MRS output
# ---------------------------------------------------------------------------

_RAW_MRS = "[ TOP: h0 INDEX: e2 [ e SF: prop ] RELS: < > HCONS: < h0 qeq e2 > ]"


def _make_ace_result(*, mrs_raises=False, raw_mrs=None):
    result = MagicMock()
    if mrs_raises:
        result.mrs.side_effect = Exception("MRSSyntaxError: expected a symbol")
    else:
        result.mrs.return_value = MagicMock()
    result.get.side_effect = lambda key, default=None: (
        raw_mrs if key == "mrs" else default
    )
    result.result.return_value = None
    return result


@pytest.fixture()
def client(app, tmp_path, monkeypatch):
    """Test client with a fake non-empty .dat for grammar 'fake.db'."""
    import web.routes as routes
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    (db_dir / "fake.dat").write_bytes(b"x" * 512)
    monkeypatch.setattr(routes, "current_directory", str(tmp_path))
    return app.test_client()


def _post_parse(client, *, grm="fake.db", sentence="test", mrs="json"):
    return client.post(
        "/parse",
        data={
            "input": sentence,
            "grm": grm,
            "results": 1,
            "derivation": "null",
            "mrs": mrs,
            "dmrs": "null",
        },
    )


class TestMrsRawFallback:
    def test_fallback_sets_mrs_str_on_pydelphin_failure(self, client):
        """When result.mrs() raises, the raw ACE string is used as mrs_str."""
        mock_result = _make_ace_result(mrs_raises=True, raw_mrs=_RAW_MRS)
        mock_response = MagicMock()
        mock_response.results.return_value = [mock_result]

        with patch("delphin.ace.ACEParser") as MockParser, \
             patch("web.routes.find_ace", return_value="/bin/ace"):
            MockParser.return_value.__enter__.return_value.interact.return_value = (
                mock_response
            )
            MockParser.return_value.__exit__.return_value = False
            r = _post_parse(client)

        data = r.get_json()
        assert r.status_code == 200
        assert len(data["errors"]) == 1
        assert "MRSSyntaxError" in data["errors"][0]
        assert data["results"][0].get("mrs_str") == _RAW_MRS

    def test_no_fallback_when_raw_mrs_absent(self, client):
        """When result.get('mrs') is None there is no mrs_str in the response."""
        mock_result = _make_ace_result(mrs_raises=True, raw_mrs=None)
        mock_response = MagicMock()
        mock_response.results.return_value = [mock_result]

        with patch("delphin.ace.ACEParser") as MockParser, \
             patch("web.routes.find_ace", return_value="/bin/ace"):
            MockParser.return_value.__enter__.return_value.interact.return_value = (
                mock_response
            )
            MockParser.return_value.__exit__.return_value = False
            r = _post_parse(client)

        data = r.get_json()
        assert r.status_code == 200
        assert "mrs_str" not in data["results"][0]

    def test_successful_pydelphin_parse_no_errors(self, client):
        """When pydelphin succeeds, errors list is empty and mrs_str is set."""
        mrsjson_encoded = (
            '{"top": "h0", "index": "e2", "relations": [], "constraints": []}'
        )
        mock_result = _make_ace_result(mrs_raises=False)
        mock_response = MagicMock()
        mock_response.results.return_value = [mock_result]

        with patch("delphin.ace.ACEParser") as MockParser, \
             patch("delphin.codecs.simplemrs.encode", return_value=_RAW_MRS), \
             patch("delphin.codecs.mrsjson.encode", return_value=mrsjson_encoded), \
             patch("web.routes.find_ace", return_value="/bin/ace"):
            MockParser.return_value.__enter__.return_value.interact.return_value = (
                mock_response
            )
            MockParser.return_value.__exit__.return_value = False
            r = _post_parse(client)

        data = r.get_json()
        assert r.status_code == 200
        assert data["errors"] == []
        assert data["results"][0]["mrs_str"] == _RAW_MRS
