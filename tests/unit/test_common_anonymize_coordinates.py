"""Unit tests for services.common.anonymize_deployment_coordinates — rounds
deployments.csv's latitude/longitude to a fixed number of decimals, a
deterministic (not random) privacy option for sensitive camera-trap
locations: the same coordinate always rounds to the same result, so
Zenodo/B2SHARE/HFH end up publishing identical anonymized coordinates for
the same deployment, however many of them (or in what order) prepare it."""
import csv
from pathlib import Path

from wildintel_publisher.services.common import anonymize_deployment_coordinates


def _write_deployments_csv(output_dir: Path, rows: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "deployments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["deploymentID", "latitude", "longitude"])
        writer.writeheader()
        writer.writerows(rows)


def _read_deployments_csv(output_dir: Path) -> list[dict]:
    with (output_dir / "deployments.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_rounds_latitude_and_longitude_to_the_given_decimals(tmp_path):
    _write_deployments_csv(tmp_path, [{"deploymentID": "d1", "latitude": "41.123456", "longitude": "-3.987654"}])

    rounded = anonymize_deployment_coordinates(tmp_path, decimals=2)

    assert rounded == 1
    rows = _read_deployments_csv(tmp_path)
    assert rows[0]["latitude"] == "41.12"
    assert rows[0]["longitude"] == "-3.99"


def test_default_decimals_is_two(tmp_path):
    _write_deployments_csv(tmp_path, [{"deploymentID": "d1", "latitude": "41.123456", "longitude": "-3.987654"}])

    anonymize_deployment_coordinates(tmp_path)

    rows = _read_deployments_csv(tmp_path)
    assert rows[0]["latitude"] == "41.12"


def test_leaves_blank_or_unparsable_coordinates_untouched(tmp_path):
    _write_deployments_csv(
        tmp_path,
        [
            {"deploymentID": "d1", "latitude": "", "longitude": ""},
            {"deploymentID": "d2", "latitude": "not-a-number", "longitude": "-3.987654"},
            {"deploymentID": "d3", "latitude": "41.123456", "longitude": "-3.987654"},
        ],
    )

    rounded = anonymize_deployment_coordinates(tmp_path, decimals=1)

    assert rounded == 1  # only d3 has both coordinates parsable
    rows = _read_deployments_csv(tmp_path)
    assert rows[0] == {"deploymentID": "d1", "latitude": "", "longitude": ""}
    assert rows[1] == {"deploymentID": "d2", "latitude": "not-a-number", "longitude": "-3.987654"}
    assert rows[2]["latitude"] == "41.1"


def test_is_idempotent(tmp_path):
    _write_deployments_csv(tmp_path, [{"deploymentID": "d1", "latitude": "41.126", "longitude": "-3.984"}])

    anonymize_deployment_coordinates(tmp_path, decimals=2)
    first_pass = _read_deployments_csv(tmp_path)
    anonymize_deployment_coordinates(tmp_path, decimals=2)
    second_pass = _read_deployments_csv(tmp_path)

    assert first_pass == second_pass


def test_noop_when_deployments_csv_is_missing(tmp_path):
    assert anonymize_deployment_coordinates(tmp_path) == 0


def test_noop_when_deployments_csv_has_no_coordinate_columns(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    with (tmp_path / "deployments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["deploymentID", "locationName"])
        writer.writeheader()
        writer.writerow({"deploymentID": "d1", "locationName": "Loc 1"})

    assert anonymize_deployment_coordinates(tmp_path) == 0
    rows = _read_deployments_csv(tmp_path)
    assert rows[0] == {"deploymentID": "d1", "locationName": "Loc 1"}
