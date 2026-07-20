"""Unit tests for /api/fs/browse — the local directory picker's backend."""
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def test_browse_lists_subdirectories(tmp_path):
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "a_dir").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    (tmp_path / "a_file.txt").write_text("x")

    response = _client().get("/api/fs/browse", params={"path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["current"] == str(tmp_path)
    assert body["parent"] == str(tmp_path.parent)
    assert [d["name"] for d in body["dirs"]] == ["a_dir", "b_dir"]


def test_browse_falls_back_to_home_when_path_missing():
    response = _client().get("/api/fs/browse", params={"path": "/no/such/path/at/all"})
    assert response.status_code == 200
    assert response.json()["current"]


def test_browse_defaults_to_home_when_no_path_given():
    import os
    response = _client().get("/api/fs/browse")
    assert response.status_code == 200
    assert response.json()["current"] == os.path.expanduser("~")
