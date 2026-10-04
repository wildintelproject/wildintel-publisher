"""Web backend test suite fixtures (the HOME redirect lives in tests/conftest.py)."""
import pytest


@pytest.fixture(autouse=True)
def _mock_camtrap_dp_validation():
    """Overrides tests/conftest.py's fixture of the same name: it turns the
    Camtrap DP validation into a no-op for the CLI suites, but the backend's
    tests rely on the real one failing on a package with no datapackage.json."""
    yield
