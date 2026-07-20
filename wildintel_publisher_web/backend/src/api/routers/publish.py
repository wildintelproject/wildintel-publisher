"""FastAPI router — multi-repo publish (upload phase for every selected
repo, then a cross-repo DOI populate pass, then the release/lock phase for
all of them). See services.publish_orchestrator for the actual flow;
services.doi_populate for the generic DOI cross-referencing logic."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.requests import PublishAllRequest, RepoPublishConfig
from services import b2share_service, hfh_service, publish_orchestrator, zenodo_service

router = APIRouter(prefix="/api/publish", tags=["publish"])


def _resolve_repo_config(cfg: RepoPublishConfig, *, version: str | None, timeout: int | None) -> dict:
    """Validates/resolves what each single-repo publish router already did
    (token fallback to settings.toml, required fields, output_dir default)
    before handing the config off to the orchestrator — see
    services.hfh_service/zenodo_service/b2share_service's own resolve_token/
    save_config, reused here unchanged."""
    data = cfg.model_dump()
    data["version"] = version
    data["timeout"] = timeout

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

    return data


@router.post("/start")
async def start(req: PublishAllRequest) -> dict:
    """Starts the whole multi-repo publish as one background task. Returns
    a task_id; poll GET /api/publish/{task_id} for a per-repo status dict."""
    if not req.repos:
        raise HTTPException(400, "No repositories to publish to.")

    resolved_repos = [_resolve_repo_config(cfg, version=req.version, timeout=req.timeout) for cfg in req.repos]

    task_id = publish_orchestrator.start_publish_all_task(
        input_dir=Path(req.input_dir), repos=resolved_repos, primary_doi_source=req.primary_doi_source,
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
