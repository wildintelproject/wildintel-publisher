"""Unit tests for services.software_adapter.SoftwareAdapter — proves the
ProductAdapter abstraction works for a git-cloned software application, the
same way test_yolo_adapter.py proves it for a YOLO dataset."""
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from wildintel_publisher.services import product
from wildintel_publisher.services.software_adapter import SoftwareAdapter

DEFAULT_CITATION_CFF = {
    "cff-version": "1.2.0", "title": "my-app", "version": "2.1.0",
    "authors": [{"given-names": "Jane", "family-names": "Doe"}],
}


def _write_repo(root: Path, *, citation_cff: dict | None = None, with_git_dir: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if with_git_dir:
        (root / ".git").mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    if citation_cff is not None:
        (root / "CITATION.cff").write_text(yaml.safe_dump(citation_cff), encoding="utf-8")
    return root


def _init_real_git_repo(root: Path, *, remote_url: str | None = None, citation_cff: dict | None = DEFAULT_CITATION_CFF) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    if citation_cff is not None:
        (root / "CITATION.cff").write_text(yaml.safe_dump(citation_cff), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    if remote_url:
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=root, check=True)
    return root


def test_validate_passes_when_git_dir_and_citation_cff_present(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF)
    SoftwareAdapter().validate(root)  # must not raise


def test_validate_fails_when_git_dir_missing(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF, with_git_dir=False)
    with pytest.raises(RuntimeError, match=r"\.git"):
        SoftwareAdapter().validate(root)


def test_validate_fails_when_citation_cff_missing(tmp_path):
    root = _write_repo(tmp_path / "repo")
    with pytest.raises(RuntimeError, match="CITATION.cff"):
        SoftwareAdapter().validate(root)


def test_extract_metadata_reads_citation_cff(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff={
        "cff-version": "1.2.0", "title": "my-app", "abstract": "A test app.", "version": "2.1.0",
        "license": "MIT", "authors": [{"given-names": "Jane", "family-names": "Doe", "affiliation": "Acme"}],
        "repository-code": "https://example.org/my-app",
    })

    metadata = SoftwareAdapter().extract_metadata(root)

    assert metadata["title"] == "my-app"
    assert metadata["description"] == "A test app."
    assert metadata["version"] == "2.1.0"
    assert metadata["license"] == {"id": "MIT", "name": "MIT", "url": ""}
    assert metadata["authors"] == [{"name": "Jane Doe", "affiliation": "Acme"}]
    assert metadata["homepage"] == "https://example.org/my-app"


def test_extract_metadata_reads_an_entity_author(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff={
        "cff-version": "1.2.0", "title": "my-app",
        "authors": [{"name": "Acme Corp"}],
    })

    metadata = SoftwareAdapter().extract_metadata(root)

    assert metadata["authors"] == [{"name": "Acme Corp", "affiliation": ""}]


def test_extract_metadata_falls_back_to_url_when_no_repository_code(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff={
        "cff-version": "1.2.0", "title": "my-app", "url": "https://example.org/my-app",
    })

    metadata = SoftwareAdapter().extract_metadata(root)

    assert metadata["homepage"] == "https://example.org/my-app"


def test_extract_metadata_returns_none_for_fields_citation_cff_does_not_provide(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff={"cff-version": "1.2.0"})
    metadata = SoftwareAdapter().extract_metadata(root)

    assert metadata["title"] is None
    assert metadata["description"] is None
    assert metadata["version"] is None
    assert metadata["license"] is None
    assert metadata["authors"] == []


def test_extract_metadata_falls_back_to_git_remote_for_homepage(tmp_path):
    root = _init_real_git_repo(
        tmp_path / "repo", remote_url="https://github.com/user/repo.git",
        citation_cff={"cff-version": "1.2.0", "title": "my-app"},
    )

    metadata = SoftwareAdapter().extract_metadata(root)

    assert metadata["homepage"] == "https://github.com/user/repo.git"


def test_prepare_copies_everything_except_git_dir(tmp_path):
    input_dir = _write_repo(tmp_path / "input", citation_cff=DEFAULT_CITATION_CFF)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    SoftwareAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "main.py").is_file()
    assert not (output_dir / ".git").exists()


def test_prepare_preserves_the_source_citation_cff_under_a_source_prefix(tmp_path):
    # CITATION.cff is one of product.GENERATED_FILENAMES — the pipeline
    # writes its own citation-focused version, so the repo's own copy (the
    # one extract_metadata just read from) must survive under a SOURCE_
    # prefix rather than being silently overwritten.
    input_dir = _write_repo(tmp_path / "input", citation_cff=DEFAULT_CITATION_CFF)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    SoftwareAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "SOURCE_CITATION.cff").is_file()
    assert not (output_dir / "CITATION.cff").exists()  # left free for prepare_<repo>_export's own generated one


def test_prepare_preserves_the_source_readme_under_a_source_prefix(tmp_path):
    input_dir = _write_repo(tmp_path / "input", citation_cff=DEFAULT_CITATION_CFF)
    (input_dir / "README.md").write_text("# My project\nOwn docs.", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    SoftwareAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "SOURCE_README.md").read_text(encoding="utf-8") == "# My project\nOwn docs."
    assert not (output_dir / "README.md").exists()  # left free for prepare_<repo>_export's own generated one


def test_prepare_never_copies_metadata_json_itself(tmp_path):
    # metadata.json is pipeline bookkeeping (copied into output_dir
    # separately and generically by prepare_<repo>_export's own
    # product.copy_metadata_json) — not "the product's own files" prepare()
    # is responsible for, unlike README.md/LICENSE/CITATION.cff.
    input_dir = _write_repo(tmp_path / "input", citation_cff=DEFAULT_CITATION_CFF)
    (input_dir / "metadata.json").write_text(json.dumps({"product_type": "software", "publish_history": []}), encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    SoftwareAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert not (output_dir / "metadata.json").exists()
    assert not (output_dir / "SOURCE_metadata.json").exists()


def test_generate_metadata_json_preserves_a_foreign_metadata_json(tmp_path):
    # A cloned repo could plausibly have its own metadata.json for entirely
    # unrelated reasons — generate_metadata_json must not silently destroy
    # it (see product._preserve_foreign_metadata_json).
    root = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF)
    (root / "metadata.json").write_text(json.dumps({"unrelated": "data"}), encoding="utf-8")

    product.generate_metadata_json(product.SOFTWARE, root)

    preserved = json.loads((root / "SOURCE_metadata.json").read_text(encoding="utf-8"))
    assert preserved == {"unrelated": "data"}
    on_disk = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk["product_type"] == "software"


def test_generate_metadata_json_is_idempotent_and_does_not_rename_its_own_file(tmp_path):
    root = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF)

    product.generate_metadata_json(product.SOFTWARE, root)
    product.generate_metadata_json(product.SOFTWARE, root)  # regenerate, e.g. re-picking the same directory

    assert not (root / "SOURCE_metadata.json").exists()


def test_full_pipeline_preserves_a_foreign_metadata_json_through_prepare(tmp_path):
    """End-to-end: generate_metadata_json (preserves the foreign file) then
    prepare() + copy_metadata_json (what prepare_<repo>_export actually
    does) — proves the two fixes work together without reintroducing the
    collision one level deeper, in output_dir."""
    input_dir = _write_repo(tmp_path / "input", citation_cff=DEFAULT_CITATION_CFF)
    (input_dir / "metadata.json").write_text(json.dumps({"unrelated": "data"}), encoding="utf-8")

    product.generate_metadata_json(product.SOFTWARE, input_dir)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    SoftwareAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)
    product.copy_metadata_json(input_dir, output_dir)

    assert json.loads((output_dir / "SOURCE_metadata.json").read_text(encoding="utf-8")) == {"unrelated": "data"}
    assert json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))["product_type"] == "software"


def test_extract_core_files_copies_loose_files(tmp_path):
    output_dir = _write_repo(tmp_path / "output", citation_cff=DEFAULT_CITATION_CFF)
    (output_dir / "README.md").write_text("citation readme", encoding="utf-8")
    target_dir = tmp_path / "target"

    SoftwareAdapter().extract_core_files(output_dir, target_dir)

    assert (target_dir / "main.py").is_file()
    assert not (target_dir / "README.md").exists()


def test_extract_core_files_falls_back_to_zip_when_self_contained(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    zip_path = output_dir / "software-local.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("main.py", "print('hi')")
    (output_dir / "README.md").write_text("citation readme", encoding="utf-8")
    target_dir = tmp_path / "target"

    SoftwareAdapter().extract_core_files(output_dir, target_dir)

    assert (target_dir / "main.py").read_text(encoding="utf-8") == "print('hi')"
    assert not (target_dir / "README.md").exists()


def test_link_media_to_hfh_is_a_no_op(tmp_path):
    output_dir = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF)
    assert SoftwareAdapter().link_media_to_hfh(output_dir, "alice/dataset") == 0


def test_bundle_local_zip_packs_files_but_not_generated_ones(tmp_path):
    output_dir = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF)
    (output_dir / "README.md").write_text("# hi", encoding="utf-8")
    (output_dir / "metadata.json").write_text("{}", encoding="utf-8")
    zip_path = output_dir / "software-local.zip"

    SoftwareAdapter().bundle_local_zip(output_dir, zip_path, embed_images=True)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "main.py" in names
    assert "README.md" not in names
    assert "metadata.json" not in names


def test_readme_context_is_empty(tmp_path):
    output_dir = _write_repo(tmp_path / "repo", citation_cff=DEFAULT_CITATION_CFF)
    assert SoftwareAdapter().readme_context(output_dir) == {}


def test_generate_metadata_json_writes_product_type_and_history(tmp_path):
    """End-to-end through services.product, not just the adapter directly —
    proves SoftwareAdapter is properly registered and reachable via
    product.get_adapter/generate_metadata_json."""
    root = _write_repo(tmp_path / "repo", citation_cff={
        "cff-version": "1.2.0", "title": "my-app", "abstract": "A test app.", "version": "1.0",
        "license": "MIT", "authors": [{"given-names": "Jane", "family-names": "Doe"}],
    })

    result = product.generate_metadata_json(product.SOFTWARE, root)

    assert result["product_type"] == "software"
    assert result["title"] == "my-app"
    assert result["publish_history"] == []

    on_disk = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk == result
