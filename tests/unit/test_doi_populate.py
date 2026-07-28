"""Unit tests for services.doi_populate — the generic cross-repo DOI
cross-referencing step (see the module's own docstring for the overall
design: it runs after all selected repos have uploaded/reserved whatever
DOI they can, but before any of them locks)."""
import json

import yaml

from wildintel_publisher.services.doi_populate import collect_identifiers, populate


def _write_citation(output_dir, data):
    (output_dir / "CITATION.cff").write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_record(output_dir, filename, data):
    (output_dir / filename).write_text(json.dumps(data), encoding="utf-8")


def test_collect_identifiers_reads_zenodo_and_b2share_but_skips_hfh(tmp_path):
    zenodo_dir, b2share_dir, hfh_dir = tmp_path / "zenodo", tmp_path / "b2share", tmp_path / "hfh"
    for d in (zenodo_dir, b2share_dir, hfh_dir):
        d.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_record(b2share_dir, "b2share_record.json", {"pid": "10.1234/b2share.1", "pid_kind": "doi"})
    # hfh has no record file at all — PROVIDES_DOI=False, never a source

    identifiers = collect_identifiers({"zenodo": zenodo_dir, "b2share": b2share_dir, "hfh": hfh_dir})

    assert {i.repo: i.value for i in identifiers} == {"zenodo": "10.5281/zenodo.1", "b2share": "10.1234/b2share.1"}


def test_collect_identifiers_skips_b2share_epic_pid_not_yet_a_doi(tmp_path):
    b2share_dir = tmp_path / "b2share"
    b2share_dir.mkdir()
    _write_record(b2share_dir, "b2share_record.json", {"pid": "11304/deadbeef", "pid_kind": "epic"})

    assert collect_identifiers({"b2share": b2share_dir}) == []


def test_collect_identifiers_skips_a_repo_with_no_record_yet(tmp_path):
    zenodo_dir = tmp_path / "zenodo"
    zenodo_dir.mkdir()

    assert collect_identifiers({"zenodo": zenodo_dir}) == []


def test_populate_cross_references_zenodo_and_b2share_as_alternates(tmp_path):
    zenodo_dir, b2share_dir = tmp_path / "zenodo", tmp_path / "b2share"
    zenodo_dir.mkdir()
    b2share_dir.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_record(b2share_dir, "b2share_record.json", {"pid": "10.1234/b2share.1", "pid_kind": "doi"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
    _write_citation(b2share_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1", "url": "https://doi.org/10.1234/b2share.1"})

    changed = populate({"zenodo": zenodo_dir, "b2share": b2share_dir})

    assert changed == {"zenodo": True, "b2share": True}
    zenodo_citation = yaml.safe_load((zenodo_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert zenodo_citation["doi"] == "10.5281/zenodo.1"  # own, untouched
    assert zenodo_citation["identifiers"] == [
        {"type": "doi", "value": "https://doi.org/10.1234/b2share.1", "description": "B2SHARE (EUDAT) DOI"},
    ]
    b2share_citation = yaml.safe_load((b2share_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert b2share_citation["doi"] == "10.1234/b2share.1"  # own, untouched
    assert b2share_citation["identifiers"] == [
        {"type": "doi", "value": "https://doi.org/10.5281/zenodo.1", "description": "Zenodo DOI"},
    ]
    assert (zenodo_dir / "checksums-sha256.txt").is_file()
    assert (b2share_dir / "checksums-sha256.txt").is_file()


def test_populate_gives_hfh_the_only_available_doi_as_primary_automatically(tmp_path):
    zenodo_dir, hfh_dir = tmp_path / "zenodo", tmp_path / "hfh"
    zenodo_dir.mkdir()
    hfh_dir.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
    _write_citation(hfh_dir, {"cff-version": "1.2.0", "url": "https://huggingface.co/datasets/alice/dataset"})

    changed = populate({"zenodo": zenodo_dir, "hfh": hfh_dir})

    assert changed == {"zenodo": False, "hfh": True}  # zenodo has nothing to add from hfh (no DOI)
    hfh_citation = yaml.safe_load((hfh_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert hfh_citation["doi"] == "10.5281/zenodo.1"
    assert hfh_citation["url"] == "https://doi.org/10.5281/zenodo.1"
    assert "identifiers" not in hfh_citation


def test_populate_also_patches_hfh_readme_citation_url_with_the_primary_doi(tmp_path):
    zenodo_dir, hfh_dir = tmp_path / "zenodo", tmp_path / "hfh"
    zenodo_dir.mkdir()
    hfh_dir.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
    _write_citation(hfh_dir, {"cff-version": "1.2.0", "url": "https://huggingface.co/datasets/alice/dataset"})
    (hfh_dir / "README.md").write_text(
        "## Citation\n\n> A. Author (2026). *Ds* (Version 1.0) [Data set]. Hugging Face. "
        "https://huggingface.co/datasets/alice/dataset\n",
        encoding="utf-8",
    )

    changed = populate({"zenodo": zenodo_dir, "hfh": hfh_dir})

    assert changed["hfh"] is True
    readme_text = (hfh_dir / "README.md").read_text(encoding="utf-8")
    assert "https://doi.org/10.5281/zenodo.1" in readme_text
    assert "huggingface.co/datasets/alice/dataset" not in readme_text


def test_populate_marks_hfh_changed_when_only_the_readme_needed_patching(tmp_path):
    """CITATION.cff already has this exact DOI as primary (e.g. a second
    populate() run after the README was regenerated some other way) — the
    README patch alone must still be reflected in `changed`."""
    zenodo_dir, hfh_dir = tmp_path / "zenodo", tmp_path / "hfh"
    zenodo_dir.mkdir()
    hfh_dir.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
    _write_citation(hfh_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
    (hfh_dir / "README.md").write_text(
        "## Citation\n\n> A. Author (2026). *Ds* (Version 1.0) [Data set]. Hugging Face. "
        "https://huggingface.co/datasets/alice/dataset\n",
        encoding="utf-8",
    )

    changed = populate({"zenodo": zenodo_dir, "hfh": hfh_dir})

    assert changed["hfh"] is True
    assert "https://doi.org/10.5281/zenodo.1" in (hfh_dir / "README.md").read_text(encoding="utf-8")


def test_populate_leaves_hfh_with_no_primary_when_two_candidates_and_none_chosen(tmp_path):
    zenodo_dir, b2share_dir, hfh_dir = tmp_path / "zenodo", tmp_path / "b2share", tmp_path / "hfh"
    for d in (zenodo_dir, b2share_dir, hfh_dir):
        d.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_record(b2share_dir, "b2share_record.json", {"pid": "10.1234/b2share.1", "pid_kind": "doi"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})
    _write_citation(b2share_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1"})
    _write_citation(hfh_dir, {"cff-version": "1.2.0"})

    changed = populate({"zenodo": zenodo_dir, "b2share": b2share_dir, "hfh": hfh_dir})

    assert changed["hfh"] is True
    hfh_citation = yaml.safe_load((hfh_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert "doi" not in hfh_citation
    values = {item["value"] for item in hfh_citation["identifiers"]}
    assert values == {"https://doi.org/10.5281/zenodo.1", "https://doi.org/10.1234/b2share.1"}


def test_populate_honors_an_explicit_primary_doi_source_for_hfh(tmp_path):
    zenodo_dir, b2share_dir, hfh_dir = tmp_path / "zenodo", tmp_path / "b2share", tmp_path / "hfh"
    for d in (zenodo_dir, b2share_dir, hfh_dir):
        d.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_record(b2share_dir, "b2share_record.json", {"pid": "10.1234/b2share.1", "pid_kind": "doi"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})
    _write_citation(b2share_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1"})
    _write_citation(hfh_dir, {"cff-version": "1.2.0"})

    populate({"zenodo": zenodo_dir, "b2share": b2share_dir, "hfh": hfh_dir}, primary_doi_source="b2share")

    hfh_citation = yaml.safe_load((hfh_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert hfh_citation["doi"] == "10.1234/b2share.1"
    assert hfh_citation["identifiers"] == [
        {"type": "doi", "value": "https://doi.org/10.5281/zenodo.1", "description": "Zenodo DOI"},
    ]


def test_populate_is_a_no_op_for_a_repo_with_nothing_to_add(tmp_path):
    zenodo_dir = tmp_path / "zenodo"
    zenodo_dir.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})

    changed = populate({"zenodo": zenodo_dir})

    assert changed == {"zenodo": False}
    assert not (zenodo_dir / "checksums-sha256.txt").exists()  # never touched — nothing to add


def test_populate_rerun_is_idempotent(tmp_path):
    zenodo_dir, b2share_dir = tmp_path / "zenodo", tmp_path / "b2share"
    zenodo_dir.mkdir()
    b2share_dir.mkdir()
    _write_record(zenodo_dir, "zenodo_record.json", {"doi": "10.5281/zenodo.1"})
    _write_record(b2share_dir, "b2share_record.json", {"pid": "10.1234/b2share.1", "pid_kind": "doi"})
    _write_citation(zenodo_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})
    _write_citation(b2share_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1"})

    populate({"zenodo": zenodo_dir, "b2share": b2share_dir})
    second_run_changed = populate({"zenodo": zenodo_dir, "b2share": b2share_dir})

    assert second_run_changed == {"zenodo": False, "b2share": False}
    zenodo_citation = yaml.safe_load((zenodo_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert len(zenodo_citation["identifiers"]) == 1  # not duplicated
