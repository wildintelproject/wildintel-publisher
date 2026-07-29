"""Unit tests for services.git_source.checkout_matching_tag — against a
real, local, throwaway git repository (no network): a `git clone` of a
local path behaves identically, as far as fetch/checkout are concerned, to
one of a real remote URL."""
import subprocess
from pathlib import Path

import pytest

from wildintel_publisher.services.git_source import checkout_matching_tag


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _write_file_and_commit(repo: Path, filename: str, content: str, message: str) -> None:
    (repo / filename).write_text(content, encoding="utf-8")
    _run(["git", "add", filename], repo)
    _run(["git", "commit", "-m", message], repo)


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    """A source repo with two tags ('1.0.0' and 'v2.0.0', covering both
    naming conventions) and untagged commits after the last one — so tests
    can tell which commit actually ended up checked out."""
    repo = tmp_path / "source"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "test@test.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    _write_file_and_commit(repo, "VERSION", "1.0.0", "release 1.0.0")
    _run(["git", "tag", "1.0.0"], repo)
    _write_file_and_commit(repo, "VERSION", "2.0.0", "release 2.0.0")
    _run(["git", "tag", "v2.0.0"], repo)
    _write_file_and_commit(repo, "VERSION", "2.1.0-dev", "unreleased work past v2.0.0")

    return repo


@pytest.fixture
def cloned_repo(source_repo: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "clone"
    _run(["git", "clone", "--depth", "1", str(source_repo), str(dest)], tmp_path)
    return dest


def test_checks_out_a_tag_matching_version_exactly(cloned_repo):
    tag = checkout_matching_tag(cloned_repo, "1.0.0")

    assert tag == "1.0.0"
    assert (cloned_repo / "VERSION").read_text(encoding="utf-8") == "1.0.0"


def test_checks_out_a_tag_matching_v_prefixed_version(cloned_repo):
    tag = checkout_matching_tag(cloned_repo, "2.0.0")

    assert tag == "v2.0.0"
    assert (cloned_repo / "VERSION").read_text(encoding="utf-8") == "2.0.0"


def test_leaves_head_alone_when_no_tag_matches(cloned_repo):
    before = (cloned_repo / "VERSION").read_text(encoding="utf-8")

    tag = checkout_matching_tag(cloned_repo, "9.9.9")

    assert tag is None
    assert (cloned_repo / "VERSION").read_text(encoding="utf-8") == before
