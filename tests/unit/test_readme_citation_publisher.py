"""Regression tests: each repo's write_readme must cite the contributor
resolved as "publisher" (see common.resolve_publisher) instead of the repo's
own name, and append a "© <year> <holder(s)>" notice for any "rightsHolder"
contributor(s) (see common.resolve_copyright_holders) — falling back to the
old hardcoded repo name when there's no publisher at all (e.g. Software,
or a YOLO dataset whose data.yaml sets none)."""
import csv

import pytest

from wildintel_publisher.config import B2ShareSettings, HFHSettings, ZenodoSettings
from wildintel_publisher.services import b2share, common, hfh, product, zenodo

AUTHORS = [{"name": "Jane Doe"}]
PUBLISHER = {"name": "WildINTEL", "website": "https://wildintel.eu/", "email": "wildintelproject@gmail.com"}
COPYRIGHT_HOLDERS = ["Institute of Nature Conservation PAS"]


@pytest.fixture(autouse=True)
def _media_csv(tmp_path):
    # readme_context (see CamtrapDPAdapter.readme_context) reads media.csv
    # for its Hugging Face discovery fields, regardless of which repo's
    # write_readme is under test here.
    with (tmp_path / common.MEDIA_CSV_FILENAME).open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=["mediaID"]).writeheader()


def _citation_line(readme_text: str) -> str:
    for line in readme_text.splitlines():
        if line.startswith("> ") and "[Data set]" in line:
            return line
    raise AssertionError(f"No APA citation line found in:\n{readme_text}")


def test_hfh_readme_cites_the_contributor_publisher_and_copyright_holders(tmp_path):
    path = hfh.write_readme(
        tmp_path, HFHSettings(), "1.0.0", product.get_adapter(product.CAMTRAPDP),
        title="T", description="D", license_id="CC-BY-NC-4.0",
        authors=AUTHORS, date_released="2026-01-01",
        publisher=PUBLISHER, copyright_holders=COPYRIGHT_HOLDERS,
    )
    line = _citation_line(path.read_text(encoding="utf-8"))
    assert "[Data set]. WildINTEL." in line
    assert "Hugging Face" not in line
    assert line.endswith("© 2026 Institute of Nature Conservation PAS")


def test_hfh_readme_falls_back_to_hugging_face_when_no_contributor_publisher(tmp_path):
    path = hfh.write_readme(
        tmp_path, HFHSettings(), "1.0.0", product.get_adapter(product.CAMTRAPDP),
        title="T", description="D", license_id="CC-BY-NC-4.0",
        authors=AUTHORS, date_released="2026-01-01",
    )
    line = _citation_line(path.read_text(encoding="utf-8"))
    assert "[Data set]. Hugging Face." in line
    assert "©" not in line


def test_zenodo_readme_cites_the_contributor_publisher_and_copyright_holders(tmp_path):
    path = zenodo.write_readme(
        tmp_path, ZenodoSettings(), "1.0.0", product.get_adapter(product.CAMTRAPDP), self_contained=True,
        title="T", description="D", license_id="CC-BY-NC-4.0",
        authors=AUTHORS, date_released="2026-01-01", hfh_repo_id=None,
        publisher=PUBLISHER, copyright_holders=COPYRIGHT_HOLDERS,
    )
    line = _citation_line(path.read_text(encoding="utf-8"))
    assert "[Data set]. WildINTEL." in line
    assert "Zenodo." not in line
    assert line.endswith("© 2026 Institute of Nature Conservation PAS")


def test_zenodo_readme_falls_back_to_zenodo_when_no_contributor_publisher(tmp_path):
    path = zenodo.write_readme(
        tmp_path, ZenodoSettings(), "1.0.0", product.get_adapter(product.CAMTRAPDP), self_contained=True,
        title="T", description="D", license_id="CC-BY-NC-4.0",
        authors=AUTHORS, date_released="2026-01-01", hfh_repo_id=None,
    )
    line = _citation_line(path.read_text(encoding="utf-8"))
    assert "[Data set]. Zenodo." in line
    assert "©" not in line


def test_b2share_readme_cites_the_contributor_publisher_and_copyright_holders(tmp_path):
    path = b2share.write_readme(
        tmp_path, "1.0.0", product.get_adapter(product.CAMTRAPDP), self_contained=True,
        title="T", description="D", license_id="CC-BY-NC-4.0",
        authors=AUTHORS, date_released="2026-01-01", hfh_repo_id=None,
        publisher=PUBLISHER, copyright_holders=COPYRIGHT_HOLDERS,
    )
    line = _citation_line(path.read_text(encoding="utf-8"))
    assert "[Data set]. WildINTEL." in line
    # PLACEHOLDER_CITATION_URL (self_contained=True with no DOI yet) itself
    # mentions "B2SHARE" — only the publisher FIELD must not, not the line
    # as a whole.
    assert "[Data set]. B2SHARE (EUDAT)." not in line
    assert line.endswith("© 2026 Institute of Nature Conservation PAS")


def test_b2share_readme_falls_back_to_b2share_when_no_contributor_publisher(tmp_path):
    path = b2share.write_readme(
        tmp_path, "1.0.0", product.get_adapter(product.CAMTRAPDP), self_contained=True,
        title="T", description="D", license_id="CC-BY-NC-4.0",
        authors=AUTHORS, date_released="2026-01-01", hfh_repo_id=None,
    )
    line = _citation_line(path.read_text(encoding="utf-8"))
    assert "[Data set]. B2SHARE (EUDAT)." in line
    assert "©" not in line
