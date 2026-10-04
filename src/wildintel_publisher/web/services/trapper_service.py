"""Trapper integration for the web backend — thin wrapper around trapper_client.

No server-side session is kept: every call builds its own TrapperClient from
fresh credentials, matching wildintel_publisher.core.services.trapper's
own stateless design (see ../../../../wildintel_publisher/services/trapper.py) —
credentials are never stored in memory beyond a single request.

Connection defaults (base_url/user_name/user_password) are read from and
written to the SAME settings.toml the CLI's own 'trapper config' commands
use — wildintel_publisher is a local path dependency (see
pyproject.toml) precisely so this backend and the CLI share one
configuration file instead of each keeping their own copy.

The actual package download reuses wildintel_publisher.core.services.trapper.
fetch_camtrapdp_package() directly (same function 'trapper download' calls in
the CLI) — it's synchronous and can take a while on large projects, so it
runs as a background asyncio task polled by task_id, the same pattern
wildintel-trapverify's own trapper_service.py uses for its equivalent
long-running generate-and-download call.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from dynaconf import loaders
from trapper_client import TrapperClient
from wildintel_publisher.core.config import DEFAULT_CONFIG_FILE, load_settings
from wildintel_publisher.core.services.trapper import fetch_camtrapdp_package

from wildintel_publisher.web.services import session_store

# Generous enough to avoid pagination round-trips for typical result sizes,
# without trying to be "unlimited" (TrapperComponent.where() pages lazily
# anyway, so a huge page_size here is just a batch-size hint).
LIST_PAGE_SIZE = 200

# Matches commands/trapper.py's own DEFAULT_VERSION in the CLI — not stored
# in settings.toml, just a shared literal default.
DEFAULT_VERSION = "1.0"

# Simple in-memory task store {task_id: {status, path, error}} — one process,
# no persistence across restarts, same trade-off wildintel-trapverify makes
# for its own background download task.
_download_tasks: dict[str, dict[str, Any]] = {}


def _client(url: str, username: str, password: str) -> TrapperClient:
    return TrapperClient(base_url=url.rstrip("/"), user_name=username, user_password=password)


def get_connection_defaults() -> dict:
    """Current TRAPPER connection defaults from settings.toml.

    The password itself is never returned (same principle as the CLI's own
    'config show', which masks secret fields) — only whether one is saved,
    so the frontend can decide whether to let the user leave the password
    field blank and reuse the stored one.
    """
    settings = load_settings()
    return {
        "base_url": settings.TRAPPER.base_url,
        "user_name": settings.TRAPPER.user_name,
        "has_password": bool(settings.TRAPPER.user_password),
    }


def resolve_credentials(url: str | None, username: str | None, password: str | None) -> tuple[str, str, str]:
    """Fills in whatever wasn't given from settings.toml's TRAPPER section —
    mirrors commands/trapper.py's own `trapper_user or TRAPPER_DEFAULTS.user_name`
    fallback, needed here too since the frontend may submit blank fields on
    purpose to reuse what's already saved.

    Raises:
        ValueError: if a piece is still missing after the fallback (with a
        message identifying which one(s), for the router to turn into a 400).
    """
    settings = load_settings()
    resolved_url = url or settings.TRAPPER.base_url
    resolved_username = username or settings.TRAPPER.user_name
    resolved_password = password or settings.TRAPPER.user_password

    missing = [
        name for name, value in (("url", resolved_url), ("username", resolved_username), ("password", resolved_password))
        if not value
    ]
    if missing:
        raise ValueError(f"Missing Trapper {'/'.join(missing)} — provide it, or save it in the configuration first.")

    return resolved_url, resolved_username, resolved_password


def save_credentials(url: str, username: str, password: str) -> None:
    """Persists base_url/user_name/user_password into the shared settings.toml —
    called once a connection has been verified (see the /test-connection
    route), so a working connection doesn't need to be retyped next time.

    Rewrites the FULL Settings object, not just the TRAPPER section — writing
    only a partial dict would wipe out HFH/ZENODO/B2SHARE (same footgun the
    CLI's own config_commands.py._save() already guards against)."""
    settings = load_settings()
    settings.TRAPPER.base_url = url
    settings.TRAPPER.user_name = username
    settings.TRAPPER.user_password = password
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)


def test_connection(url: str, username: str, password: str) -> dict:
    """Verifies credentials by requesting a single page of research projects.

    Returns:
        {"ok": True, "research_projects_count": N}

    Raises:
        trapper_client.err.UnauthorizedError/ForbiddenError/etc, or a raw
        httpx.ConnectError/TimeoutException — left for the router to map to
        the appropriate HTTP status.
    """
    client = _client(url, username, password)
    result = client.research_projects.get(page=1, page_size=1)
    return {"ok": True, "research_projects_count": result.pagination.count}


def list_research_projects(url: str, username: str, password: str) -> list[dict]:
    """Research projects accessible to the authenticated user."""
    client = _client(url, username, password)
    return [
        {"pk": p.pk, "name": p.name, "acronym": p.acronym}
        for p in client.research_projects.where(page_size=LIST_PAGE_SIZE)
    ]


def list_classification_projects(url: str, username: str, password: str, research_project_pk: int) -> list[dict]:
    """Classification projects belonging to `research_project_pk`."""
    client = _client(url, username, password)
    return [
        {"pk": p.pk, "name": p.name, "is_active": p.is_active}
        for p in client.classification_projects.where(research_project=research_project_pk, page_size=LIST_PAGE_SIZE)
    ]


def list_deployments(url: str, username: str, password: str, classification_project_pk: int) -> list[dict]:
    """Deployments belonging to `classification_project_pk`.

    `deployment_id` is the human-readable string identifier (e.g.
    "r0007-dona_0018") — the one wildintel_publisher's own
    'trapper download --deployment-id' expects, as opposed to `pk` (the
    numeric primary key, only used here as a stable React key/select value).
    """
    client = _client(url, username, password)
    return [
        {"pk": d.pk, "deployment_id": d.deployment_id, "location_id": d.location_id}
        for d in client.deployments.where(classification_project=classification_project_pk, page_size=LIST_PAGE_SIZE)
    ]


def _fetch_params(*, url: str, project_id: int, deployment_id: str, clear_cache: bool, include_events: bool) -> dict:
    """The non-secret subset of a Trapper fetch request — persisted as-is
    into session.json's own "fetch"."params" (see session_store), and later
    replayed unchanged by resume_download_task. Never username/password."""
    return {
        "url": url, "project_id": project_id, "deployment_id": deployment_id,
        "clear_cache": clear_cache, "include_events": include_events,
    }


async def _run_fetch(
    task_id: str, *, username: str, password: str, output_dir: Path, settings,
    url: str, project_id: int, deployment_id: str, clear_cache: bool, include_events: bool,
) -> None:
    """Shared by start_download_task (fresh request) and resume_download_task
    (an earlier interruption's own params, replayed) — runs
    'fetch_camtrapdp_package' as a background worker-thread task (it's a
    blocking/synchronous call), updating both the in-memory poll status
    (_download_tasks) and the session manifest (session_store) on success
    or failure.

    title/description/license default from the shared settings.toml's
    TRAPPER section — same defaults 'trapper download' itself falls back to
    when its own --title/--description/--license-* flags aren't given."""
    trapper_defaults = settings.TRAPPER
    camtrapdp_defaults = settings.CAMTRAPDP
    fetch = {
        "source_type": "trapper",
        "params": _fetch_params(
            url=url, project_id=project_id, deployment_id=deployment_id,
            clear_cache=clear_cache, include_events=include_events,
        ),
        "output_dir": str(output_dir), "input_dir": None,
    }
    try:
        path = await asyncio.to_thread(
            fetch_camtrapdp_package,
            trapper_url=url,
            trapper_user=username,
            trapper_password=password,
            project_id=project_id,
            deployment_id=deployment_id,
            output_dir=output_dir,
            clear_cache=clear_cache,
            title=camtrapdp_defaults.dataset_name,
            description=camtrapdp_defaults.description,
            version=DEFAULT_VERSION,
            license_id=camtrapdp_defaults.license_id,
            license_name=camtrapdp_defaults.license_name,
            license_url=camtrapdp_defaults.license_url,
            include_events=include_events,
            retry_attempts=trapper_defaults.retry_attempts,
            retry_wait_seconds=trapper_defaults.retry_wait_seconds,
        )
        _download_tasks[task_id] = {"status": "done", "path": str(path), "error": None}
        fetch["input_dir"] = str(path)
        session_store.write_fetch_phase(
            task_id, product_type="camtrapdp", source_type="trapper", fetch=fetch, status="done", error=None,
        )
    except Exception as exc:
        _download_tasks[task_id] = {"status": "error", "path": None, "error": str(exc)}
        session_store.write_fetch_phase(
            task_id, product_type="camtrapdp", source_type="trapper", fetch=fetch, status="error", error=str(exc),
        )


def start_download_task(
    *, url: str, username: str, password: str, project_id: int, deployment_id: str, clear_cache: bool = False,
    include_events: bool = True,
) -> str:
    """Mints a brand new session (see session_store's own docstring) and
    launches the fetch in it — its task_id then flows through preprocessing
    and, if the user gets that far, into services.publish_orchestrator's
    own start_publish_all_task(task_id=...), so the whole run — fetched
    source, preprocessing, publish build dirs — ends up living under the
    same session_dir. Poll get_download_task_status(task_id) for progress."""
    task_id = session_store.new_task_id()
    _download_tasks[task_id] = {"status": "running", "path": None, "error": None}

    settings = load_settings()
    output_dir = session_store.session_dir(task_id) / "source"
    params = _fetch_params(
        url=url, project_id=project_id, deployment_id=deployment_id,
        clear_cache=clear_cache, include_events=include_events,
    )
    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="trapper",
        fetch={"source_type": "trapper", "params": params, "output_dir": str(output_dir), "input_dir": None},
        status="running", error=None,
    )

    asyncio.create_task(_run_fetch(
        task_id, username=username, password=password, output_dir=output_dir, settings=settings, **params,
    ))
    return task_id


def resume_download_task(task_id: str, *, username: str, password: str) -> str:
    """Resumes a Trapper fetch an earlier interruption left on disk — same
    project/deployment/clear_cache/include_events as the original request
    (see session_store.write_fetch_phase — url isn't secret, so it's reused
    from the manifest too), with freshly-supplied credentials (never
    persisted — see session_store's own docstring). Retrying the exact same
    fetch is what actually skips redoing completed work, via
    fetch_camtrapdp_package's own skip-if-already-fetched check (see
    services.trapper) — this function itself has no partial-download logic
    of its own."""
    manifest = session_store.read_manifest(task_id)
    if manifest is None or manifest.get("fetch", {}).get("source_type") != "trapper":
        raise RuntimeError(f"No interrupted Trapper fetch session found for task {task_id!r}.")
    params = manifest["fetch"]["params"]
    output_dir = Path(manifest["fetch"]["output_dir"])

    _download_tasks[task_id] = {"status": "running", "path": None, "error": None}
    settings = load_settings()
    asyncio.create_task(_run_fetch(
        task_id, username=username, password=password, output_dir=output_dir, settings=settings, **params,
    ))
    return task_id


def get_download_task_status(task_id: str) -> dict[str, Any] | None:
    return _download_tasks.get(task_id)
