"""FastAPI router — multi-repo publish (upload phase for every selected
repo, then a cross-repo DOI populate pass, then the release/lock phase for
all of them). See services.publish_orchestrator for the actual flow;
services.doi_populate for the generic DOI cross-referencing logic."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.requests import PublishAllRequest, RepoPublishConfig
from services import b2share_service, gbif_service, hfh_service, publish_orchestrator, zenodo_service

router = APIRouter(prefix="/api/publish", tags=["publish"])


def _resolve_repo_config(
    cfg: RepoPublishConfig, *, version: str | None, timeout: int | None, dry_run: bool,
) -> dict:
    """Validates/resolves what each single-repo publish router already did
    (token fallback to settings.toml, required fields, output_dir default)
    before handing the config off to the orchestrator — see
    services.hfh_service/zenodo_service/b2share_service's own resolve_token/
    save_config, reused here unchanged.

    In dry_run, none of that applies: no token/repo_id/community_id is
    required (the publish never actually reaches a real repository, so
    there's nothing to authenticate against or create), and nothing gets
    written to settings.toml — a dry run must not have side effects on the
    user's saved configuration."""
    data = cfg.model_dump()
    data["version"] = version
    data["timeout"] = timeout

    if dry_run:
        data["token"] = cfg.token or "dry-run"
        if not data.get("output_dir"):
            get_output_dir = {
                "hfh": hfh_service.get_hfh_output_dir,
                "zenodo": zenodo_service.get_zenodo_output_dir,
                "b2share": b2share_service.get_b2share_output_dir,
                "gbif": gbif_service.get_gbif_output_dir,
            }[cfg.repo]
            data["output_dir"] = str(get_output_dir())
        return data

    if cfg.repo == "hfh":
        if not cfg.repo_id:
            raise HTTPException(400, "Missing the HuggingFace Hub repository (user_or_org/dataset).")
        try:
            data["token"] = hfh_service.resolve_token(cfg.token)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        hfh_service.save_config(cfg.repo_id, cfg.token)
        if not data.get("output_dir"):
            data["output_dir"] = str(hfh_service.get_hfh_output_dir())
    elif cfg.repo == "zenodo":
        try:
            data["token"] = zenodo_service.resolve_token(cfg.token)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        zenodo_service.save_config(cfg.environment, cfg.communities, cfg.token)
        if not data.get("output_dir"):
            data["output_dir"] = str(zenodo_service.get_zenodo_output_dir())
    elif cfg.repo == "b2share":
        if not cfg.community_id:
            raise HTTPException(400, "Missing the EUDAT B2SHARE community UUID.")
        try:
            data["token"] = b2share_service.resolve_token(cfg.token)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        b2share_service.save_config(cfg.environment, cfg.community_id, cfg.token)
        if not data.get("output_dir"):
            data["output_dir"] = str(b2share_service.get_b2share_output_dir())
    elif cfg.repo == "gbif":
        if not cfg.archive_url:
            raise HTTPException(400, "Missing the archive URL where the Camtrap DP is already hosted.")
        if not cfg.publishing_organization_key or not cfg.installation_key:
            raise HTTPException(400, "Missing the GBIF publishing organization/installation UUID.")
        try:
            data["username"], data["password"] = gbif_service.resolve_credentials(cfg.username, cfg.password)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        gbif_service.save_config(
            cfg.environment, cfg.publishing_organization_key, cfg.installation_key,
            cfg.registry_language, cfg.username, cfg.password,
        )
        if not data.get("output_dir"):
            data["output_dir"] = str(gbif_service.get_gbif_output_dir())

    return data


@router.post("/start")
async def start(req: PublishAllRequest) -> dict:
    """Starts the whole multi-repo publish as one background task. Returns
    a task_id; poll GET /api/publish/{task_id} for a per-repo status dict."""
    if not req.repos:
        raise HTTPException(400, "No repositories to publish to.")

    resolved_repos = [
        _resolve_repo_config(cfg, version=req.version, timeout=req.timeout, dry_run=req.dry_run)
        for cfg in req.repos
    ]

    task_id = publish_orchestrator.start_publish_all_task(
        input_dir=Path(req.input_dir), repos=resolved_repos, primary_doi_source=req.primary_doi_source,
        dry_run=req.dry_run,
    )
    return {"task_id": task_id}


@router.get("/{task_id}")
def status(task_id: str) -> dict:
    """Poll the status of a multi-repo publish task — {"status", "repos":
    {repo: {"status", "stage", "error", "repo_url", "doi", "pid",
    "output_dir"}}, "error"}."""
    result = publish_orchestrator.get_publish_task_status(task_id)
    if result is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return result
