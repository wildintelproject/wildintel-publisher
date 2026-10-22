"""The reports of validations and publications: report_service, its router, and where they are kept."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wildintel_publisher.core import config
from wildintel_publisher.core.services import report_service

_real_reports_dir = config.reports_dir  # the autouse fixture below replaces config's


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def reports_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "reports"
    monkeypatch.setattr(config, "reports_dir", lambda settings=None: root)
    return root


def test_the_reports_go_to_the_documents_folder_unless_the_settings_say_otherwise():
    settings = config.Settings()
    assert _real_reports_dir(settings) == config.get_app_documents_dir() / "reports"
    settings.GENERAL.reports_dir = "/data/my-reports"
    assert _real_reports_dir(settings) == Path("/data/my-reports")


def test_a_reports_folder_must_be_absolute_and_blank_means_the_default():
    assert config.GeneralSettings(reports_dir="  ").reports_dir is None
    with pytest.raises(ValueError):
        config.GeneralSettings(reports_dir="relative/folder")


def test_a_validation_report_says_whether_it_passed_and_lists_the_warnings(tmp_path):
    ok = report_service.validation_report(tmp_path / "ds", "yolo", error=None, warnings=["no test images"])
    assert ok["totals"] == {"entries": 2, "ok": 1, "failed": 0, "warnings": 1}
    bad = report_service.validation_report(tmp_path / "ds", "yolo", error="no images/")
    assert bad["totals"]["failed"] == 1 and bad["entries"][0]["message"] == "no images/"


def test_a_publication_report_has_an_entry_per_repository():
    repos = {
        "hfh": {"status": "done", "repo_url": "https://huggingface.co/datasets/x/y", "doi": None},
        "zenodo": {"status": "done", "doi": "10.5281/zenodo.1"},
        "gbif": {"status": "error", "error": "boom"},
    }
    report = report_service.publication_report("Publication of X", repos, source_dir="/d", product_type="yolo", dry_run=False)
    by = {(e["identifier"], e["check"]): e for e in report["entries"]}
    assert by[("hfh", "publication")]["message"] == "Published at https://huggingface.co/datasets/x/y."
    assert by[("zenodo", "doi")]["message"] == "10.5281/zenodo.1"
    assert by[("gbif", "publication")]["status"] == "failed" and by[("gbif", "publication")]["message"] == "boom"
    assert report["totals"]["failed"] == 1


def test_saving_listing_reading_and_deleting(reports_root):
    first = report_service.validation_report(Path("/x/ds"), "yolo", error=None)
    report_id = report_service.save(first)

    assert (reports_root / f"{report_id}.json").is_file()
    assert report_service.read(report_id)["id"] == report_id
    assert [r["id"] for r in report_service.list_reports()] == [report_id]
    assert "entries" not in report_service.list_reports()[0]

    report_service.delete(report_id)
    assert report_service.list_reports() == []
    with pytest.raises(report_service.ReportError):
        report_service.read(report_id)


def test_a_report_id_is_never_a_path():
    with pytest.raises(report_service.ReportError):
        report_service.read("../../etc/passwd")


def test_the_api_lists_downloads_and_deletes(reports_root):
    report_id = report_service.save(report_service.validation_report(Path("/x/ds"), "yolo", error="bad"))
    client = _client()

    assert [r["id"] for r in client.get("/api/reports").json()] == [report_id]
    assert client.get(f"/api/reports/{report_id}").json()["totals"]["failed"] == 1
    csv_response = client.get(f"/api/reports/{report_id}/download?format=csv")
    assert csv_response.text.splitlines()[0] == "identifier,check,status,message"
    assert client.get(f"/api/reports/{report_id}/download?format=xml").status_code == 400
    assert client.delete(f"/api/reports/{report_id}").json() == {"status": "ok"}
    assert client.get(f"/api/reports/{report_id}").status_code == 404


def test_the_settings_say_where_the_reports_go_by_default():
    body = _client().get("/api/settings").json()
    assert body["GENERAL"]["default_reports_dir"] == str(config.default_reports_dir())
    assert body["GENERAL"]["reports_dir"] is None


def test_a_finished_publication_leaves_its_report(tmp_path):
    from wildintel_publisher.web.services import publish_orchestrator

    task = {
        "status": "done", "error": None,
        "repos": {"hfh": {"status": "done", "repo_url": "https://huggingface.co/datasets/x/y", "doi": None}},
    }
    publish_orchestrator._keep_publication_report(task, input_dir=tmp_path / "my-dataset", dry_run=True)

    [report] = report_service.list_reports()
    assert report["kind"] == "publication" and report["title"] == "Publication of my-dataset"
    assert report_service.read(report["id"])["parameters"] == {"dry_run": True, "repositories": ["hfh"]}


def test_a_report_that_cannot_be_kept_never_breaks_the_publication(tmp_path, monkeypatch):
    from wildintel_publisher.web.services import publish_orchestrator

    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setattr(config, "reports_dir", lambda settings=None: blocker / "reports")

    publish_orchestrator._keep_publication_report({"status": "error", "error": "x", "repos": {}}, input_dir=tmp_path, dry_run=False)


def test_running_the_deep_checks_keeps_a_validation_report_with_the_failing_images(tmp_path):
    import yaml

    root = tmp_path / "yolo"
    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True)
        (root / "images" / split / "a.jpg").write_bytes(b"x")
    (root / "labels" / "train").mkdir(parents=True)
    (root / "labels" / "train" / "a.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    (root / "data.yaml").write_text(yaml.safe_dump({"train": "images/train", "val": "images/val", "names": ["cat"]}), encoding="utf-8")
    client = _client()

    structure = client.post("/api/yolo/structure-check", json={"input_dir": str(root)}).json()
    assert structure["ok"] and len(structure["checks"]) == 5

    body = client.post("/api/yolo/deep-checks", json={"input_dir": str(root), "checks": ["image_labels"]}).json()
    assert body["results"][0]["failures"] == ["images/val/a.jpg"]
    report = report_service.read(body["report_id"])
    assert report["kind"] == "validation" and report["totals"]["failed"] == 1
    assert {"identifier": "images/val/a.jpg", "check": "image_labels", "status": "failed", "message": "No label file."} in report["entries"]
    assert report["checks"]["image_labels"]["label"] == "Every image has a label file"

    assert client.post("/api/yolo/deep-checks", json={"input_dir": str(root), "checks": ["nope"]}).status_code == 400
