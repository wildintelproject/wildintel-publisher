"""Integration tests for 'hfh pipeline' (prepare -> upload -> release chained),
including its --wizard interactive mode."""
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _fake_httpx_get_image(self, url, *args, **kwargs):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = b"fake-image-bytes"
    return response


def _mocked_hfh_apis():
    """Returns the same set of patches needed for upload_to_huggingface +
    release_on_huggingface to run end-to-end without real network."""
    fake_api = MagicMock()
    fake_api.repo_info.side_effect = Exception("does not matter, repo_info result unused below")
    fake_api.dataset_info.return_value = MagicMock(private=True)
    fake_public_response = MagicMock(status_code=200)
    return [
        patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}),
        patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api),
        patch("wildintel_publisher.services.hfh.create_repo"),
        patch("wildintel_publisher.services.hfh.upload_folder"),
        patch("wildintel_publisher.services.hfh._repo_exists", return_value=False),
        patch("httpx.head", return_value=fake_public_response),
        patch("httpx.get", return_value=fake_public_response),
    ]


def test_hfh_pipeline_runs_all_three_steps(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_faketoken")
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"

    patches = _mocked_hfh_apis()
    with patch("httpx.Client.get", _fake_httpx_get_image):
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "hfh", "pipeline", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
                "--repo-id", "someuser/somedataset",
            ])
        finally:
            for p in patches:
                p.stop()

    assert result.exit_code == 0, result.output
    assert "Step 1/3: prepare" in result.output
    assert "Step 2/3: upload" in result.output
    assert "Step 3/3: release" in result.output
    assert "Pipeline completed" in result.output
    assert (output_dir / "README.md").is_file()


def test_hfh_pipeline_wizard_cancelled_at_initial_prompt_runs_nothing(tmp_path):
    result = runner.invoke(app, ["hfh", "pipeline", "--wizard"], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled" in result.output


def test_hfh_pipeline_wizard_runs_with_answered_prompts(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_faketoken")
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "hfh_out"

    # Prompts in order: continue?, input-dir, output-dir, version, timeout, repo-id, private?,
    # overwrite?, mirror-images?, then the post-wizard "Continue with these parameters?" confirm.
    answers = (
        "y\n"
        f"{input_dir}\n"
        f"{output_dir}\n"
        "1.0\n"
        "60\n"
        "someuser/somedataset\n"
        "n\n"  # private? -> no (public)
        "n\n"  # overwrite? -> no
        "y\n"  # mirror images? -> yes (mirror)
        "y\n"  # final confirm
    )

    patches = _mocked_hfh_apis()
    with patch("httpx.Client.get", _fake_httpx_get_image):
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, ["hfh", "pipeline", "--wizard"], input=answers)
        finally:
            for p in patches:
                p.stop()

    assert result.exit_code == 0, result.output
    assert "Pipeline completed" in result.output
