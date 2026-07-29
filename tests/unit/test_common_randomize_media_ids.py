"""Unit tests for services.common.randomize_media_ids — replaces any
mediaID in media.csv that isn't already a UUID with a freshly generated
one, and keeps observations.csv's own mediaID foreign-key column in sync.
Idempotent by construction: a mediaID that's already a UUID is left alone,
so a second pass never generates a different one."""
import csv
import uuid
from pathlib import Path

from wildintel_publisher.services.common import randomize_media_ids


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_replaces_non_uuid_media_ids_and_updates_observations(tmp_path):
    _write_csv(
        tmp_path / "media.csv", ["mediaID", "fileName"],
        [{"mediaID": "img001", "fileName": "img001.jpg"}, {"mediaID": "img002", "fileName": "img002.jpg"}],
    )
    _write_csv(
        tmp_path / "observations.csv", ["observationID", "mediaID"],
        [{"observationID": "obs1", "mediaID": "img001"}, {"observationID": "obs2", "mediaID": "img002"}],
    )

    replaced = randomize_media_ids(tmp_path)

    assert replaced == 2
    media_rows = _read_csv(tmp_path / "media.csv")
    obs_rows = _read_csv(tmp_path / "observations.csv")
    for row in media_rows:
        uuid.UUID(row["mediaID"])  # must not raise
    # The foreign key in observations.csv must point at the SAME new value.
    assert obs_rows[0]["mediaID"] == media_rows[0]["mediaID"]
    assert obs_rows[1]["mediaID"] == media_rows[1]["mediaID"]
    assert obs_rows[0]["mediaID"] != "img001"


def test_leaves_already_valid_uuids_untouched(tmp_path):
    existing = str(uuid.uuid4())
    _write_csv(tmp_path / "media.csv", ["mediaID", "fileName"], [{"mediaID": existing, "fileName": "a.jpg"}])

    replaced = randomize_media_ids(tmp_path)

    assert replaced == 0
    rows = _read_csv(tmp_path / "media.csv")
    assert rows[0]["mediaID"] == existing


def test_is_idempotent(tmp_path):
    _write_csv(tmp_path / "media.csv", ["mediaID", "fileName"], [{"mediaID": "img001", "fileName": "img001.jpg"}])

    randomize_media_ids(tmp_path)
    first_pass = _read_csv(tmp_path / "media.csv")
    randomize_media_ids(tmp_path)
    second_pass = _read_csv(tmp_path / "media.csv")

    assert first_pass == second_pass


def test_leaves_rows_with_no_media_id_untouched_in_observations(tmp_path):
    _write_csv(tmp_path / "media.csv", ["mediaID", "fileName"], [{"mediaID": "img001", "fileName": "img001.jpg"}])
    _write_csv(
        tmp_path / "observations.csv", ["observationID", "mediaID"],
        [{"observationID": "event-only", "mediaID": ""}, {"observationID": "obs1", "mediaID": "img001"}],
    )

    randomize_media_ids(tmp_path)

    obs_rows = _read_csv(tmp_path / "observations.csv")
    assert obs_rows[0]["mediaID"] == ""


def test_noop_when_media_csv_is_missing(tmp_path):
    assert randomize_media_ids(tmp_path) == 0


def test_noop_when_media_csv_has_no_media_id_column(tmp_path):
    _write_csv(tmp_path / "media.csv", ["fileName"], [{"fileName": "a.jpg"}])

    assert randomize_media_ids(tmp_path) == 0


def test_noop_when_observations_csv_has_no_media_id_column(tmp_path):
    _write_csv(tmp_path / "media.csv", ["mediaID", "fileName"], [{"mediaID": "img001", "fileName": "a.jpg"}])
    _write_csv(tmp_path / "observations.csv", ["observationID"], [{"observationID": "obs1"}])

    replaced = randomize_media_ids(tmp_path)

    assert replaced == 1  # media.csv itself is still updated
    obs_rows = _read_csv(tmp_path / "observations.csv")
    assert obs_rows[0] == {"observationID": "obs1"}
