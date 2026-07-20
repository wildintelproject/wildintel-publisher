"""Unit tests for services.common.keep_only_public_media/drop_observations_of_removed_media."""
from pathlib import Path

import pytest

from wildintel_publisher.services.common import (
    drop_observations_of_removed_media,
    keep_only_public_media,
    read_csv,
)


def test_keep_only_public_media_filters_private_rows_and_returns_kept_ids(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=True)

    kept_ids = keep_only_public_media(output_dir)

    assert kept_ids == {"m1"}
    _, rows = read_csv(output_dir / "media.csv")
    assert [row["mediaID"] for row in rows] == ["m1"]


def test_keep_only_public_media_no_op_when_all_already_public(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)

    kept_ids = keep_only_public_media(output_dir)

    assert kept_ids == {"m1"}
    _, rows = read_csv(output_dir / "media.csv")
    assert len(rows) == 1


def test_keep_only_public_media_raises_when_file_missing(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        keep_only_public_media(tmp_path)


def test_keep_only_public_media_raises_when_column_missing(tmp_path):
    media_csv = tmp_path / "media.csv"
    media_csv.write_text("mediaID,fileName\nm1,a.jpg\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="filePublic"):
        keep_only_public_media(tmp_path)


def test_drop_observations_of_removed_media_removes_rows_referencing_dropped_media(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=True)
    keep_only_public_media(output_dir)

    drop_observations_of_removed_media(output_dir, {"m1"})

    _, rows = read_csv(output_dir / "observations.csv")
    assert [row["observationID"] for row in rows] == ["o1"]


def test_drop_observations_of_removed_media_keeps_rows_without_media_id(tmp_path):
    observations_csv = tmp_path / "observations.csv"
    observations_csv.write_text("observationID,mediaID\no1,\no2,m2\n", encoding="utf-8")

    drop_observations_of_removed_media(tmp_path, {"m1"})

    _, rows = read_csv(observations_csv)
    assert [row["observationID"] for row in rows] == ["o1"]


def test_drop_observations_of_removed_media_no_op_when_no_public_ids(tmp_path):
    observations_csv = tmp_path / "observations.csv"
    original = "observationID,mediaID\no1,m1\n"
    observations_csv.write_text(original, encoding="utf-8")

    drop_observations_of_removed_media(tmp_path, set())

    assert observations_csv.read_text(encoding="utf-8") == original


def test_drop_observations_of_removed_media_no_op_when_file_missing(tmp_path: Path):
    drop_observations_of_removed_media(tmp_path, {"m1"})  # must not raise
    assert not (tmp_path / "observations.csv").exists()
