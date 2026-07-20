"""Unit tests for services.camtrapdp_adapter.CamtrapDPAdapter's README
template hook — the rest of the adapter is already exercised end to end by
the CLI integration tests (test_hfh_cli.py/test_zenodo_cli.py/
test_b2share_cli.py), which assert on the rendered README's own content."""
from wildintel_publisher.services.camtrapdp_adapter import CamtrapDPAdapter


def test_readme_context_has_nothing_extra(tmp_path):
    # Camtrap DP's README fragments (templates/*/_readme-format-camtrapdp.md.j2)
    # need nothing beyond the generic context every product type gets.
    assert CamtrapDPAdapter().readme_context(tmp_path) == {}
