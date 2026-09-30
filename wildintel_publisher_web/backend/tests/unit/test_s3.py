"""Unit tests for the /api/s3/* endpoints and services.s3_service.
run_s3_image_upload — s3_service's boto3 calls are mocked out (no real
network), but settings.toml reads/writes go through the real
wildintel_publisher.config machinery, isolated to a throwaway HOME by
conftest.py."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _write_fake_camtrapdp(input_dir: Path, *, file_name: str = "IMG_0001.JPG", content: bytes = b"fake-image-bytes") -> None:
    """A minimal camtrapdp product with a single media row whose filePath is
    a local relative path — download_public_images copies it in, rather than
    downloading it over the network, same "local directory" case it already
    supports."""
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / file_name).write_bytes(content)
    (input_dir / "media.csv").write_text(
        f"mediaID,fileName,filePath,filePublic\nm1,{file_name},{file_name},true\n", encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _reset_s3_config():
    """Resets settings.toml to fresh defaults before each test — several
    tests here save real S3 credentials, and without this it'd leak into
    whichever test runs next."""
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    settings = Settings()
    # Blank the product's own S3 defaults (see S3Settings), so each test
    # only sees the connection details it passes itself.
    settings.S3.endpoint_url = settings.S3.region = settings.S3.bucket = settings.S3.public_base_url = None
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)
    yield


def test_get_config_defaults_to_the_wildintel_bucket():
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    response = _client().get("/api/s3/config")
    assert response.status_code == 200
    body = response.json()
    assert body["endpoint_url"] == "https://s3.wildintel.uhu.es:9443"
    assert body["region"] == "garage"
    assert body["bucket"] == "public"
    assert body["public_base_url"] == "https://media.wildintel.uhu.es"
    assert body["has_access_key"] is False
    assert body["has_secret_key"] is False


def test_test_connection_success_saves_config():
    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        response = _client().post("/api/s3/test-connection", json={
            "bucket": "my-bucket", "access_key": "AKIA...", "secret_key": "s3cr3t", "region": "eu-west-1",
        })
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    fake_client.head_bucket.assert_called_once_with(Bucket="my-bucket")

    config_response = _client().get("/api/s3/config")
    body = config_response.json()
    assert body["bucket"] == "my-bucket"
    assert body["region"] == "eu-west-1"
    assert body["has_access_key"] is True
    assert body["has_secret_key"] is True


def test_test_connection_reports_400_when_no_credentials():
    response = _client().post("/api/s3/test-connection", json={"bucket": "my-bucket"})
    assert response.status_code == 400


def test_test_connection_maps_access_denied_to_400():
    from botocore.exceptions import ClientError
    fake_client = MagicMock()
    fake_client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "403"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "HeadBucket",
    )
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        response = _client().post("/api/s3/test-connection", json={
            "bucket": "my-bucket", "access_key": "bad", "secret_key": "bad",
        })
    assert response.status_code == 400
    assert "Access denied" in response.json()["detail"]


def test_run_s3_image_upload_downloads_uploads_and_rewrites_media_csv_with_a_content_hash_key(tmp_path):
    from services import s3_service
    from wildintel_publisher.services.common import read_csv, sha1_file

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir, content=b"fake-image-bytes")

    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        result = s3_service.run_s3_image_upload(
            input_dir=input_dir, dry_run=False, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
            region="eu-west-1", prefix="wildintel",
        )

    assert result == {"downloaded_images": 1, "uploaded": 1, "rewritten": 1}
    fake_client.upload_file.assert_called_once()
    uploaded_args = fake_client.upload_file.call_args
    assert uploaded_args.args[1] == "my-bucket"

    content_hash = sha1_file(input_dir / "IMG_0001.JPG")
    expected_key = f"wildintel/{content_hash[:2]}/{content_hash[2:4]}/{content_hash}"
    assert uploaded_args.args[2] == expected_key
    assert uploaded_args.kwargs["ExtraArgs"] == {"ContentType": "image/jpeg"}

    fieldnames, rows = read_csv(input_dir / "media.csv")
    assert rows[0]["filePath"] == f"https://my-bucket.s3.eu-west-1.amazonaws.com/{expected_key}"


def test_run_s3_image_upload_reports_error_when_no_bucket_configured(tmp_path):
    from services import s3_service

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir)
    with pytest.raises(ValueError):
        s3_service.run_s3_image_upload(
            input_dir=input_dir, dry_run=False, access_key="AKIA...", secret_key="s3cr3t",
        )


def test_run_s3_image_upload_dry_run_skips_the_real_upload_but_still_rewrites_media_csv(tmp_path):
    from services import s3_service
    from wildintel_publisher.services.common import read_csv, sha1_file

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir, content=b"fake-image-bytes")

    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        result = s3_service.run_s3_image_upload(
            input_dir=input_dir, dry_run=True, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
            region="eu-west-1", prefix="wildintel",
        )

    assert result == {"downloaded_images": 1, "uploaded": 0, "rewritten": 1}
    fake_client.upload_file.assert_not_called()

    content_hash = sha1_file(input_dir / "IMG_0001.JPG")
    expected_key = f"wildintel/{content_hash[:2]}/{content_hash[2:4]}/{content_hash}"
    fieldnames, rows = read_csv(input_dir / "media.csv")
    assert rows[0]["filePath"] == f"https://my-bucket.s3.eu-west-1.amazonaws.com/{expected_key}"


def test_run_s3_image_upload_uploads_duplicate_content_only_once(tmp_path):
    from services import s3_service

    input_dir = tmp_path / "product"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "a.jpg").write_bytes(b"same-bytes")
    (input_dir / "b.jpg").write_bytes(b"same-bytes")
    (input_dir / "media.csv").write_text(
        "mediaID,fileName,filePath,filePublic\n"
        "m1,a.jpg,a.jpg,true\n"
        "m2,b.jpg,b.jpg,true\n",
        encoding="utf-8",
    )

    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        result = s3_service.run_s3_image_upload(
            input_dir=input_dir, dry_run=False, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
        )

    assert result["uploaded"] == 1
    fake_client.upload_file.assert_called_once()


def test_run_s3_image_upload_resolves_local_images_from_media_dir(tmp_path):
    """A local Camtrap DP source: input_dir is only a working copy of the core
    files, the real images stayed at the user's original directory."""
    from services import s3_service

    input_dir = tmp_path / "working-copy"
    input_dir.mkdir()
    (input_dir / "media.csv").write_text(
        "mediaID,fileName,filePath,filePublic\nm1,IMG_0001.JPG,IMG_0001.JPG,true\n", encoding="utf-8",
    )
    media_dir = tmp_path / "original"
    media_dir.mkdir()
    (media_dir / "IMG_0001.JPG").write_bytes(b"fake-image-bytes")

    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        result = s3_service.run_s3_image_upload(
            input_dir=input_dir, media_dir=media_dir, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
        )

    assert result == {"downloaded_images": 1, "uploaded": 1, "rewritten": 1}


def test_run_s3_image_upload_reports_total_as_unique_objects_when_uploading(tmp_path):
    from services import s3_service

    input_dir = tmp_path / "product"
    input_dir.mkdir()
    (input_dir / "a.jpg").write_bytes(b"same-bytes")
    (input_dir / "b.jpg").write_bytes(b"same-bytes")
    (input_dir / "media.csv").write_text(
        "mediaID,fileName,filePath,filePublic\nm1,a.jpg,a.jpg,true\nm2,b.jpg,b.jpg,true\n", encoding="utf-8",
    )

    updates: list[dict] = []
    with patch("services.s3_service.boto3.client", return_value=MagicMock()):
        s3_service.run_s3_image_upload(
            input_dir=input_dir, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
            progress=updates.append,
        )

    assert {"stage": "uploading", "uploaded": 0, "total": 1, "log": []} in updates
    # a.jpg is PUT once; b.jpg (same bytes) only reuses its object.
    assert [u["uploaded"] for u in updates if "uploaded" in u] == [0, 1]
    assert updates[-1] == {"stage": "rewriting"}


def _poll_upload(client: TestClient, task_id: str) -> dict:
    import time
    for _ in range(100):
        body = client.get(f"/api/s3/upload/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("the S3 upload task never finished")


def test_upload_endpoint_runs_the_upload_in_the_background_and_rewrites_media_csv(tmp_path):
    from wildintel_publisher.services.common import read_csv

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir)

    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        with _client() as client:
            start = client.post("/api/s3/upload", json={
                "input_dir": str(input_dir), "bucket": "my-bucket", "access_key": "AKIA...",
                "secret_key": "s3cr3t", "region": "eu-west-1", "prefix": "wildintel",
            })
            assert start.status_code == 200, start.text
            body = _poll_upload(client, start.json()["task_id"])

    assert body["status"] == "done"
    assert body["uploaded"] == 1
    assert body["rewritten"] == 1
    fake_client.upload_file.assert_called_once()
    _, rows = read_csv(input_dir / "media.csv")
    assert rows[0]["filePath"].startswith("https://my-bucket.s3.eu-west-1.amazonaws.com/wildintel/")


def test_upload_endpoint_reports_a_missing_bucket_as_an_error_status(tmp_path):
    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir)

    with _client() as client:
        start = client.post("/api/s3/upload", json={
            "input_dir": str(input_dir), "access_key": "AKIA...", "secret_key": "s3cr3t",
        })
        assert start.status_code == 200, start.text
        body = _poll_upload(client, start.json()["task_id"])

    assert body["status"] == "error"
    assert "bucket" in body["error"].lower()


def test_upload_endpoint_rejects_a_directory_without_media_csv(tmp_path):
    response = _client().post("/api/s3/upload", json={"input_dir": str(tmp_path), "bucket": "my-bucket"})
    assert response.status_code == 400


def test_upload_status_of_an_unknown_task_is_404():
    assert _client().get("/api/s3/upload/does-not-exist").status_code == 404


def test_run_s3_image_upload_retries_a_transient_upload_error(tmp_path):
    from botocore.exceptions import EndpointConnectionError
    from services import s3_service

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir)

    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    fast_retry_settings = Settings()
    fast_retry_settings.S3.retry_wait_seconds = 0.0
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), fast_retry_settings.model_dump(mode="json"), merge=False)

    fake_client = MagicMock()
    fake_client.upload_file.side_effect = [EndpointConnectionError(endpoint_url="https://example.test"), None]
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        result = s3_service.run_s3_image_upload(
            input_dir=input_dir, dry_run=False, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
        )

    assert result["uploaded"] == 1
    assert fake_client.upload_file.call_count == 2


def test_run_s3_image_upload_dry_run_reports_each_file_with_its_key(tmp_path):
    from services import s3_service
    from wildintel_publisher.services.common import sha1_file

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir, content=b"fake-image-bytes")
    updates: list[dict] = []
    with patch("services.s3_service.boto3.client", return_value=MagicMock()):
        s3_service.run_s3_image_upload(
            input_dir=input_dir, dry_run=True, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
            prefix="wildintel", progress=updates.append,
        )

    content_hash = sha1_file(input_dir / "IMG_0001.JPG")
    expected_key = f"wildintel/{content_hash[:2]}/{content_hash[2:4]}/{content_hash}"
    final_log = [u["log"] for u in updates if "log" in u][-1]
    assert final_log == [{"file": "IMG_0001.JPG", "key": expected_key, "action": "would-upload"}]


def test_test_connection_can_skip_ssl_verification_and_saves_the_choice():
    from wildintel_publisher.config import load_settings

    with patch("services.s3_service.boto3.client", return_value=MagicMock()) as build:
        response = _client().post("/api/s3/test-connection", json={
            "bucket": "my-bucket", "access_key": "AKIA...", "secret_key": "s3cr3t", "verify_ssl": False,
        })

    assert response.status_code == 200
    assert build.call_args.kwargs["verify"] is False
    assert load_settings().S3.verify_ssl is False


def test_run_s3_image_upload_passes_verify_ssl_to_the_client(tmp_path):
    from services import s3_service

    input_dir = tmp_path / "product"
    _write_fake_camtrapdp(input_dir)
    with patch("services.s3_service.boto3.client", return_value=MagicMock()) as build:
        s3_service.run_s3_image_upload(
            input_dir=input_dir, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t", verify_ssl=False,
        )
    assert build.call_args.kwargs["verify"] is False


def test_run_s3_image_upload_skips_non_public_media(tmp_path):
    from services import s3_service

    input_dir = tmp_path / "product"
    input_dir.mkdir()
    (input_dir / "pub.jpg").write_bytes(b"public")
    (input_dir / "priv.jpg").write_bytes(b"private")
    (input_dir / "media.csv").write_text(
        "mediaID,fileName,filePath,filePublic\nm1,pub.jpg,pub.jpg,true\nm2,priv.jpg,priv.jpg,false\n", encoding="utf-8",
    )
    fake_client = MagicMock()
    with patch("services.s3_service.boto3.client", return_value=fake_client):
        result = s3_service.run_s3_image_upload(
            input_dir=input_dir, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
        )

    assert result["uploaded"] == 1
    fake_client.upload_file.assert_called_once()


def test_run_s3_image_upload_fails_clearly_when_no_image_can_be_fetched(tmp_path):
    from services import s3_service

    input_dir = tmp_path / "product"
    input_dir.mkdir()
    (input_dir / "media.csv").write_text(
        "mediaID,fileName,filePath,filePublic\nm1,a.jpg,images/a.jpg,true\n", encoding="utf-8",
    )
    with patch("services.s3_service.boto3.client", return_value=MagicMock()):
        with pytest.raises(ValueError, match="a.jpg.*local file not found"):
            s3_service.run_s3_image_upload(
                input_dir=input_dir, dry_run=True, bucket="my-bucket", access_key="AKIA...", secret_key="s3cr3t",
            )
