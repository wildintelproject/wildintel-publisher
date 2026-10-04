"""Unit tests for /api/fs/browse — the local directory picker's backend."""
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
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


def test_pick_directory_returns_what_the_native_dialog_chose():
    from unittest.mock import patch

    with patch("wildintel_publisher.web.services.native_dialog.pick_directory", return_value="/data/yolo") as pick:
        response = _client().post("/api/fs/pick-directory", json={"initial_path": "/data", "title": "Pick"})
    assert response.status_code == 200
    assert response.json() == {"path": "/data/yolo"}
    pick.assert_called_once_with("/data", "Pick")


def test_pick_directory_reports_a_cancel_as_a_null_path():
    from unittest.mock import patch

    with patch("wildintel_publisher.web.services.native_dialog.pick_directory", return_value=None):
        assert _client().post("/api/fs/pick-directory", json={}).json() == {"path": None}


def test_pick_directory_is_501_when_the_machine_has_no_native_dialog():
    from unittest.mock import patch
    from wildintel_publisher.web.services.native_dialog import NativeDialogUnavailable

    with patch("wildintel_publisher.web.services.native_dialog.pick_directory", side_effect=NativeDialogUnavailable("no zenity")):
        assert _client().post("/api/fs/pick-directory", json={}).status_code == 501


def test_native_dialog_runs_zenity_on_linux_and_treats_a_failed_exit_as_a_cancel(tmp_path):
    from unittest.mock import MagicMock, patch
    from wildintel_publisher.web.services import native_dialog

    with patch.object(native_dialog.sys, "platform", "linux"), \
         patch.object(native_dialog.shutil, "which", side_effect=lambda t: "/usr/bin/zenity" if t == "zenity" else None), \
         patch.object(native_dialog.subprocess, "run", return_value=MagicMock(returncode=0, stdout=f"{tmp_path}\n")) as run:
        assert native_dialog.pick_directory(str(tmp_path)) == str(tmp_path)
    assert run.call_args.args[0][:3] == ["zenity", "--file-selection", "--directory"]

    with patch.object(native_dialog.sys, "platform", "linux"), \
         patch.object(native_dialog.shutil, "which", return_value="/usr/bin/zenity"), \
         patch.object(native_dialog.subprocess, "run", return_value=MagicMock(returncode=1, stdout="")):
        assert native_dialog.pick_directory(str(tmp_path)) is None


def test_native_dialog_is_unavailable_without_zenity_or_kdialog():
    import pytest
    from unittest.mock import patch
    from wildintel_publisher.web.services import native_dialog

    with patch.object(native_dialog.sys, "platform", "linux"), patch.object(native_dialog.shutil, "which", return_value=None):
        with pytest.raises(native_dialog.NativeDialogUnavailable):
            native_dialog.pick_directory()
