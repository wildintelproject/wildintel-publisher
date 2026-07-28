"""Integration tests for 'hfh prepare/upload/release' — image downloads and
HuggingFace Hub API calls are mocked out (no real network)."""
import csv
import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import httpx
import yaml
from huggingface_hub import GitRefInfo, GitRefs
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _fake_httpx_get(self, url, *args, **kwargs):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = b"fake-image-bytes"
    return response


def test_hfh_prepare_produces_full_export(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=True)
    output_dir = tmp_path / "hfh_out"

    with patch("httpx.Client.get", _fake_httpx_get):
        result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    for filename in ("README.md", "CITATION.cff", "LICENSE", "checksums-sha256.txt", "datapackage.json", "camtrapdp-local.zip"):
        assert (output_dir / filename).is_file(), filename
    assert (output_dir / "images" / "m1.jpg").read_bytes() == b"fake-image-bytes"

    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [row["mediaID"] for row in rows] == ["m1"]  # private media filtered out

    with (output_dir / "observations.csv").open(newline="", encoding="utf-8") as f:
        obs_rows = list(csv.DictReader(f))
    assert [row["observationID"] for row in obs_rows] == ["o1"]


def test_hfh_prepare_writes_a_placeholder_repo_id_with_no_citation_url_yet(camtrapdp_dir, tmp_path):
    """The real repo_id isn't known until 'hfh upload' — see
    hfh.py's PLACEHOLDER_REPO_ID/_patch_readme_with_repo_id/
    _patch_citation_with_repo_id."""
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"

    result = runner.invoke(app, [
        "hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--link-images",
    ])

    assert result.exit_code == 0, result.output
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "REPLACE_WITH_HF_USER/dataset" in readme

    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert "url" not in citation
    assert "repository-artifact" not in citation


def test_hfh_prepare_does_not_copy_trappers_original_zip(camtrapdp_dir, tmp_path):
    """The raw camtrapdp.zip that 'trapper download' leaves alongside the
    package (still containing gzip-compressed CSVs, and unfiltered private
    media) must never be copied into the HFH export — only the 4 core
    files are copied (see CORE_CAMTRAPDP_FILES), same as 'zenodo prepare'."""
    input_dir = camtrapdp_dir("trapper_out", include_private_media=True)
    (input_dir / "camtrapdp.zip").write_bytes(b"fake-trapper-zip-bytes")
    output_dir = tmp_path / "hfh_out"

    with patch("httpx.Client.get", _fake_httpx_get):
        result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "camtrapdp.zip").exists()
    assert (output_dir / "camtrapdp-local.zip").is_file()


def test_hfh_prepare_local_zip_csvs_are_uncompressed(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"

    with patch("httpx.Client.get", _fake_httpx_get):
        result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(output_dir / "camtrapdp-local.zip") as zf:
        infos = zf.infolist()
        assert infos  # sanity: the zip isn't empty
        for info in infos:
            assert info.compress_type == zipfile.ZIP_STORED, f"{info.filename} is compressed"


def test_hfh_prepare_link_mode_skips_images_and_local_zip(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"

    result = runner.invoke(app, [
        "hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--link-images",
    ])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "images").exists()
    assert not (output_dir / "camtrapdp-local.zip").exists()
    for filename in ("README.md", "CITATION.cff", "LICENSE", "checksums-sha256.txt", "datapackage.json"):
        assert (output_dir / filename).is_file(), filename

    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["filePath"] == "https://trapper.example/m1.jpg?rt=tok1"  # untouched


def test_hfh_prepare_refuses_non_empty_output_dir_without_overwrite(camtrapdp_dir, tmp_path, caplog):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 1
    # commands/hfh.py reports the failure via logging.error, not console.print/stdout —
    # not visible in CliRunner's captured result.output, so check pytest's own log capture.
    assert "already exists and is not empty" in caplog.text
    assert (output_dir / "leftover.txt").is_file()  # untouched


def test_hfh_prepare_reuses_non_empty_output_dir_with_overwrite(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    with patch("httpx.Client.get", _fake_httpx_get):
        result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--overwrite"])

    assert result.exit_code == 0, result.output
    assert (output_dir / "README.md").is_file()


def test_hfh_prepare_fails_when_input_dir_missing(tmp_path):
    result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(tmp_path / "does-not-exist"), "--output-dir", str(tmp_path / "out")])
    assert result.exit_code == 1


def test_hfh_prepare_fails_when_title_missing(tmp_path):
    input_dir = tmp_path / "bad_input"
    input_dir.mkdir()
    (input_dir / "datapackage.json").write_text("{}", encoding="utf-8")
    (input_dir / "media.csv").write_text("mediaID,filePublic\nm1,true\n", encoding="utf-8")

    result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(tmp_path / "out")])

    assert result.exit_code == 1


def _prepared_export(camtrapdp_dir, tmp_path, *, link_images: bool = False):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"
    args = ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)]
    if link_images:
        args.append("--link-images")
    with patch("httpx.Client.get", _fake_httpx_get):
        result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return output_dir


def test_hfh_upload_requires_repo_id(camtrapdp_dir, tmp_path):
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)
    result = runner.invoke(app, ["hfh", "upload", "--output-dir", str(output_dir)], env={"HF_TOKEN": ""})
    assert result.exit_code == 1
    assert "Missing the HuggingFace Hub repository" in result.output or "HuggingFace Hub token" in result.output


def test_hfh_upload_rewrites_media_csv_and_calls_upload_folder(camtrapdp_dir, tmp_path):
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)

    fake_response = httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co"))
    fake_api = MagicMock()
    fake_api.repo_info.side_effect = RepositoryNotFoundError("not found", response=fake_response)  # doesn't exist yet -> create it

    with patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}), \
         patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("wildintel_publisher.services.hfh.create_repo") as mock_create_repo, \
         patch("wildintel_publisher.services.hfh.upload_folder") as mock_upload_folder:
        result = runner.invoke(app, [
            "hfh", "upload", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 0, result.output
    mock_create_repo.assert_called_once()
    mock_upload_folder.assert_called_once()
    fake_api.create_tag.assert_not_called()  # tagging moved to 'hfh release' — see the tests below

    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["filePath"] == "https://huggingface.co/datasets/someuser/somedataset/resolve/main/images/m1.jpg"

    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["homepage"] == "https://huggingface.co/datasets/someuser/somedataset"

    # README.md/CITATION.cff get the real repo_id/url patched in — no more
    # placeholder (see hfh.py's _patch_readme_with_repo_id/_patch_citation_with_repo_id).
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "someuser/somedataset" in readme
    assert "REPLACE_WITH_HF_USER" not in readme

    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["url"] == "https://huggingface.co/datasets/someuser/somedataset"
    assert "repository-artifact" not in citation


def test_hfh_upload_writes_a_gbif_archive_with_real_media_urls(camtrapdp_dir, tmp_path):
    """camtrapdp-remote.zip (unlike camtrapdp-local.zip, whose media.csv uses
    paths relative to a sibling images/ folder) must carry the real,
    permanent Hugging Face Hub URLs — the whole point is that GBIF's
    CAMTRAP_DP crawler can resolve every image after extracting it in
    isolation, with nothing else needed alongside it."""
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)

    fake_response = httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co"))
    fake_api = MagicMock()
    fake_api.repo_info.side_effect = RepositoryNotFoundError("not found", response=fake_response)

    with patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}), \
         patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("wildintel_publisher.services.hfh.create_repo"), \
         patch("wildintel_publisher.services.hfh.upload_folder"):
        result = runner.invoke(app, [
            "hfh", "upload", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 0, result.output
    assert (output_dir / "camtrapdp-remote.zip").is_file()

    with zipfile.ZipFile(output_dir / "camtrapdp-remote.zip") as zf:
        names = set(zf.namelist())
        # Nested inside a single top-level folder, not loose at the zip's own
        # root — GBIF's own CAMTRAP_DP crawler requires exactly one root
        # directory once it unpacks the archive (see write_remote_zip).
        assert names == {
            "camtrapdp-remote/datapackage.json", "camtrapdp-remote/deployments.csv",
            "camtrapdp-remote/media.csv", "camtrapdp-remote/observations.csv",
        }
        with zf.open("camtrapdp-remote/media.csv") as f:
            rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
    assert rows[0]["filePath"] == "https://huggingface.co/datasets/someuser/somedataset/resolve/main/images/m1.jpg"

    # camtrapdp-local.zip keeps its own, deliberately different, relative-path
    # media.csv — the two archives serve different purposes (see docs/publishing-gbif.md).
    with zipfile.ZipFile(output_dir / "camtrapdp-local.zip") as zf:
        with zf.open("media.csv") as f:
            local_rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
    assert local_rows[0]["filePath"] == "images/m1.jpg"


def test_hfh_upload_link_mode_writes_no_gbif_archive(camtrapdp_dir, tmp_path):
    """Link mode never hosts media on this HFH repo (see
    test_hfh_upload_link_mode_does_not_touch_media_csv) — there's no real
    URL to package for GBIF, so camtrapdp-remote.zip isn't generated at all."""
    output_dir = _prepared_export(camtrapdp_dir, tmp_path, link_images=True)

    fake_response = httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co"))
    fake_api = MagicMock()
    fake_api.repo_info.side_effect = RepositoryNotFoundError("not found", response=fake_response)

    with patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}), \
         patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("wildintel_publisher.services.hfh.create_repo"), \
         patch("wildintel_publisher.services.hfh.upload_folder"):
        result = runner.invoke(app, [
            "hfh", "upload", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset", "--link-images",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 0, result.output
    assert not (output_dir / "camtrapdp-remote.zip").exists()


def test_hfh_upload_link_mode_does_not_touch_media_csv(camtrapdp_dir, tmp_path):
    output_dir = _prepared_export(camtrapdp_dir, tmp_path, link_images=True)

    fake_response = httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co"))
    fake_api = MagicMock()
    fake_api.repo_info.side_effect = RepositoryNotFoundError("not found", response=fake_response)

    with patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}), \
         patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("wildintel_publisher.services.hfh.create_repo") as mock_create_repo, \
         patch("wildintel_publisher.services.hfh.upload_folder") as mock_upload_folder:
        result = runner.invoke(app, [
            "hfh", "upload", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset", "--link-images",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 0, result.output
    mock_create_repo.assert_called_once()
    mock_upload_folder.assert_called_once()
    fake_api.create_tag.assert_not_called()  # tagging moved to 'hfh release'

    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["filePath"] == "https://trapper.example/m1.jpg?rt=tok1"  # untouched

    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "homepage" not in metadata or not metadata["homepage"]  # link mode: the media isn't hosted on this HFH repo

    # Unlike homepage (mirror-only), the repo_id/url patch always happens —
    # this repo genuinely is where the record lives, link mode or not.
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "someuser/somedataset" in readme

    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["url"] == "https://huggingface.co/datasets/someuser/somedataset"
    assert "repository-artifact" not in citation


def test_hfh_upload_refuses_to_republish_a_version_already_tagged(camtrapdp_dir, tmp_path):
    """The fixture's camtrapdp always has version '1.0' (see conftest.py) —
    if that's already a tag on the target repo, 'hfh upload' must refuse
    rather than silently overwriting/re-tagging it."""
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)

    fake_api = MagicMock()
    fake_api.repo_info.return_value = MagicMock()  # repo already exists
    fake_api.list_repo_refs.return_value = GitRefs(
        branches=[], converts=[], tags=[GitRefInfo(name="1.0", ref="refs/tags/1.0", target_commit="abc123")],
    )

    with patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}), \
         patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("wildintel_publisher.services.hfh.upload_folder") as mock_upload_folder:
        result = runner.invoke(app, [
            "hfh", "upload", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 1
    mock_upload_folder.assert_not_called()  # fails fast, before spending any upload bandwidth


def test_hfh_release_tags_the_version_and_makes_repo_public_and_verifies_accessibility(camtrapdp_dir, tmp_path):
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)

    fake_info = MagicMock(private=True)
    fake_api = MagicMock()
    fake_api.dataset_info.return_value = fake_info

    fake_response = MagicMock(status_code=200)

    with patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("httpx.head", return_value=fake_response), \
         patch("httpx.get", return_value=fake_response):
        result = runner.invoke(app, [
            "hfh", "release", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 0, result.output
    fake_api.create_tag.assert_called_once_with(repo_id="someuser/somedataset", tag="1.0", repo_type="dataset", token="hf_faketoken")
    fake_api.update_repo_settings.assert_called_once()
    assert "publicly accessible" in result.output


def test_hfh_release_maps_a_409_from_create_tag_to_a_clear_error(camtrapdp_dir, tmp_path):
    """Defense in depth: even if tag_exists's own check somehow missed a
    conflict (e.g. a concurrent publish), a 409 from the actual create_tag
    call must still be reported clearly, not as a generic failure."""
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)

    conflict_response = httpx.Response(409, request=httpx.Request("POST", "https://huggingface.co"))
    fake_api = MagicMock()
    fake_api.create_tag.side_effect = HfHubHTTPError("409 Conflict", response=conflict_response)

    with patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api):
        result = runner.invoke(app, [
            "hfh", "release", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 1


def test_hfh_release_dry_run_does_not_tag_or_change_visibility(camtrapdp_dir, tmp_path):
    output_dir = _prepared_export(camtrapdp_dir, tmp_path)

    fake_info = MagicMock(private=True)
    fake_api = MagicMock()
    fake_api.dataset_info.return_value = fake_info
    fake_response = MagicMock(status_code=404)

    with patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("httpx.head", return_value=fake_response), \
         patch("httpx.get", return_value=fake_response):
        result = runner.invoke(app, [
            "hfh", "release", "--output-dir", str(output_dir), "--repo-id", "someuser/somedataset", "--dry-run",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert result.exit_code == 0, result.output
    fake_api.create_tag.assert_not_called()
    fake_api.update_repo_settings.assert_not_called()
