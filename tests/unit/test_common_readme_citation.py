"""Unit tests for common.patch_readme_citation_url — swaps the URL at the
end of a rendered README's '## Citation' APA citation line, whatever was
there before (a repo's own default URL, an already cross-referenced DOI, or
nothing meaningful yet). Used by services.doi_populate (same-run
cross-referencing into HFH's README) and by zenodo.py/b2share.py/gbif.py's
own sync_doi_to_hfh/sync_pid_to_hfh (an out-of-band, later sync)."""
from wildintel_publisher.services.common import patch_readme_citation_url

README_TEMPLATE = """# My Dataset

Some description.

## Citation

To cite this dataset:

> Author, A. (2026). *My Dataset* (Version 1.0) [Data set]. Hugging Face. {url}

This citation was generated from the [`CITATION.cff`](CITATION.cff) file.

## License

MIT.
"""


def _write_readme(tmp_path, url: str):
    path = tmp_path / "README.md"
    path.write_text(README_TEMPLATE.format(url=url), encoding="utf-8")
    return path


def test_replaces_the_default_repo_url_with_a_doi(tmp_path):
    path = _write_readme(tmp_path, "https://huggingface.co/datasets/alice/dataset")

    changed = patch_readme_citation_url(path, "https://doi.org/10.5281/zenodo.1")

    assert changed is True
    text = path.read_text(encoding="utf-8")
    assert "> Author, A. (2026). *My Dataset* (Version 1.0) [Data set]. Hugging Face. https://doi.org/10.5281/zenodo.1" in text
    assert "huggingface.co/datasets/alice/dataset" not in text
    # Nothing else in the file should be touched.
    assert "# My Dataset" in text
    assert "## License" in text


def test_is_idempotent_when_the_url_is_already_current(tmp_path):
    path = _write_readme(tmp_path, "https://doi.org/10.5281/zenodo.1")

    changed = patch_readme_citation_url(path, "https://doi.org/10.5281/zenodo.1")

    assert changed is False


def test_can_be_called_again_later_with_a_different_doi(tmp_path):
    """Covers an HFH export re-synced a second time (e.g. GBIF's DOI shows
    up after Zenodo's was already reflected, or vice versa)."""
    path = _write_readme(tmp_path, "https://huggingface.co/datasets/alice/dataset")
    patch_readme_citation_url(path, "https://doi.org/10.5281/zenodo.1")

    changed = patch_readme_citation_url(path, "https://doi.org/10.1234/b2share.1")

    assert changed is True
    text = path.read_text(encoding="utf-8")
    assert text.count("[Data set]. Hugging Face. https://doi.org/10.1234/b2share.1") == 1
    assert "zenodo.1" not in text


def test_returns_false_and_does_not_touch_a_missing_file(tmp_path):
    missing = tmp_path / "README.md"
    changed = patch_readme_citation_url(missing, "https://doi.org/10.5281/zenodo.1")
    assert changed is False
    assert not missing.exists()


def test_returns_false_when_there_is_no_citation_section(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# My Dataset\n\nNo citation section here.\n", encoding="utf-8")

    changed = patch_readme_citation_url(path, "https://doi.org/10.5281/zenodo.1")

    assert changed is False
    assert "doi.org" not in path.read_text(encoding="utf-8")
