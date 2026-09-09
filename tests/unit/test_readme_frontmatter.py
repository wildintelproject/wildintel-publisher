"""Regression test: a dataset title containing a colon (e.g. "Iberian
CamTrap: Revision 1") used to break the YAML frontmatter HFH parses out of
README.md ("Invalid YAML in README.md: bad indentation of a mapping
entry") because pretty_name was interpolated unquoted — see
templates/common/README-{camtrapdp,yolo,software}-body.md.j2's
`pretty_name: {{ dataset_name | tojson }}`."""
import yaml

from wildintel_publisher.config import HFHSettings
from wildintel_publisher.services import hfh, product


def _extract_frontmatter(readme_text: str) -> dict:
    _, frontmatter, _ = readme_text.split("---", 2)
    return yaml.safe_load(frontmatter)


def test_hfh_readme_frontmatter_is_valid_yaml_when_title_has_a_colon(tmp_path):
    title = "Iberian CamTrap: Revision 1"

    path = hfh.write_readme(
        tmp_path, HFHSettings(), "1.0.0", product.get_adapter(product.CAMTRAPDP),
        title=title, description="A dataset.", license_id="CC-BY-NC-4.0",
        authors=[{"given_names": "Jane", "family_names": "Doe"}], date_released="2026-01-01",
    )

    frontmatter = _extract_frontmatter(path.read_text(encoding="utf-8"))
    assert frontmatter["pretty_name"] == title
    assert frontmatter["license"] == "cc-by-nc-4.0"
