"""Unit tests for services.common.decompress_gzipped_tables/
_clear_datapackage_resource_compression — moved here from
services.trapper (still exercised there via 'trapper download', but now
also reused by camtrapdp_source.resolve_local_camtrapdp_source/
fetch_camtrap_dp_archive, for a Camtrap DP package whose tables are still
gzip-compressed, e.g. a Trapper export extracted by hand instead of
downloaded through this project)."""
import gzip
import json
from pathlib import Path

from wildintel_publisher.core.services.common import (
    _clear_datapackage_resource_compression,
    decompress_gzipped_tables,
)


def _write_datapackage(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "datapackage.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_decompress_gzipped_tables_removes_gz_and_strips_compression_marker(tmp_path):
    """Reproduces Trapper's real shape: resources declare "path": "deployments.csv"
    (no .gz suffix) but the physical file inside the zip is deployments.csv.gz,
    with a stray "compression": "gz" key that must be cleared once decompressed
    (otherwise frictionless/any reader tries to gunzip an already-plain CSV)."""
    gz_path = tmp_path / "deployments.csv.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"deploymentID\nd1\n")

    _write_datapackage(tmp_path, {
        "resources": [{"name": "deployments", "path": "deployments.csv", "compression": "gz"}],
    })

    decompress_gzipped_tables(tmp_path)

    assert not gz_path.exists()
    assert (tmp_path / "deployments.csv").read_bytes() == b"deploymentID\nd1\n"
    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert "compression" not in data["resources"][0]
    assert data["resources"][0]["path"] == "deployments.csv"


def test_decompress_gzipped_tables_handles_path_still_ending_in_gz(tmp_path):
    """The real-world shape this fix was written for: datapackage.json's own
    "path" already ends in ".gz" (e.g. a Trapper export extracted by hand),
    not just the "compression" marker on an otherwise-plain name — the
    resource's own path must be renamed too, or frictionless keeps looking
    for the now-deleted .gz file."""
    gz_path = tmp_path / "media.csv.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"mediaID\nm1\n")

    _write_datapackage(tmp_path, {
        "resources": [{"name": "media", "path": "media.csv.gz", "compression": "gz"}],
    })

    decompress_gzipped_tables(tmp_path)

    assert not gz_path.exists()
    assert (tmp_path / "media.csv").read_bytes() == b"mediaID\nm1\n"
    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["resources"][0]["path"] == "media.csv"
    assert "compression" not in data["resources"][0]


def test_decompress_gzipped_tables_no_op_when_nothing_compressed(tmp_path):
    original = {"resources": [{"name": "media", "path": "media.csv"}]}
    path = _write_datapackage(tmp_path, original)
    before = path.read_text(encoding="utf-8")

    decompress_gzipped_tables(tmp_path)  # no .gz files at all — must not raise or touch datapackage.json

    assert path.read_text(encoding="utf-8") == before


def test_clear_datapackage_resource_compression_no_op_when_nothing_decompressed(tmp_path):
    original = {"resources": [{"name": "media", "path": "media.csv", "compression": "gz"}]}
    path = _write_datapackage(tmp_path, original)
    before = path.read_text(encoding="utf-8")

    _clear_datapackage_resource_compression(tmp_path, set())

    assert path.read_text(encoding="utf-8") == before
