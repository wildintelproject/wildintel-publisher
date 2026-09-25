"""Orchestrates publishing the same product to several repos in one go —
the web wizard's own version of "publish all", now with a cross-repo DOI
populate step wired in between uploading and locking (see
wildintel_publisher.services.doi_populate for the generic
cross-referencing logic).

Flow, for `repos` (an ORDERED list of already-configured
{"repo": "hfh"|"zenodo"|"b2share", ...} dicts — see schemas.requests.
RepoPublishConfig):

  1. Upload phase — prepare + upload every repo, ONE AFTER ANOTHER (each
     one hands the next its own core files — see _extract_chain_input and
     the own_output_mode paragraph below for exactly which copy of them —
     same chaining the wizard used to do itself before this module
     existed). Whichever repos provide their own DOI (PROVIDES_DOI —
     Zenodo/B2SHARE) already reserve it here, same as 'zenodo upload'/
     'b2share upload' on the CLI.
  2. Populate phase — doi_populate.populate() cross-references whatever
     DOI got reserved above into every OTHER repo's own CITATION.cff (as
     an alternate identifier, or as the primary one for HFH, which never
     has a DOI of its own — see primary_doi_source). Any repo whose files
     actually changed gets re-uploaded (same upload_to_X call as phase 1,
     reusing the same draft/deposition/repository).
  3. Lock phase — release_on_zenodo/release_on_b2share/
     tag_release_on_huggingface+release_on_huggingface for every repo, in
     order — only now, once every cross-reference has already landed.

Between steps 2 and 3 — once the populate broadcast is over and no file
can change anymore — the product's own core files are copied into each
repo's user-configured output_dir (see _finalize_one/
copy_prepared_output_files), and right after that each repo's build
directory, chain input and downloaded copies are deleted (see
_discard_build_artifacts), plus the shared media cache once every repo
is finalized. Phase 3 only needs the small per-repo records kept in the
session's own metadata.json (see _capture_repo_record/_resolve_lock_dir/
_read_hfh_version). The rest of the session is deleted once step 3 has
finished.

own_output_mode — each repo's OWN output_mode (RepoPublishConfig; the same
choice that, after phase 2, decides how its user-facing output_dir gets filled
— see _finalize_one) ALSO decides, right here in phase 1, what it hands the
NEXT repo in the chain (see _extract_chain_input/_download_repo_copy,
called from the per-repo loop below):
  - "prepared" (the default) — the repo's own build_dir, as it stands
    right after its own upload (e.g. media.csv already rewritten to HFH
    URLs, in mirror mode) — unchanged from before this mode-awareness
    existed.
  - "downloaded" — round-trips through the real remote FIRST (still
    unpublished/undrafted at this point — see _download_repo_copy's own
    docstring on why that's fine for HFH/Zenodo but needs a draft-aware
    call for B2SHARE), so the next repo builds on a verified copy of what
    actually landed, not just what the local build_dir claims.
  - "passthrough" — forwards this repo's OWN input unchanged, with no
    extraction at all: this repo is treated as not having transformed
    anything worth handing forward.
This only matters for the INTERNAL chain — a fresh dry_run "downloaded"
falls back to "prepared" (nothing real was ever uploaded to round-trip
through).

GBIF is not like the other three: it never prepares or uploads any files of
its own — it only registers, in GBIF's Registry, a dataset whose CAMTRAP_DP
endpoint points at a URL where the Camtrap DP is already hosted elsewhere
(archive_url — typically another repo in the same `repos` list, once THAT
one has published its OWN phase 1, e.g. HFH's floating "main" branch, not
tagged yet at this point). Unlike the other three, though, it registers
EARLY: repo == "gbif" makes its one real Registry call (create-or-update the
dataset + its endpoint) during phase 1 itself (_upload_one), the moment its
own turn in the chain comes up — not phase 3 — precisely so that whatever
DOI GBIF auto-mints for it (most organizations don't get one — see
gbif.register_gbif_dataset) is already known in time for phase 2 below.
It's still excluded from doi_populate's own cross-referencing dict (it has
no CITATION.cff of its own to write into), so its DOI doesn't flow through
the generic multi-repo mechanism there — instead, right BEFORE
doi_populate.populate() runs (still phase 2, before ANY repo gets
tagged/released), a dedicated best-effort step reflects GBIF's own DOI into
HFH's build_dir CITATION.cff/README.md (same gbif_service.sync_doi_to_hfh
the CLI's manual "Sync DOI" section calls) and re-uploads just those files
to HFH's still-untagged "main". Deliberately BEFORE populate(), not after:
GBIF's DOI is always meant to be HFH's PRIMARY identifier, and
common.patch_citation_with_identifier only ever claims HFH's top-level
"doi" field for a value when none is set yet — going first is what lets
GBIF's DOI win that slot unconditionally, so whatever Zenodo/B2SHARE DOI
populate() cross-references into HFH moments later always lands as a
secondary "identifiers" entry instead, never displacing it. It also means
HFH's own tag, created moments later in phase 3, captures a commit that
already has GBIF's DOI cross-referenced into it, instead of tagging first
and patching main afterward (which would leave the tag stale relative to
main). This only happens when HFH is part of the same run; standalone GBIF
(or GBIF without HFH) skips it, same as before.

phase 3 (_lock_one) is then a no-op for GBIF — nothing left to register.
Instead, once every repo's own phase-3 lock+finalize has run (so HFH's tag,
if any, already exists), one last best-effort step re-points GBIF's
endpoint away from HFH's floating "main" branch to that tag's own
permanent URL (e.g. ".../resolve/main/..." -> ".../resolve/1.0/...") via a
SECOND call to gbif.register_gbif_dataset with the same dataset_key —
leaving GBIF pointed at main forever would mean a LATER v2 publish's own
phase-1 upload could silently change what THIS v1 GBIF dataset serves,
before v2 ever gets its own tag. Skipped the same way as the DOI-sync step
above when HFH isn't part of the run, or when archive_url doesn't look like
one of HFH's own resolve URLs (a manually-provided external archive).

Dry run (dry_run=True on start_publish_all_task): every step above still
runs, EXCEPT the actual network upload/release calls to Zenodo/B2SHARE/HFH,
which are replaced by the _dry_run_* helpers below — a synthetic record
(fake-but-well-formed DOI/PID) is written to disk instead of a real one, so
the populate phase's cross-referencing logic runs completely for real
against it. prepare_*_export (local file generation) and doi_populate.
populate() itself are never mocked — only the network boundary is.

Resumable sessions: every task's build directories (and the extra "chain"
directories fed from one repo into the next) live under a persistent
session_store.session_dir(task_id) directory instead of a throwaway
tempdir (possibly the SAME session an earlier fetch/preprocess phase
already created — see session_store's own docstring — when `task_id` is
passed into start_publish_all_task), and a session.json manifest is
written there after every state change (see _write_session_manifest) —
deliberately EXCLUDING credentials (token/password: see _scrub_secrets),
since resuming always requires the user to re-supply them. The whole
session_dir is only deleted once the task actually finishes successfully
(see _run's `finally`); on error, it's left on disk on purpose, so
resume_publish_all_task can pick the task back up — already-downloaded
images (download_public_images already skips what's on disk) and
already-uploaded Zenodo/B2SHARE files (see zenodo.upload_to_zenodo/
b2share.upload_to_b2share, which skip whatever the reused deposition/draft
already lists) aren't redone, and any repo whose own "stage" is already
"done" is skipped entirely rather than re-run."""
from __future__ import annotations

import asyncio
import json
import random
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wildintel_publisher.config import load_settings
from wildintel_publisher.services import b2share as b2share_cli
from wildintel_publisher.services import common
from wildintel_publisher.services import doi_populate
from wildintel_publisher.services import gbif as gbif_cli
from wildintel_publisher.services import hfh as hfh_cli
from wildintel_publisher.services import product
from wildintel_publisher.services import zenodo as zenodo_cli

from services import b2share_service, camtrapdp_service, gbif_service, hfh_service, session_store, zenodo_service

DEFAULT_TIMEOUT = 60

# Hard, product-type-inherent repo restrictions enforced here regardless of
# caller (defense in depth on top of the wizard's own REPOS_BY_PRODUCT_TYPE
# gating in WizardPage.tsx) — a product type absent from this dict is left
# fully unrestricted at this layer (same as Camtrap DP/YOLO today, which stay
# generic across all four repos here; the CLI's own hfh/zenodo/b2share/gbif
# commands are equally unrestricted, see docs/developer-guide.md). A software
# application has no biodiversity/media content to speak of, so HFH and GBIF
# are never a fit for it, in the wizard or otherwise — only Zenodo/B2SHARE.
ALLOWED_REPOS_BY_PRODUCT_TYPE: dict[str, set[str]] = {
    product.SOFTWARE: {"zenodo", "b2share"},
}


def _require_repo_allowed(product_type: str, repo: str) -> None:
    allowed = ALLOWED_REPOS_BY_PRODUCT_TYPE.get(product_type)
    if allowed is not None and repo not in allowed:
        raise RuntimeError(
            f"{repo!r} does not accept {product_type!r} products — allowed repositories for "
            f"{product_type!r} are: {', '.join(sorted(allowed))}."
        )

# Unmistakably fake — never a real DOI registrant prefix — so a dry-run
# record can never be confused with (or accidentally look up) a real DOI.
DRY_RUN_DOI_PREFIX = "10.0000/dry-run"

_publish_tasks: dict[str, dict[str, Any]] = {}


def _dry_run_id() -> str:
    return uuid.uuid4().hex[:8]


def _dry_run_upload_hfh(cfg: dict, *, repo_status: dict) -> None:
    """Simulated 'upload_to_huggingface' — no HTTP call, just a plausible
    repo_url for the UI/CITATION.cff to display."""
    repo_id = cfg.get("repo_id") or f"dry-run/{_dry_run_id()}"
    repo_status["repo_url"] = f"https://huggingface.co/datasets/{repo_id}"


def _dry_run_zenodo_record(cfg: dict) -> dict:
    """Simulated 'upload_to_zenodo' response — a synthetic zenodo_record.json
    with a fake-but-well-formed DOI, real enough for doi_populate.populate()
    (which only cares that the 'doi' field is a non-empty string) to
    cross-reference it into every other repo's CITATION.cff, same as a real
    reserved DOI would be."""
    deposition_id = random.randint(1_000_000, 9_999_999)
    environment = cfg.get("environment") or "sandbox"
    host = "zenodo.org" if environment == "production" else "sandbox.zenodo.org"
    return {
        "deposition_id": deposition_id, "environment": environment,
        "doi": f"{DRY_RUN_DOI_PREFIX}/zenodo.{deposition_id}",
        "record_url": f"https://{host}/records/{deposition_id}", "published": False,
    }


def _dry_run_b2share_record(cfg: dict) -> dict:
    """Simulated 'upload_to_b2share' response — same idea as
    _dry_run_zenodo_record, with B2SHARE's own field names (pid/pid_kind)."""
    record_id = _dry_run_id()
    environment = cfg.get("environment") or "sandbox"
    host = "b2share.eudat.eu" if environment == "production" else "trng-b2share.eudat.eu"
    return {
        "record_id": record_id, "environment": environment,
        "pid": f"{DRY_RUN_DOI_PREFIX}/b2share.{record_id}", "pid_kind": "doi",
        "record_url": f"https://{host}/records/{record_id}", "published": False,
    }


def _initial_repo_status() -> dict:
    return {
        "status": "pending", "stage": "", "error": None,
        "repo_url": None, "doi": None, "pid": None, "output_dir": None,
        # gbif only: None until phase 2's post-populate sync step runs (see
        # _run) — then True/False once an auto-sync of GBIF's own DOI into
        # HFH's (still untagged) CITATION.cff was actually attempted.
        "doi_synced_to_hfh": None,
        # gbif only: None until the post-lock step runs (see _run) — then
        # True/False once GBIF's endpoint was actually re-pointed from
        # HFH's floating "main" branch to its own just-created tag.
        "archive_repointed_to_tag": None,
    }


def _archive_url_for_tag(archive_url: str, version: str) -> str | None:
    """Swaps a HuggingFace Hub resolve URL's branch segment for `version` —
    e.g. ".../datasets/alice/dataset/resolve/main/camtrapdp-remote.zip" ->
    ".../resolve/1.0/camtrapdp-remote.zip". Used to re-point GBIF's endpoint
    at HFH's own tag once it exists, instead of the floating "main" branch
    it was initially registered against (see the module's own docstring).

    Returns None if `archive_url` doesn't look like one of HFH's own
    "resolve/<branch>/<file>" URLs — a manually-provided external archive,
    or a URL already pointing somewhere else — in which case the caller
    leaves it untouched rather than guess."""
    match = re.match(r"^(https://huggingface\.co/datasets/[^/]+/[^/]+/resolve/)[^/]+(/.+)$", archive_url)
    if not match:
        return None
    return f"{match.group(1)}{version}{match.group(2)}"


def get_publish_task_status(task_id: str) -> dict[str, Any] | None:
    return _publish_tasks.get(task_id)


# Never written to session.json — a resumed session always requires the user
# to re-enter these by hand (see the module docstring's "Resumable sessions"
# note).
_SECRET_CFG_KEYS = {"token", "password"}


def _scrub_secrets(cfg: dict) -> dict:
    return session_store.scrub_secrets(cfg, _SECRET_CFG_KEYS)


def _session_dir(task_id: str) -> Path:
    return session_store.session_dir(task_id)


def _write_session_manifest(
    task_id: str, *, repos: list[dict], primary_doi_source: str | None,
    dry_run: bool, input_dir: Path, media_dir: Path | None, created_at: str,
    build_dirs: dict[str, Path], input_dirs: dict[str, Path],
) -> None:
    """Persists everything needed to resume this task after a crash/restart
    or a backend restart — see resume_publish_all_task. Written after every
    state change in _run so a session_dir left behind by an interrupted task
    is never more than one step stale.

    Merges into whatever's already on disk (see session_store's own
    docstring) rather than overwriting it wholesale — a session that
    reached this point via a prior fetch/preprocess phase (see
    session_store.write_fetch_phase/write_preprocessing_phase) keeps its
    own "fetch"/"preprocessing"/"product_type"/"source_type" sections
    alongside these publish-phase fields, whose own shape is unchanged from
    before this module started sharing session_store with those phases."""
    task = _publish_tasks[task_id]
    existing = session_store.read_manifest(task_id) or {}
    manifest = {
        **existing,
        "task_id": task_id,
        "created_at": created_at,
        "phase": "done" if task["status"] == "done" else "publishing",
        "status": task["status"],
        "error": task.get("error"),
        "dry_run": dry_run,
        "primary_doi_source": primary_doi_source,
        "input_dir": str(input_dir),
        "media_dir": str(media_dir) if media_dir else None,
        "repos": [_scrub_secrets(cfg) for cfg in repos],
        "repo_status": task["repos"],
        "build_dirs": {repo: str(d) for repo, d in build_dirs.items()},
        "input_dirs": {repo: str(d) for repo, d in input_dirs.items()},
    }
    session_store.write_manifest(task_id, manifest)


def list_unfinished_sessions() -> list[dict[str, Any]]:
    """Sessions left on disk by a task that didn't finish successfully — a
    task that reaches "done" always deletes its own session_dir (see _run's
    `finally`), so anything found here is either still running (backend
    hasn't restarted since) or was interrupted (backend restarted, or the
    process died) — the web app offers both to resume on startup. Spans
    every phase (fetching/preprocessing/publishing), not just this module's
    own publish phase — see session_store.list_sessions."""
    return session_store.list_sessions()


def discard_session(task_id: str) -> None:
    """Permanently deletes an interrupted session's build directories and
    manifest — for when the user chooses not to resume it."""
    session_store.discard_session(task_id)


async def _register_gbif(cfg: dict, *, input_dir: Path, repo_status: dict, dry_run: bool) -> None:
    """Creates or updates the GBIF Registry dataset for `cfg`, pointing its
    CAMTRAP_DP endpoint at whatever `cfg["archive_url"]` currently is — the
    ONE call this module ever needs for it, reused both in phase 1 (register
    early, against HFH's still-untagged "main") and again in the post-lock
    step (re-point at HFH's own tag — see the module's own docstring and
    _archive_url_for_tag). register_gbif_dataset's own dataset_key fallback
    (its own record file under `cfg["output_dir"]`) is what makes the second
    call update the SAME dataset rather than create a new one, even across a
    resume where `cfg["dataset_key"]` itself wasn't preserved."""
    if dry_run:
        dataset_key = cfg.get("dataset_key") or f"dry-run-{_dry_run_id()}"
        environment = cfg.get("environment") or "sandbox"
        host = "www.gbif.org" if environment == "production" else "registry.gbif-test.org"
        repo_status["repo_url"] = f"https://{host}/dataset/{dataset_key}"
        return
    meta = await asyncio.to_thread(product.read_metadata_json, input_dir)
    if meta.get("product_type") != product.CAMTRAPDP:
        raise RuntimeError(
            f"GBIF only accepts Camtrap DP (biodiversity occurrence data) — {input_dir} is a "
            f"{meta.get('product_type')!r} product."
        )
    license_info = meta.get("license") or {}
    record = await asyncio.to_thread(
        gbif_cli.register_gbif_dataset,
        cfg["archive_url"], Path(cfg["output_dir"]),
        environment=cfg.get("environment") or "sandbox",
        publishing_organization_key=cfg.get("publishing_organization_key"),
        installation_key=cfg.get("installation_key"),
        username=cfg.get("username"), password=cfg.get("password"),
        title=meta["title"], description=meta["description"],
        license_url=license_info.get("url") or "",
        registry_language=cfg.get("registry_language") or "eng",
        homepage=meta.get("homepage"),
        dataset_key=cfg.get("dataset_key") or None,
    )
    repo_status["repo_url"] = record.get("dataset_page_url")
    repo_status["doi"] = record.get("doi")


def _detect_hfh_repo_id(input_dir: Path) -> str | None:
    """Same detection each PublishForm used to do live from the frontend
    (see camtrapdp_service.detect_hfh_repo_id) — now done server-side,
    right before a link-mode Zenodo/B2SHARE repo's own prepare/upload, from
    whichever directory is actually its input at that point in the chain."""
    try:
        meta = product.read_metadata_json(input_dir)
    except Exception:
        return None
    return camtrapdp_service.detect_hfh_repo_id(meta.get("homepage"))


async def _upload_one(
    cfg: dict, *, input_dir: Path, build_dir: Path, settings, repo_status: dict, dry_run: bool,
    media_dir: Path | None = None, media_cache_dir: Path | None = None,
) -> None:
    """Phase 1 (and re-run as-is during phase 2 for a changed repo, minus
    the 'preparing' half — see _reupload_one): prepare + upload a single
    repo into its own build_dir.

    prepare_*_export always runs for real, dry_run or not — it's pure local
    file generation (no network), and it's what gives doi_populate() and the
    UI real files to work with. Only the actual network upload is
    swapped out for a simulated one in dry_run (see the _dry_run_* helpers).

    media_cache_dir (unlike media_dir, passed for EVERY repo, not just the
    first — see _run's own call site) is one shared cache under this same
    task's own session_dir: each media file only gets downloaded/copied
    from its real source once per session no matter how many repos publish
    it — see common.download_public_images's own docstring for the
    mechanics and why a later repo's own image-resizing step can't corrupt
    it."""
    repo = cfg["repo"]
    version = cfg.get("version")
    timeout = cfg.get("timeout") or DEFAULT_TIMEOUT

    # Best-effort: input_dir always carries a real metadata.json in
    # production (the wizard's earlier generate-metadata step guarantees
    # it) — skip the check rather than fail outright if it's ever missing/
    # unreadable, same graceful-degradation _detect_hfh_repo_id uses above
    # for a similar best-effort read.
    try:
        meta = await asyncio.to_thread(product.read_metadata_json, input_dir)
    except Exception:
        meta = None
    if meta is not None:
        _require_repo_allowed(meta["product_type"], repo)

    if repo == "hfh":
        repo_status["stage"] = "preparing"
        await asyncio.to_thread(
            hfh_cli.prepare_hfh_export, input_dir=input_dir, output_dir=build_dir, metadata=settings.HFH,
            version=version or hfh_cli.DEFAULT_VERSION, image_timeout=timeout, overwrite=True,
            mirror_images=cfg["mirror_images"], media_dir=media_dir, media_cache_dir=media_cache_dir,
        )
        repo_status["stage"] = "uploading"
        if dry_run:
            _dry_run_upload_hfh(cfg, repo_status=repo_status)
        else:
            repo_url = await asyncio.to_thread(
                hfh_cli.upload_to_huggingface, build_dir, repo_id=cfg["repo_id"], token=cfg["token"],
                private=cfg["private"], mirror_images=cfg["mirror_images"],
            )
            repo_status["repo_url"] = repo_url
        return

    if repo == "gbif":
        # Registers (or updates) early, against whatever archive_url was
        # configured (typically HFH's still-untagged "main") — see
        # _register_gbif and the module's own docstring for why.
        await _register_gbif(cfg, input_dir=input_dir, repo_status=repo_status, dry_run=dry_run)
        return

    hfh_repo_id = cfg.get("hfh_repo_id")
    if hfh_repo_id is None and not cfg["mirror_images"]:
        hfh_repo_id = await asyncio.to_thread(_detect_hfh_repo_id, input_dir)
        cfg["hfh_repo_id"] = hfh_repo_id  # remembered for phase 2's re-upload

    if repo == "zenodo":
        repo_status["stage"] = "preparing"
        max_zip_file = cfg.get("max_zip_file")
        await asyncio.to_thread(
            zenodo_cli.prepare_zenodo_export, input_dir=input_dir, output_dir=build_dir, metadata=settings.ZENODO,
            hfh_repo_id=hfh_repo_id, self_contained=cfg["mirror_images"],
            version=version or zenodo_cli.DEFAULT_VERSION, image_timeout=timeout, overwrite=True,
            fit_archive_size=cfg.get("fit_archive_size", True),
            max_zip_bytes=round(max_zip_file * 1024 ** 3) if max_zip_file else None,
            min_image_edge=cfg.get("min_image_edge") or zenodo_cli.DEFAULT_MIN_IMAGE_EDGE,
            media_dir=media_dir, media_cache_dir=media_cache_dir,
        )
        repo_status["stage"] = "uploading"
        if dry_run:
            record = _dry_run_zenodo_record(cfg)
            (build_dir / zenodo_cli.RECORD_FILENAME).write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            await asyncio.to_thread(
                zenodo_cli.upload_to_zenodo, build_dir, token=cfg["token"], environment=cfg["environment"],
                communities=cfg.get("communities"), hfh_repo_id=hfh_repo_id,
                existing_deposition_id=cfg.get("existing_deposition_id"),
            )
    elif repo == "b2share":
        repo_status["stage"] = "preparing"
        max_zip_file = cfg.get("max_zip_file")
        await asyncio.to_thread(
            b2share_cli.prepare_b2share_export, input_dir=input_dir, output_dir=build_dir, metadata=settings.B2SHARE,
            hfh_repo_id=hfh_repo_id, self_contained=cfg["mirror_images"],
            version=version or b2share_cli.DEFAULT_VERSION, image_timeout=timeout, overwrite=True,
            fit_archive_size=cfg.get("fit_archive_size", True),
            max_zip_bytes=round(max_zip_file * 1024 ** 3) if max_zip_file else None,
            min_image_edge=cfg.get("min_image_edge") or b2share_cli.DEFAULT_MIN_IMAGE_EDGE,
            media_dir=media_dir, media_cache_dir=media_cache_dir,
        )
        repo_status["stage"] = "uploading"
        if dry_run:
            record = _dry_run_b2share_record(cfg)
            (build_dir / b2share_cli.RECORD_FILENAME).write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            await asyncio.to_thread(
                b2share_cli.upload_to_b2share, build_dir, token=cfg["token"], environment=cfg["environment"],
                community_id=cfg["community_id"], hfh_repo_id=hfh_repo_id,
                existing_record_id=cfg.get("existing_record_id"),
            )


async def _reupload_one(cfg: dict, *, build_dir: Path, dry_run: bool) -> None:
    """Phase 2: re-pushes a repo's already-uploaded files after populate()
    patched its CITATION.cff/README.md — reuses the same draft/deposition/
    repository (see each upload_to_X's own docstring: calling it again is
    safe and expected for exactly this).

    In dry_run there's no real destination to re-push to — the (already
    simulated) record file doesn't need to change just because populate()
    patched CITATION.cff, so this is a no-op."""
    if dry_run:
        return
    repo = cfg["repo"]
    if repo == "hfh":
        await asyncio.to_thread(
            hfh_cli.upload_to_huggingface, build_dir, repo_id=cfg["repo_id"], token=cfg["token"],
            private=cfg["private"], mirror_images=cfg["mirror_images"],
        )
    elif repo == "zenodo":
        await asyncio.to_thread(
            zenodo_cli.upload_to_zenodo, build_dir, token=cfg["token"], environment=cfg["environment"],
            communities=cfg.get("communities"), hfh_repo_id=cfg.get("hfh_repo_id"),
        )
    elif repo == "b2share":
        await asyncio.to_thread(
            b2share_cli.upload_to_b2share, build_dir, token=cfg["token"], environment=cfg["environment"],
            community_id=cfg["community_id"], hfh_repo_id=cfg.get("hfh_repo_id"),
        )


def _read_hfh_version(build_dir: Path, session_dir: Path | None = None) -> str:
    """The version to tag — read from HFH's own hfh_record.json (written by
    upload_to_huggingface), else build_dir's own metadata.json (still where
    the version ultimately came from in the first place — e.g. a session
    that started before the record file existed, resumed now), else — once
    build_dir itself is gone (see _discard_build_artifacts) — the session's
    own canonical metadata.json: the hfh_record.json folded into it (see
    _capture_repo_record), then its own top-level "version"."""
    record_path = build_dir / hfh_cli.RECORD_FILENAME
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("version"):
            return record["version"]
    if (build_dir / product.METADATA_FILENAME).is_file():
        return product.read_metadata_json(build_dir).get("version") or hfh_cli.DEFAULT_VERSION
    session_meta_path = session_dir / product.METADATA_FILENAME if session_dir is not None else None
    if session_meta_path is None or not session_meta_path.is_file():
        return hfh_cli.DEFAULT_VERSION
    # Read raw, not via product.read_metadata_json: the session's copy
    # carries the extra "repos" key (see _capture_repo_record), which
    # ProductMetadata's own schema rejects.
    session_meta = json.loads(session_meta_path.read_text(encoding="utf-8"))
    captured = session_meta.get("repos", {}).get("hfh") or {}
    return captured.get("version") or session_meta.get("version") or hfh_cli.DEFAULT_VERSION


def _resolve_lock_dir(cfg: dict, *, session_dir: Path, build_dir: Path) -> Path:
    """A small directory holding just this repo's own record file — all
    release_on_zenodo/release_on_b2share actually need to publish (they
    also patch a CITATION.cff/checksums next to it, but that copy is never
    uploaded anywhere after the lock, so its absence here is harmless —
    common.patch_citation_with_identifier skips a missing file). Lets
    phase 3 run after build_dir is gone (see _discard_build_artifacts).

    Reused as-is if it already exists: release_on_X rewrites the record
    in place (published flag, final pid/record_url), and a resume after
    an interrupted lock must keep building on that, not a stale copy."""
    repo = cfg["repo"]
    lock_dir = session_dir / f"{repo}-lock"
    record_filename = _RECORD_FILENAME_BY_REPO[repo]
    if (lock_dir / record_filename).is_file():
        return lock_dir
    record = _read_repo_record(session_dir, repo, build_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / record_filename).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return lock_dir


async def _lock_one(cfg: dict, *, session_dir: Path, build_dir: Path, repo_status: dict, dry_run: bool) -> None:
    """Phase 3: release_on_zenodo/release_on_b2share, or
    tag_release_on_huggingface+release_on_huggingface for HFH. GBIF has
    nothing left to do here — it already registered back in phase 1 (see
    _register_gbif and the module's own docstring) — so repo == "gbif"
    is a no-op; re-pointing its endpoint at HFH's own tag, once one exists,
    happens as a separate best-effort step in _run, after every repo's own
    phase 3 has run.

    Never needs build_dir itself (by now possibly already deleted — see
    _discard_build_artifacts): Zenodo/B2SHARE release against
    _resolve_lock_dir's own small copy of their record, and the released
    record is then folded back into the session's metadata.json and
    copied into the user's output_dir, whose own copy (from _finalize_one,
    which ran before this) still says "published": false.

    In dry_run, Zenodo/B2SHARE just flip their own simulated record's
    "published" flag (same doi/pid reserved back in _upload_one — a real
    release never changes the identifier, just publishes it); HFH has
    nothing to tag/release for real, so repo_status is filled from the
    repo_url _dry_run_upload_hfh already set."""
    repo = cfg["repo"]
    repo_status["stage"] = "releasing"
    if repo in _RECORD_FILENAME_BY_REPO:
        lock_dir = await asyncio.to_thread(_resolve_lock_dir, cfg, session_dir=session_dir, build_dir=build_dir)
        record_path = lock_dir / _RECORD_FILENAME_BY_REPO[repo]
    if repo == "hfh":
        if dry_run:
            return
        version = await asyncio.to_thread(_read_hfh_version, build_dir, session_dir)
        await asyncio.to_thread(
            hfh_cli.tag_release_on_huggingface, repo_id=cfg["repo_id"], token=cfg["token"], version=version,
        )
        await asyncio.to_thread(
            hfh_cli.release_on_huggingface, repo_id=cfg["repo_id"], token=cfg["token"],
            dry_run=False, verify_only=False,
        )
    elif repo == "zenodo":
        if dry_run:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["published"] = True
            record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            record = await asyncio.to_thread(zenodo_cli.release_on_zenodo, lock_dir, token=cfg["token"])
        repo_status["doi"] = record.get("doi")
        repo_status["repo_url"] = record.get("record_url")
    elif repo == "b2share":
        if dry_run:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["published"] = True
            record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            record = await asyncio.to_thread(b2share_cli.release_on_b2share, lock_dir, token=cfg["token"])
        repo_status["pid"] = record.get("pid")
        repo_status["repo_url"] = record.get("record_url")
    # repo == "gbif": nothing to do — see this function's own docstring.

    if repo in _RECORD_FILENAME_BY_REPO:
        _capture_repo_record(session_dir, repo, lock_dir)
        output_dir = Path(cfg["output_dir"])
        if output_dir.is_dir():
            shutil.copy2(record_path, output_dir / record_path.name)


async def _extract_chain_input(core_source: Path, chain_dir: Path, *, metadata_source: Path) -> Path:
    """The next repo in the publish order must never receive the previous
    repo's raw build_dir as its own input_dir — that directory also carries
    the previous repo's own extras (README.md, LICENSE, CITATION.cff,
    checksums-sha256.txt, images/, its zip...), and in --self-contained mode
    the product's own core files (datapackage.json/media.csv/... or
    data.yaml/images/labels) have already been bundled into a zip and
    deleted from build_dir entirely (see common.cleanup_self_contained_sources)
    — copying/validating straight from build_dir would find nothing.

    Uses the same ProductAdapter.extract_core_files every single-repo
    publish already uses for its own "prepared" user-facing output (see
    each web service's copy_prepared_output_files) — which also knows how
    to pull the core files back out of the self-contained zip when the loose
    copies are gone (see camtrapdp_adapter.py/yolo_adapter.py's own
    extract_core_files).

    `core_source` and `metadata_source` are DELIBERATELY separate params
    (see _run's own call sites, one per output_mode): `core_source` is
    normally the repo's own build_dir (output_mode="prepared", the
    default), but for output_mode="downloaded" it's instead a fresh,
    just-downloaded-back copy from the real remote (see
    _download_repo_copy) — which never has metadata.json (that file is
    deliberately excluded from every upload, see _upload_one's own
    docstring), so metadata_source always stays the repo's own build_dir
    regardless of where the core files themselves come from.

    `chain_dir` is caller-provided (a fixed path under the task's own
    session_dir, not a throwaway tempdir) so it survives a crash and its
    path can be persisted for resume_publish_all_task."""
    meta = await asyncio.to_thread(product.read_metadata_json, metadata_source)
    adapter = product.get_adapter(meta["product_type"])
    chain_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(adapter.extract_core_files, core_source, chain_dir)
    await asyncio.to_thread(product.copy_metadata_json, metadata_source, chain_dir)
    return chain_dir


def _checksums_cache_path(session_dir: Path, repo: str) -> Path:
    return session_dir / "checksums-cache" / f"{repo}.txt"


def _cache_checksums(session_dir: Path, repo: str, build_dir: Path) -> None:
    """Saves a copy of build_dir's own checksums-sha256.txt into the
    session's own small cache — see _get_checksums_for_populate, which
    reads it back later (at populate time) instead of needing build_dir to
    still exist by then. A no-op for GBIF (never has one)."""
    src = build_dir / common.CHECKSUM_FILENAME
    if not src.is_file():
        return
    dest = _checksums_cache_path(session_dir, repo)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


# hfh_cli's own RECORD_FILENAME is deliberately absent — HFH never needs
# _read_repo_record (see _download_repo_copy's own "hfh" branch, which
# only ever needs cfg["repo_id"], already known upfront).
_RECORD_FILENAME_BY_REPO = {"zenodo": zenodo_cli.RECORD_FILENAME, "b2share": b2share_cli.RECORD_FILENAME}
# What _capture_repo_record folds into the session's metadata.json — HFH's
# own record included (only its "version" is ever read back, by
# _read_hfh_version, once build_dir is gone).
_CAPTURED_RECORD_FILENAMES = {**_RECORD_FILENAME_BY_REPO, "hfh": hfh_cli.RECORD_FILENAME}


async def _get_checksums_for_populate(cfg: dict, *, session_dir: Path, build_dir: Path) -> Path:
    """The checksums-sha256.txt to update (see
    common.update_checksums_entries) when populate()/sync_doi_to_hfh patch
    a repo's own CITATION.cff/README.md. Three tiers, in order: the
    session's own small cache (see _cache_checksums, written right after
    this repo's own upload); build_dir directly, if it's still around
    (true for every run today — nothing deletes it yet, see the module's
    own docstring); only then a fresh download from the real remote
    (reusing _download_repo_copy — same as the chain's own
    output_mode="downloaded" case), for whenever build_dir eventually
    isn't an option either."""
    cached = _checksums_cache_path(session_dir, cfg["repo"])
    if cached.is_file():
        return cached
    in_build_dir = build_dir / common.CHECKSUM_FILENAME
    if in_build_dir.is_file():
        return in_build_dir
    downloaded = await _resolve_populate_file(
        cfg, session_dir=session_dir, build_dir=build_dir, filename=common.CHECKSUM_FILENAME,
    )
    if downloaded is None:
        raise RuntimeError(
            f"No checksums-sha256.txt found for {cfg['repo']!r} — neither cached, in its build_dir, "
            "nor in a fresh download from the real remote."
        )
    return downloaded


def _capture_repo_record(session_dir: Path, repo: str, build_dir: Path) -> None:
    """Folds a repo's own small record file (zenodo_record.json/
    b2share_record.json/hfh_record.json — written into build_dir by
    upload_to_X right after this repo's own upload) into the session's own
    canonical metadata.json, under "repos"[repo] — same idea as
    _capture_session_metadata, for the SAME reason: so _read_repo_record
    (and, through it, _download_repo_copy's own fallback) can still find a
    repo's deposition_id/record_id once build_dir itself is gone. A no-op
    for GBIF (registers straight into its own output_dir, never build_dir
    — see _register_gbif), and a harmless no-op if the session's own
    metadata.json hasn't been seeded yet (see _seed_session_metadata,
    which always runs first in _run)."""
    filename = _CAPTURED_RECORD_FILENAMES.get(repo)
    if not filename:
        return
    record_path = build_dir / filename
    meta_path = session_dir / product.METADATA_FILENAME
    if not record_path.is_file() or not meta_path.is_file():
        return
    record = json.loads(record_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("repos", {})[repo] = record
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_repo_record(session_dir: Path, repo: str, build_dir: Path) -> dict:
    """A repo's own small record (deposition_id for Zenodo, record_id for
    B2SHARE) — build_dir's own copy if it's still there, else the
    session's own canonical metadata.json (see _capture_repo_record), for
    whenever build_dir isn't an option anymore.

    Raises:
        RuntimeError: if neither has one — this repo genuinely never
        reserved anything yet.
    """
    filename = _RECORD_FILENAME_BY_REPO[repo]
    record_path = build_dir / filename
    if record_path.is_file():
        return json.loads(record_path.read_text(encoding="utf-8"))
    meta_path = session_dir / product.METADATA_FILENAME
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        record = meta.get("repos", {}).get(repo)
        if record:
            return record
    raise RuntimeError(f"No record found for {repo!r} — neither in {record_path} nor in the session's own metadata.json.")


async def _download_repo_copy(cfg: dict, *, session_dir: Path, build_dir: Path, target_dir: Path) -> None:
    """Downloads what THIS repo just uploaded back from the real remote,
    BEFORE it's ever locked/published — backs the chain's own
    output_mode="downloaded" case (see _run): a real round-trip
    verification that what actually landed on the remote is what the next
    repo in the chain then builds on, instead of just trusting the local
    build_dir.

    Reuses each repo's own record (see _read_repo_record — build_dir's own
    copy if still there, else the session's own canonical metadata.json)
    to know which remote deposition/record/repo to fetch. HFH has no
    separate draft/published state to worry about (its repo_id alone is
    enough — the files are already on its default branch, regardless of
    whether a tag exists yet); Zenodo's own get_deposition already works
    fine against a not-yet-published draft (same single endpoint, no
    separate flag — see
    test_zenodo_upload_resumes_by_skipping_files_the_deposition_already_has);
    B2SHARE's own published-record endpoint does NOT (a still-draft record
    isn't there yet), so this uses download_draft_files_from_b2share
    instead of download_files_from_b2share (published records only).
    Also backs _finalize_one's own "downloaded" case, which likewise runs
    before phase 3's lock."""
    repo = cfg["repo"]
    if repo == "hfh":
        await asyncio.to_thread(
            hfh_service.download_from_repo, repo_id=cfg["repo_id"], token=cfg["token"], target_dir=target_dir,
        )
    elif repo == "zenodo":
        record = _read_repo_record(session_dir, repo, build_dir)
        await asyncio.to_thread(
            zenodo_service.download_files_from_zenodo, environment=cfg["environment"],
            deposition_id=record["deposition_id"], token=cfg["token"], target_dir=target_dir,
        )
    elif repo == "b2share":
        record = _read_repo_record(session_dir, repo, build_dir)
        await asyncio.to_thread(
            b2share_service.download_draft_files_from_b2share, environment=cfg["environment"],
            record_id=record["record_id"], token=cfg["token"], target_dir=target_dir,
        )


def _populate_cache_dir(session_dir: Path, repo: str) -> Path:
    return session_dir / "populate-cache" / repo


def _cache_citation_and_readme(session_dir: Path, repo: str, build_dir: Path) -> None:
    """Saves a copy of build_dir's own CITATION.cff/README.md into the
    session's own small cache — see _resolve_populate_file, which reads
    them back later (at populate time) instead of needing build_dir to
    still exist by then. Exactly _cache_checksums's own reasoning, for the
    other two files doi_populate.populate() patches. A no-op for GBIF (has
    neither)."""
    cache_dir = _populate_cache_dir(session_dir, repo)
    for filename in ("CITATION.cff", "README.md"):
        src = build_dir / filename
        if src.is_file():
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, cache_dir / filename)


async def _resolve_populate_file(
    cfg: dict, *, session_dir: Path, build_dir: Path, filename: str, allow_download: bool = True,
) -> Path | None:
    """One file (CITATION.cff, README.md, or checksums-sha256.txt) needed
    to patch this repo's own citation — same three tiers as
    _get_checksums_for_populate's own docstring: the session's own small
    cache (see _cache_citation_and_readme/_cache_checksums), build_dir
    directly, or a fresh download from the real remote (reusing
    _download_repo_copy — same as the chain's own output_mode="downloaded"
    case; shared across every file/tier that needs it this same run, so a
    prior call for a DIFFERENT file never triggers a second download).
    None if even the download doesn't have it (e.g. a repo whose export
    never included this file in the first place).

    `allow_download=False` skips straight to that None instead of
    attempting the download — for a file (README.md) that populate()/
    sync_doi_to_hfh already treat as optional (patched only if present,
    see common.patch_readme_citation_url), a cache/build_dir miss just
    means this repo's export never produced one, not that it's missing
    and needs fetching back — unlike CITATION.cff/checksums-sha256.txt,
    which every repo always has and DOES warrant that last-resort
    round-trip."""
    cached = _populate_cache_dir(session_dir, cfg["repo"]) / filename
    if cached.is_file():
        return cached
    in_build_dir = build_dir / filename
    if in_build_dir.is_file():
        return in_build_dir
    if not allow_download:
        return None
    downloaded_dir = session_dir / f"{cfg['repo']}-download-fallback"
    if not (downloaded_dir / filename).is_file():
        await _download_repo_copy(cfg, session_dir=session_dir, build_dir=build_dir, target_dir=downloaded_dir)
    found = downloaded_dir / filename
    return found if found.is_file() else None


async def _resolve_populate_dir(cfg: dict, *, session_dir: Path, build_dir: Path, allow_download: bool = True) -> Path:
    """Materializes a small, throwaway directory with just what
    doi_populate.populate()/gbif_service.sync_doi_to_hfh need to patch THIS
    repo's own CITATION.cff/README.md and cross-reference its own DOI (its
    own record file, if it provides one) — never the FULL build_dir
    (LICENSE, images/, the zip...), which neither of them ever touches
    anyway. Each file is resolved independently via
    _resolve_populate_file/_read_repo_record's own 3-tier fallback.

    `allow_download=False` (see the call site building `populate_dirs` for
    EVERY repo, not just the ones actually being patched — collect_
    identifiers still needs every DOI-providing repo's own record file
    represented there) skips CITATION.cff's own download-fallback tier for
    a repo that isn't a patch candidate to begin with — no point in a real
    remote round-trip just to obtain a copy of a file that would, at best,
    sit here unpatched. README.md never downloads regardless (see
    _resolve_populate_file's own docstring).

    Idempotent within the SAME run: if this repo's own populate_dir was
    already resolved (and, by the time this is called again, possibly
    already patched by an earlier step this same run — e.g. GBIF's own DOI
    sync into HFH, which happens before doi_populate.populate() itself,
    see the module's own docstring), it's reused as-is rather than
    re-resolved from cache/build_dir, which would silently discard that
    earlier patch."""
    repo = cfg["repo"]
    populate_dir = session_dir / f"{repo}-populate"
    if (populate_dir / "CITATION.cff").is_file():
        return populate_dir
    populate_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("CITATION.cff", "README.md"):
        source = await _resolve_populate_file(
            cfg, session_dir=session_dir, build_dir=build_dir, filename=filename,
            allow_download=(allow_download if filename == "CITATION.cff" else False),
        )
        if source is not None:
            shutil.copy2(source, populate_dir / filename)
    record_filename = _RECORD_FILENAME_BY_REPO.get(repo)
    if record_filename:
        try:
            record = _read_repo_record(session_dir, repo, build_dir)
        except RuntimeError:
            record = None
        if record is not None:
            (populate_dir / record_filename).write_text(json.dumps(record), encoding="utf-8")
    return populate_dir


def _copy_populate_patches_back(populate_dir: Path, checksums_path: Path, build_dir: Path) -> None:
    """Copies CITATION.cff/README.md (from populate_dir) and the patched
    checksums-sha256.txt (from wherever _get_checksums_for_populate
    resolved it) back into build_dir. Needed because
    doi_populate.populate()/gbif_service.sync_doi_to_hfh patch those
    small, independently-resolved copies (see _resolve_populate_dir/
    _get_checksums_for_populate), never build_dir directly — but
    _reupload_one's own full re-upload and _finalize_one's own "prepared"
    output_mode copy still read straight from build_dir (still around for
    every run today — see the module's own docstring)."""
    for filename in ("CITATION.cff", "README.md"):
        patched = populate_dir / filename
        if patched.is_file():
            shutil.copy2(patched, build_dir / filename)
    if checksums_path.is_file():
        shutil.copy2(checksums_path, build_dir / common.CHECKSUM_FILENAME)


async def _finalize_one(
    cfg: dict, *, session_dir: Path, build_dir: Path, previous_output_dir: str, dry_run: bool,
) -> str:
    """Copies the product's own core files (see each web service's own
    copy_prepared_output_files) into this repo's user-configured
    output_dir, then resolves output_mode — same three choices each
    single-repo publish endpoint already offered, just computed here since
    chaining is now internal (see the module's own docstring).

    Runs right after phase 2 (populate + re-upload), BEFORE phase 3's
    lock — the files never change after that point (a release/tag only
    publishes what's already there), so waiting for the lock bought
    nothing, and doing it now is what lets build_dir stop being needed
    by the time phase 3 starts.

    output_mode == "downloaded" means "fetch a fresh copy back from the
    repo" — still unpublished at this point, so it goes through the same
    draft-aware _download_repo_copy the chain itself uses. Meaningless in
    dry_run (nothing was actually uploaded there to fetch back), so it
    falls through to the same result as "prepared" instead of hitting
    the network."""
    repo = cfg["repo"]
    output_dir = Path(cfg["output_dir"])
    output_mode = cfg.get("output_mode", "prepared")

    if repo == "gbif":
        # register_gbif_dataset already wrote gbif_linked_dataset_record.json
        # straight into output_dir itself (see _register_gbif) — there's no
        # build_dir content to copy, and no "downloaded"/"passthrough" choice
        # that would mean anything for a repo that never hosts a copy.
        return str(output_dir)

    if repo == "hfh":
        await asyncio.to_thread(hfh_service.copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)
    elif repo == "zenodo":
        await asyncio.to_thread(zenodo_service.copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)
    elif repo == "b2share":
        await asyncio.to_thread(b2share_service.copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)

    if output_mode == "passthrough":
        return previous_output_dir
    if output_mode == "downloaded" and not dry_run:
        download_dir = output_dir.parent / f"{output_dir.name}-downloaded"
        await _download_repo_copy(cfg, session_dir=session_dir, build_dir=build_dir, target_dir=download_dir)
        return str(download_dir)
    return str(output_dir)


def _seed_session_metadata(session_dir: Path, input_dir: Path) -> None:
    """Seeds the session's own canonical metadata.json, once, from the
    task's original input_dir — see _capture_session_metadata and the
    module's own docstring on why a single, always-present copy at the
    session level (rather than whichever per-repo directory — source/,
    <repo>-build/, chain-after-<repo>/... — happens to still exist at any
    given point) is what this is for. Never overwrites an already-seeded
    (and possibly since-evolved, via _capture_session_metadata) copy, so
    it's safe to call on every _run invocation, including a resume."""
    dest = session_dir / product.METADATA_FILENAME
    if dest.is_file():
        return
    src = input_dir / product.METADATA_FILENAME
    if src.is_file():
        shutil.copy2(src, dest)


def _capture_session_metadata(session_dir: Path, build_dir: Path) -> None:
    """Pulls forward whatever a repo's own upload just changed in ITS OWN
    metadata.json (e.g. product.write_homepage, in mirror mode) into the
    session's canonical copy — see _seed_session_metadata. ALWAYS
    overwrites (unlike the seed step): build_dir's own copy is the latest
    truth right after that repo's own turn. A no-op for GBIF (its own
    build_dir is never populated — see _upload_one)."""
    src = build_dir / product.METADATA_FILENAME
    if not src.is_file():
        return
    dest = session_dir / product.METADATA_FILENAME
    # "repos" is session-only bookkeeping (see _capture_repo_record) that
    # no build_dir's own copy ever has — carried over, never overwritten.
    captured = json.loads(dest.read_text(encoding="utf-8")).get("repos") if dest.is_file() else None
    shutil.copy2(src, dest)
    if captured:
        meta = json.loads(dest.read_text(encoding="utf-8"))
        meta["repos"] = captured
        dest.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _gbif_metadata_dir(session_dir: Path) -> Path:
    return session_dir / "gbif-input"


def _discard_build_artifacts(session_dir: Path, repo: str, build_dir: Path | None) -> None:
    """Deletes everything big this repo left under session_dir — its own
    build_dir, the chain input it handed the next repo (chain-after-<repo>)
    and any downloaded-back copy (see _download_repo_copy/
    _resolve_populate_file) — right after its own _finalize_one, the last
    step that needs any of them (phase 3 only needs the small caches: see
    _resolve_lock_dir/_read_hfh_version). Only ever touches paths inside
    session_dir, never a caller-supplied input_dir."""
    candidates = [
        build_dir, session_dir / f"chain-after-{repo}",
        session_dir / f"{repo}-downloaded", session_dir / f"{repo}-download-fallback",
    ]
    for path in candidates:
        if path is not None and path.resolve().is_relative_to(session_dir.resolve()):
            shutil.rmtree(path, ignore_errors=True)


async def _run(
    task_id: str, *, input_dir: Path, repos: list[dict], primary_doi_source: str | None,
    dry_run: bool, media_dir: Path | None, settings, resume: bool,
) -> None:
    task = _publish_tasks[task_id]
    session_dir = _session_dir(task_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    _seed_session_metadata(session_dir, input_dir)
    # A fresh start_publish_all_task() call reusing a task_id an earlier
    # fetch/preprocess phase already created (see session_store) has
    # nothing in `task` (a brand new in-memory dict) yet, but the manifest
    # on disk already knows when the whole session really began — prefer
    # that over "now" so created_at reflects the session's actual start,
    # not just whenever publishing happened to begin.
    created_at = task.get("created_at") or (session_store.read_manifest(task_id) or {}).get("created_at") \
        or datetime.now(timezone.utc).isoformat()
    task["created_at"] = created_at

    build_dirs: dict[str, Path] = {}
    # Each repo's own input_dir, as of its OWN turn in the chain — GBIF's is
    # what matters most, since its build_dir is never populated (see
    # _upload_one) and _lock_one falls back to reading metadata.json from
    # here instead; a repo publishing in mirror mode ahead of it (e.g. HFH)
    # may have just updated metadata.json's own "homepage" (see
    # product.write_homepage), and that update only reaches this dict's
    # entry, never the very first input_dir. On resume, a repo whose own
    # upload turn already finished (stage "uploaded"/"done") is restored
    # from the persisted manifest below instead of being recomputed.
    input_dirs: dict[str, Path] = {}

    if resume:
        manifest = session_store.read_manifest(task_id) or {}
        for repo, path_str in manifest.get("build_dirs", {}).items():
            path = Path(path_str)
            if path.is_dir():
                build_dirs[repo] = path
        # Unlike build_dirs (a session_dir subdirectory this module fully
        # owns), an input_dir may be a repo's own upstream input — trusted
        # as-is, with no existence check, same as a fresh (non-resumed) run
        # never checks the task's own original input_dir either.
        for repo, path_str in manifest.get("input_dirs", {}).items():
            input_dirs[repo] = Path(path_str)

    def _persist() -> None:
        _write_session_manifest(
            task_id, repos=repos, primary_doi_source=primary_doi_source,
            dry_run=dry_run, input_dir=input_dir, media_dir=media_dir, created_at=created_at,
            build_dirs=build_dirs, input_dirs=input_dirs,
        )

    try:
        # Marks a repo whose own prepare+upload turn already completed
        # (before an earlier interruption) — distinct from "done" (which
        # only means the lock/finalize phase, further below, already ran
        # for it too): the DOI-populate and lock/finalize phases below still
        # need to run for an "uploaded" repo the first time this task
        # actually reaches "done". Every stage past "uploaded" counts too —
        # a repo interrupted mid-finalize/mid-release must never be
        # re-uploaded from scratch.
        FINALIZED_STAGES = {"finalized", "releasing", "done"}
        UPLOADED_STAGES = {"uploaded", "finalizing"} | FINALIZED_STAGES

        current_input_dir = input_dir
        for i, cfg in enumerate(repos):
            repo = cfg["repo"]
            repo_status = task["repos"][repo]

            if repo_status.get("stage") in UPLOADED_STAGES:
                # Its build_dir (and, if it fed the next repo in the chain,
                # chain-after-<repo>) survive on disk, untouched — reuse the
                # already-extracted chain output instead of re-preparing it.
                if i < len(repos) - 1 and repo != "gbif":
                    chain_dir = session_dir / f"chain-after-{repo}"
                    if chain_dir.is_dir():
                        current_input_dir = chain_dir
                continue

            repo_status["status"] = "running"
            input_dirs[repo] = current_input_dir
            build_dir = build_dirs.get(repo) or (session_dir / f"{repo}-build")
            build_dir.mkdir(parents=True, exist_ok=True)
            build_dirs[repo] = build_dir
            _persist()
            await _upload_one(
                cfg, input_dir=current_input_dir, build_dir=build_dir, settings=settings,
                repo_status=repo_status, dry_run=dry_run,
                # media_dir only makes sense for the FIRST repo: from the
                # second one onward, current_input_dir is the previous
                # repo's own build_dir, which already has any local
                # media mirrored into it if applicable (see
                # _extract_chain_input below).
                media_dir=media_dir if i == 0 else None,
                # Unlike media_dir, shared by EVERY repo — each media file
                # then only gets downloaded/copied from its real source once
                # per session, regardless of how many repos mirror it (see
                # _upload_one's own docstring).
                media_cache_dir=session_dir / "media-cache",
            )
            repo_status["stage"] = "uploaded"
            _capture_session_metadata(session_dir, build_dir)
            _capture_repo_record(session_dir, repo, build_dir)
            _cache_checksums(session_dir, repo, build_dir)
            _cache_citation_and_readme(session_dir, repo, build_dir)
            if repo == "gbif" and (current_input_dir / product.METADATA_FILENAME).is_file():
                # Its input_dir is usually the previous repo's
                # chain-after-<repo>, deleted after phase 2 (see
                # _discard_build_artifacts) — the post-lock re-point step
                # still needs this exact metadata.json.
                gbif_meta_dir = _gbif_metadata_dir(session_dir)
                gbif_meta_dir.mkdir(parents=True, exist_ok=True)
                product.copy_metadata_json(current_input_dir, gbif_meta_dir)
            _persist()
            # GBIF never transforms the product (see _upload_one) — the
            # next repo in the chain keeps whatever input the CURRENT one
            # got, rather than trying to extract core files out of GBIF's
            # own (empty) build_dir.
            if i < len(repos) - 1 and repo != "gbif":
                output_mode = cfg.get("output_mode", "prepared")
                if output_mode == "passthrough":
                    # Forward this repo's OWN input unchanged, same as its
                    # own output_dir would (see _finalize_one) — no
                    # transformation of any kind applied, so there's
                    # nothing new to extract; current_input_dir is left as
                    # it already was for this repo's own turn.
                    pass
                elif output_mode == "downloaded" and not dry_run:
                    # Round-trips through the real remote before the next
                    # repo builds on it (see _download_repo_copy) — dry_run
                    # has nothing real to download back, so it falls
                    # through to the same "prepared" extraction as below.
                    downloaded_dir = session_dir / f"{repo}-downloaded"
                    await _download_repo_copy(cfg, session_dir=session_dir, build_dir=build_dir, target_dir=downloaded_dir)
                    chain_dir = session_dir / f"chain-after-{repo}"
                    current_input_dir = await _extract_chain_input(
                        downloaded_dir, chain_dir, metadata_source=build_dir,
                    )
                else:
                    chain_dir = session_dir / f"chain-after-{repo}"
                    current_input_dir = await _extract_chain_input(build_dir, chain_dir, metadata_source=build_dir)

        # Phase 2 already ran to completion before an earlier interruption
        # iff any repo got as far as finalizing — and by then some
        # build_dirs may be gone already (see _discard_build_artifacts),
        # so it must not run again.
        populate_done = any(
            task["repos"][c["repo"]].get("stage") in {"finalizing"} | FINALIZED_STAGES for c in repos
        )
        if not populate_done:
            if not dry_run:
                gbif_status = task["repos"].get("gbif")
                hfh_cfg = next((c for c in repos if c["repo"] == "hfh"), None)
                if (
                    gbif_status and gbif_status.get("doi") and hfh_cfg is not None
                    and gbif_status.get("doi_synced_to_hfh") is None
                ):
                    # BEFORE doi_populate.populate() below, on purpose: this is
                    # what makes GBIF's own DOI claim HFH's top-level "doi"
                    # field FIRST — patch_citation_with_identifier only ever
                    # writes a NEW value there when none is set yet (or it
                    # already matches), so whatever Zenodo/B2SHARE DOI populate()
                    # cross-references into HFH right after this always lands as
                    # a secondary "identifiers" entry instead, never displacing
                    # GBIF's. Also still BEFORE HFH's own tag (phase 3, below):
                    # patches build_dirs["hfh"] and re-uploads straight to HFH's
                    # still-untagged "main", so the tag about to be created
                    # captures a commit that already has GBIF's DOI
                    # cross-referenced into it, instead of tagging first and
                    # leaving the tag stale once main moves on afterward.
                    gbif_cfg = next(c for c in repos if c["repo"] == "gbif")
                    try:
                        # A small, resolved copy (see _resolve_populate_dir) —
                        # not build_dirs["hfh"] directly, since it might not
                        # have CITATION.cff/README.md physically present
                        # anymore by the time this runs. Reused as-is (not
                        # re-resolved) by the populate_dirs built further
                        # below, so THIS patch survives into that later step.
                        hfh_populate_dir = await _resolve_populate_dir(
                            hfh_cfg, session_dir=session_dir, build_dir=build_dirs["hfh"],
                        )
                        hfh_checksums_path = await _get_checksums_for_populate(
                            hfh_cfg, session_dir=session_dir, build_dir=build_dirs["hfh"],
                        )
                        await asyncio.to_thread(
                            gbif_service.sync_doi_to_hfh,
                            gbif_output_dir=Path(gbif_cfg["output_dir"]),
                            hfh_output_dir=hfh_populate_dir,
                            hfh_repo_id=hfh_cfg["repo_id"], hfh_token=hfh_cfg["token"],
                            checksums_path=hfh_checksums_path,
                        )
                        # So _finalize_one's own later "prepared" copy (still
                        # read straight from build_dir) reflects this patch too
                        # — sync_doi_to_hfh only ever wrote to hfh_populate_dir.
                        _copy_populate_patches_back(hfh_populate_dir, hfh_checksums_path, build_dirs["hfh"])
                        gbif_status["doi_synced_to_hfh"] = True
                    except Exception:
                        # Best-effort — the manual "Sync DOI" section is
                        # still there for the user to retry by hand.
                        gbif_status["doi_synced_to_hfh"] = False
                    _persist()

            # GBIF has no CITATION.cff of its own to cross-reference DOIs
            # into (and isn't otherwise integrated into this generic mechanism
            # yet) — excluded here so doi_populate.populate() (which only
            # knows about hfh/zenodo/b2share) never sees it. Its own DOI, when
            # it has one, was already reflected into HFH's CITATION.cff just
            # above, AS THE PRIMARY — any Zenodo/B2SHARE DOI cross-referenced
            # below only ever lands as a secondary "identifiers" entry there,
            # never overwriting it (see the block above's own comment).
            doi_dirs = {repo: d for repo, d in build_dirs.items() if repo != "gbif"}
            # The starting point for each repo's own checksums-sha256.txt
            # update (see _get_checksums_for_populate) — resolved (and, on a
            # cache/build_dir miss, downloaded) ONLY for a repo populate() will
            # actually try to patch: some OTHER repo's identifier to
            # cross-reference (same "is there anything to add" check it does
            # internally) AND an own CITATION.cff that actually exists (same
            # early-return guard common.patch_citation_with_identifier itself
            # uses) — so neither a single-repo run (nothing to cross-reference)
            # nor a repo whose export was never really prepared ever triggers a
            # needless resolution/download.
            identifiers = doi_populate.collect_identifiers(doi_dirs)
            repos_with_candidates = {
                repo for repo, d in doi_dirs.items()
                if any(i.repo != repo for i in identifiers) and (d / "CITATION.cff").is_file()
            }
            checksums_paths = {
                cfg["repo"]: await _get_checksums_for_populate(cfg, session_dir=session_dir, build_dir=doi_dirs[cfg["repo"]])
                for cfg in repos if cfg["repo"] in repos_with_candidates
            }
            # A small, independently-resolved copy per repo (see
            # _resolve_populate_dir) — NOT doi_dirs (raw build_dir) directly,
            # since it might not have CITATION.cff/README.md physically
            # present anymore by the time this runs. EVERY repo in doi_dirs
            # gets one here (not just repos_with_candidates): populate()'s own
            # collect_identifiers(populate_dirs) needs each DOI-providing
            # repo's own record file represented too, even one that isn't
            # itself a patch candidate (e.g. it has no CITATION.cff of its
            # own yet) — only download its CITATION.cff when it IS one (no
            # point in a real remote round-trip otherwise). Reuses HFH's own,
            # if the GBIF-DOI-sync step above already resolved (and patched)
            # it — see that function's own docstring on why re-resolving
            # would silently discard that earlier patch.
            populate_dirs = {
                cfg["repo"]: await _resolve_populate_dir(
                    cfg, session_dir=session_dir, build_dir=doi_dirs[cfg["repo"]],
                    allow_download=cfg["repo"] in repos_with_candidates,
                )
                for cfg in repos if cfg["repo"] in doi_dirs
            }
            changed = await asyncio.to_thread(
                doi_populate.populate, populate_dirs, primary_doi_source=primary_doi_source, checksums_paths=checksums_paths,
            )
            for cfg in repos:
                repo = cfg["repo"]
                if changed.get(repo) and task["repos"][repo].get("stage") != "done":
                    # populate() patched populate_dirs[repo], not build_dir
                    # directly — copy those patches back before re-uploading,
                    # since _reupload_one still re-uploads the WHOLE build_dir
                    # today (see _copy_populate_patches_back's own docstring).
                    _copy_populate_patches_back(populate_dirs[repo], checksums_paths[repo], build_dirs[repo])
                    await _reupload_one(cfg, build_dir=build_dirs[repo], dry_run=dry_run)
            _persist()

        # Finalize (fill each repo's user-facing output_dir) right after
        # the populate broadcast, BEFORE any lock — see _finalize_one's own
        # docstring on why the files can't change past this point anyway.
        previous_output_dir = str(input_dir)
        for cfg in repos:
            repo = cfg["repo"]
            repo_status = task["repos"][repo]
            if repo_status.get("stage") in FINALIZED_STAGES:
                # Already finalized before an earlier interruption — its
                # output_dir already has the final files.
                if repo_status.get("output_dir"):
                    previous_output_dir = repo_status["output_dir"]
                continue
            repo_status["stage"] = "finalizing"
            final_output_dir = await _finalize_one(
                cfg, session_dir=session_dir, build_dir=build_dirs[repo],
                previous_output_dir=previous_output_dir, dry_run=dry_run,
            )
            repo_status["output_dir"] = final_output_dir
            repo_status["stage"] = "finalized"
            previous_output_dir = final_output_dir
            _discard_build_artifacts(session_dir, repo, build_dirs.pop(repo, None))
            _persist()
        # Shared by every repo's own mirroring (see _upload_one) — nothing
        # past this point uploads anything anymore.
        shutil.rmtree(session_dir / "media-cache", ignore_errors=True)

        for cfg in repos:
            repo = cfg["repo"]
            repo_status = task["repos"][repo]
            if repo_status.get("stage") == "done":
                continue
            await _lock_one(
                cfg, session_dir=session_dir, build_dir=build_dirs.get(repo) or session_dir / f"{repo}-build",
                repo_status=repo_status, dry_run=dry_run,
            )
            repo_status["status"] = "done"
            repo_status["stage"] = "done"
            _persist()

        if not dry_run:
            gbif_cfg = next((c for c in repos if c["repo"] == "gbif"), None)
            gbif_status = task["repos"].get("gbif")
            hfh_cfg = next((c for c in repos if c["repo"] == "hfh"), None)
            if (
                gbif_cfg is not None and gbif_status is not None and hfh_cfg is not None
                and gbif_status.get("archive_repointed_to_tag") is None
            ):
                # AFTER HFH's own tag (just created above) — re-points
                # GBIF's endpoint away from HFH's floating "main" branch to
                # that tag's own permanent URL, via a second call to the
                # same register_gbif_dataset (matched to the SAME dataset
                # by its own dataset_key fallback — see _register_gbif).
                try:
                    version = await asyncio.to_thread(
                        _read_hfh_version, build_dirs.get("hfh") or session_dir / "hfh-build", session_dir,
                    )
                    tag_archive_url = _archive_url_for_tag(gbif_cfg["archive_url"], version)
                    gbif_meta_dir = _gbif_metadata_dir(session_dir)
                    if tag_archive_url is None:
                        # Not one of HFH's own resolve URLs (a manually
                        # provided external archive) — nothing to re-point.
                        gbif_status["archive_repointed_to_tag"] = False
                    else:
                        await _register_gbif(
                            {**gbif_cfg, "archive_url": tag_archive_url},
                            input_dir=gbif_meta_dir if gbif_meta_dir.is_dir() else input_dirs["gbif"],
                            repo_status=gbif_status, dry_run=False,
                        )
                        gbif_status["archive_repointed_to_tag"] = True
                except Exception:
                    # Best-effort — GBIF's dataset still resolves fine
                    # against "main" in the meantime; nothing else depends
                    # on this having succeeded.
                    gbif_status["archive_repointed_to_tag"] = False
                _persist()

        task["status"] = "done"
    except Exception as exc:
        task["status"] = "error"
        task["error"] = str(exc)
        for repo, repo_status in task["repos"].items():
            if repo_status["status"] == "running":
                repo_status["status"] = "error"
                repo_status["error"] = str(exc)
        _persist()
    finally:
        # Only a fully successful task deletes its own session — an
        # interrupted one stays on disk on purpose, for resume_publish_all_task.
        if task["status"] == "done":
            shutil.rmtree(session_dir, ignore_errors=True)


def _default_primary_doi_source(input_dir: Path, repos: list[dict]) -> str | None:
    """HFH's primary DOI when the caller didn't choose one: for every
    product type except Camtrap DP (whose wizard still asks), Zenodo's if
    it's part of the run, else B2SHARE's. None otherwise — including when
    input_dir has no readable metadata.json yet — which leaves
    doi_populate.populate's own single-candidate fallback in charge."""
    try:
        product_type = product.read_metadata_json(input_dir)["product_type"]
    except RuntimeError:
        return None
    if product_type == product.CAMTRAPDP:
        return None
    selected = {cfg["repo"] for cfg in repos}
    return next((repo for repo in ("zenodo", "b2share") if repo in selected), None)


def start_publish_all_task(
    *, input_dir: Path, repos: list[dict], primary_doi_source: str | None, dry_run: bool = False,
    media_dir: Path | None = None, task_id: str | None = None,
) -> str:
    """`task_id`, when given, reuses a session an earlier fetch/preprocess
    phase already created (see session_store's own docstring) instead of
    minting a fresh one with uuid4() — everything about that run (its
    fetched source, its preprocessing choices) then lives under the same
    session_dir as this publish. Absent (the default), or naming a task_id
    with no session on disk yet, behaves exactly as before: a brand new
    session, e.g. for a Local Directory source (out of scope for this
    mechanism) or any caller that predates it."""
    task_id = task_id or str(uuid.uuid4())
    primary_doi_source = primary_doi_source or _default_primary_doi_source(input_dir, repos)
    _publish_tasks[task_id] = {
        "status": "running", "dry_run": dry_run,
        "repos": {cfg["repo"]: _initial_repo_status() for cfg in repos},
    }
    settings = load_settings()
    asyncio.create_task(_run(
        task_id, input_dir=input_dir, repos=repos, primary_doi_source=primary_doi_source,
        dry_run=dry_run, media_dir=media_dir, settings=settings, resume=False,
    ))
    return task_id


def resume_publish_all_task(task_id: str, repos: list[dict]) -> str:
    """Resumes a publish session left on disk by an earlier interrupted run
    (see list_unfinished_sessions) — `repos` must name the very same repos,
    in the same order, as the original run, but with fresh credentials
    (session.json never stores token/password — see _scrub_secrets)."""
    manifest = session_store.read_manifest(task_id)
    if manifest is None or "repos" not in manifest:
        # Either no session at all, or one that never reached the publish
        # phase yet (still fetching/preprocessing — see session_store's own
        # docstring) — nothing to resume publishing here either way.
        raise RuntimeError(f"No interrupted publish session found for task {task_id!r}.")

    original_repo_order = [r["repo"] for r in manifest["repos"]]
    new_repo_order = [cfg["repo"] for cfg in repos]
    if new_repo_order != original_repo_order:
        raise RuntimeError(
            f"This session was for repos {original_repo_order} — got {new_repo_order}. Resume "
            "with the exact same repos, in the same order, as the original run."
        )

    dry_run = manifest["dry_run"]
    primary_doi_source = manifest.get("primary_doi_source")
    input_dir = Path(manifest["input_dir"])
    media_dir = Path(manifest["media_dir"]) if manifest.get("media_dir") else None

    repo_status = manifest["repo_status"]
    for status in repo_status.values():
        if status["status"] == "running":
            # Was mid-flight when the process died — treat as not-yet-done
            # so _run re-processes it (uploads/downloads resume from
            # whatever's already on disk / already at the remote).
            status["status"] = "pending"
            status["error"] = None

    _publish_tasks[task_id] = {
        "status": "running", "dry_run": dry_run, "created_at": manifest["created_at"], "repos": repo_status,
    }
    settings = load_settings()
    asyncio.create_task(_run(
        task_id, input_dir=input_dir, repos=repos, primary_doi_source=primary_doi_source,
        dry_run=dry_run, media_dir=media_dir, settings=settings, resume=True,
    ))
    return task_id
