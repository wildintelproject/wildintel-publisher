"""Shared, phase-agnostic session-directory primitives.

A "session" is one wizard run's own persistent directory under
get_sessions_dir()/<task_id> — first written to as soon as its source
resolves: a Trapper/git/public-URL fetch starting in the background (see
trapper_service.py/software_service.py/camtrapdp_source_service.py's own
start_*_task), or a Local Directory resolving synchronously (see
camtrapdp_source_service.resolve_local_source) — reused unchanged through
preprocessing (the camtrapdp router's generate-metadata endpoint) and all
the way through publishing (services.publish_orchestrator), so everything
about one run lives under the same folder from the moment its source is
first picked. Local Directory mints its task_id on that very first
resolve call and keeps reusing it (see resolve_local_source's own
docstring) instead of a background task_id handed out once — it never
lingers in a "fetching" phase (resolving is synchronous: either it's
"fetched" or it "error"ed, on the very same call), but everything after
that (preprocessing, publish) treats it exactly like any other source.

The manifest (session.json) is additive across phases — writing one
phase's own section (`fetch`, `preprocessing`, or publish_orchestrator's own
flat fields) never erases another phase's already-written section, since
every writer here starts from whatever's already on disk (see
read_manifest) and merges its own updates into it.

Never writes credentials: see scrub_secrets — every caller must scrub its
own secrets (Trapper's username/password, a repo's token/password) BEFORE
handing a dict to one of the write_*_phase functions below. Resuming an
interrupted session always requires the user to re-supply them by hand.

The whole session_dir is deleted only once a session's own "phase" field
reaches the literal "done" — only publish_orchestrator ever writes that,
once the whole run succeeds (see list_sessions/its own success path).
"status" is NOT that signal: every phase's own writer (write_fetch_phase/
write_preprocessing_phase/publish_orchestrator's own manifest writer)
reuses "status" to mean "this particular phase's own operation just
succeeded/failed/is running", so a "fetched" or "preprocessed" session
sits on disk with status == "done" for as long as the user hasn't moved on
to the next phase yet — that's on purpose, for the web app's "resume
this?" screen (see services.publish_orchestrator's own docstring for the
publish-phase resume mechanics this module underlies)."""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wildintel_publisher.core.config import get_sessions_dir


def new_task_id() -> str:
    return str(uuid.uuid4())


def session_dir(task_id: str) -> Path:
    return get_sessions_dir() / task_id


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_manifest(task_id: str) -> dict[str, Any] | None:
    path = session_dir(task_id) / "session.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_manifest(task_id: str, manifest: dict[str, Any]) -> None:
    """Atomic write (.tmp + replace) so a session_dir left behind by a
    crash never has a half-written session.json."""
    d = session_dir(task_id)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "session.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / "session.json")


def scrub_secrets(cfg: dict, secret_keys: set[str]) -> dict:
    return {k: v for k, v in cfg.items() if k not in secret_keys}


def write_fetch_phase(
    task_id: str, *, product_type: str, source_type: str, fetch: dict, status: str, error: str | None,
) -> None:
    """Bootstraps or updates a session while its own source fetch is in
    progress, has failed, or has just finished — called by
    trapper_service.py/software_service.py/camtrapdp_source_service.py.
    `fetch` must already be secret-free (each caller scrubs its own
    credentials before building it — Trapper's username/password are never
    part of it)."""
    existing = read_manifest(task_id) or {}
    manifest = {
        **existing,
        "task_id": task_id,
        "created_at": existing.get("created_at") or now_iso(),
        "phase": "fetched" if status == "done" else "fetching",
        "status": status,
        "error": error,
        "product_type": product_type,
        "source_type": source_type,
        "fetch": fetch,
    }
    write_manifest(task_id, manifest)


def write_preprocessing_phase(task_id: str, *, status: str, error: str | None, choices: dict) -> None:
    """No-op if `task_id` has no session on disk — preprocessing only ever
    updates a session an earlier fetch phase already created (a request
    with no session_task_id at all — a caller that predates this feature,
    or one that never threaded the session's own taskId through, e.g. a
    stale frontend build — has nothing to update here). Every current
    source, Local Directory included, always has one by this point."""
    existing = read_manifest(task_id)
    if existing is None:
        return
    manifest = {
        **existing,
        "phase": "preprocessed" if status == "done" else "preprocessing",
        "status": status,
        "error": error,
        "preprocessing": {"status": status, **choices},
    }
    write_manifest(task_id, manifest)


def list_sessions() -> list[dict[str, Any]]:
    """Every session left on disk whose manifest's phase != 'done', across
    every phase — checked on `phase`, never `status`: `status` is reused by
    every phase's own writer (write_fetch_phase/write_preprocessing_phase/
    publish_orchestrator's own _write_session_manifest) to mean "this
    particular phase's own operation just succeeded", so a "fetched" or
    "preprocessed" session sits on disk with status == "done" for as long
    as the user hasn't moved on to the next phase yet — deleting it on that
    signal would throw away a perfectly resumable session. `phase` reaching
    the literal string "done" is the one unambiguous "entire run finished"
    signal (only publish_orchestrator ever writes it, once the whole
    publish succeeds) — its own owning phase already deleted (or is about
    to delete) its own session_dir directly; defensively cleaned up here
    too in case a process died in between."""
    root = get_sessions_dir()
    if not root.is_dir():
        return []
    sessions = []
    for entry in sorted(root.iterdir()):
        manifest = read_manifest(entry.name)
        if manifest is None:
            continue
        if manifest.get("phase") == "done":
            shutil.rmtree(entry, ignore_errors=True)
            continue
        sessions.append(manifest)
    return sessions


def discard_session(task_id: str) -> None:
    """Permanently deletes an interrupted session — for when the user
    chooses not to resume it, at whichever phase it was interrupted."""
    shutil.rmtree(session_dir(task_id), ignore_errors=True)
