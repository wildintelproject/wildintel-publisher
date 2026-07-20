"""Unit tests for services.common.ensure_output_dir — the guard shared by
'hfh prepare'/'zenodo prepare'/'b2share prepare' that refuses to silently
reuse a non-empty --output-dir unless --overwrite is passed."""
import pytest

from wildintel_publisher.services.common import ensure_output_dir


def test_ensure_output_dir_creates_missing_directory(tmp_path):
    output_dir = tmp_path / "new_dir"
    ensure_output_dir(output_dir, overwrite=False)
    assert output_dir.is_dir()


def test_ensure_output_dir_allows_reusing_an_empty_existing_directory(tmp_path):
    output_dir = tmp_path / "empty_dir"
    output_dir.mkdir()
    ensure_output_dir(output_dir, overwrite=False)  # must not raise
    assert output_dir.is_dir()


def test_ensure_output_dir_raises_when_non_empty_and_no_overwrite(tmp_path):
    output_dir = tmp_path / "existing_dir"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    with pytest.raises(RuntimeError, match="already exists and is not empty"):
        ensure_output_dir(output_dir, overwrite=False)


def test_ensure_output_dir_allows_non_empty_when_overwrite_true(tmp_path):
    output_dir = tmp_path / "existing_dir"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    ensure_output_dir(output_dir, overwrite=True)  # must not raise

    assert (output_dir / "leftover.txt").is_file()  # does not wipe the directory itself
