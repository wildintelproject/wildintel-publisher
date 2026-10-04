"""Unit tests for the /api/health and /api/version endpoints."""
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
    return TestClient(app)


def test_health_returns_ok():
    response = _client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_expected_shape():
    response = _client().get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"current", "latest", "update_available", "release_url", "download_url", "error"}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _releases(*tags, assets=()):
    return [
        {"tag_name": tag, "html_url": f"https://github.com/x/releases/{tag}", "draft": False, "prerelease": False,
         "assets": [{"name": name, "browser_download_url": f"https://dl/{tag}/{name}"} for name in assets]}
        for tag in tags
    ]


def _check(monkeypatch, *, current="0.1.0", payload=None, error=None, system="Linux"):
    import httpx
    from wildintel_publisher.web.api.routers import health

    monkeypatch.setattr(health, "_current_version", lambda: current)
    monkeypatch.setattr(health.platform, "system", lambda: system)

    async def fake_get(self, url, **kwargs):
        if error:
            raise error
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return _client().get("/api/version").json()


def test_version_offers_the_newest_web_release_not_a_cli_one(monkeypatch):
    payload = _releases("v9.0.0", "web-v0.2.0", "web-v0.10.0", "web-v0.3.0")

    body = _check(monkeypatch, payload=payload)

    assert body["latest"] == "0.10.0"
    assert body["update_available"] is True
    assert body["error"] is None
    assert body["release_url"].endswith("web-v0.10.0")


def test_version_is_up_to_date_when_no_newer_web_release_exists(monkeypatch):
    body = _check(monkeypatch, current="0.3.0", payload=_releases("web-v0.3.0", "web-v0.2.0", "v5.0.0"))

    assert body["latest"] == "0.3.0" and body["update_available"] is False and body["error"] is None


def test_version_download_url_is_the_asset_for_this_os(monkeypatch):
    payload = _releases(
        "web-v0.2.0",
        assets=["wildintel-publisher-web-0.2.0-linux-x86_64", "wildintel-publisher-web-0.2.0-windows-x86_64.exe"],
    )

    assert _check(monkeypatch, payload=payload, system="Windows")["download_url"].endswith("windows-x86_64.exe")
    assert _check(monkeypatch, payload=payload)["download_url"].endswith("linux-x86_64")
    # no asset for this OS: fall back to the release page
    assert _check(monkeypatch, payload=payload, system="Darwin")["download_url"].endswith("web-v0.2.0")


def test_version_reports_an_error_instead_of_pretending_to_be_up_to_date(monkeypatch):
    body = _check(monkeypatch, error=RuntimeError("offline"))

    assert body["update_available"] is False
    assert "offline" in body["error"]
