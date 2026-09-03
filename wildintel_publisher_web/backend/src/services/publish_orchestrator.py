"""Orchestrates publishing the same product to several repos in one go —
the web wizard's own version of "publish all", now with a cross-repo DOI
populate step wired in between uploading and locking (see
wildintel_publisher.services.doi_populate for the generic
cross-referencing logic).

Flow, for `repos` (an ORDERED list of already-configured
{"repo": "hfh"|"zenodo"|"b2share", ...} dicts — see schemas.requests.
RepoPublishConfig):

  1. Upload phase — prepare + upload every repo, ONE AFTER ANOTHER (each
     one's own build directory becomes the next one's input, same
     chaining the wizard used to do itself before this module existed).
     Whichever repos provide their own DOI (PROVIDES_DOI — Zenodo/B2SHARE)
     already reserve it here, same as 'zenodo upload'/'b2share upload' on
     the CLI.
  2. Populate phase — doi_populate.populate() cross-references whatever
     DOI got reserved above into every OTHER repo's own CITATION.cff (as
     an alternate identifier, or as the primary one for HFH, which never
     has a DOI of its own — see primary_doi_source). Any repo whose files
     actually changed gets re-uploaded (same upload_to_X call as phase 1,
     reusing the same draft/deposition/repository).
  3. Lock phase — release_on_zenodo/release_on_b2share/
     tag_release_on_huggingface+release_on_huggingface for every repo, in
     order — only now, once every cross-reference has already landed.

Only after step 3 are the product's own core files copied into each
repo's user-configured output_dir (see copy_prepared_output_files) and the
throwaway build directories deleted.

GBIF is not like the other three: it never prepares or uploads any files of
its own — it only registers, in GBIF's Registry, a dataset whose CAMTRAP_DP
endpoint points at a URL where the Camtrap DP is already hosted elsewhere
(archive_url, typically another repo in the same `repos` list, once THAT
one has published). So for repo == "gbif": phase 1 (_upload_one) is a
no-op, it's excluded from the DOI cross-referencing dict entirely (it has no
CITATION.cff of its own), and phase 3 (_lock_one) is where its one real
network call happens — directly against its user-configured output_dir
(there's nothing to stage in a temporary build_dir first, unlike the other
three).

Unlike Zenodo/B2SHARE (whose DOI/PID is already known before HFH ever gets
tagged, so the populate phase cross-references it into HFH's CITATION.cff
for free, within phase 2), GBIF only learns its own DOI (if any — most
organizations don't get one auto-minted, see gbif.register_gbif_dataset)
during its own phase-3 lock call, which always runs after HFH's — so once
every repo's phase 3 has run, if HFH was part of this same run and GBIF's
came back with a DOI, it's synced into HFH's already-published CITATION.cff
as one extra best-effort step (same gbif_service.sync_doi_to_hfh the
wizard's manual "Sync DOI" section calls) — no separate user action needed
for the common case. That manual section stays as a fallback for whenever
this can't happen automatically (GBIF published standalone, without HFH in
the same run) or if the automatic attempt itself failed.

Dry run (dry_run=True on start_publish_all_task): every step above still
runs, EXCEPT the actual network upload/release calls to Zenodo/B2SHARE/HFH,
which are replaced by the _dry_run_* helpers below — a synthetic record
(fake-but-well-formed DOI/PID) is written to disk instead of a real one, so
the populate phase's cross-referencing logic runs completely for real
against it. prepare_*_export (local file generation) and doi_populate.
populate() itself are never mocked — only the network boundary is."""
from __future__ import annotations

import asyncio
import json
import random
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from wildintel_publisher.config import load_settings
from wildintel_publisher.services import b2share as b2share_cli
from wildintel_publisher.services import doi_populate
from wildintel_publisher.services import gbif as gbif_cli
from wildintel_publisher.services import hfh as hfh_cli
from wildintel_publisher.services import product
from wildintel_publisher.services import zenodo as zenodo_cli

from services import b2share_service, camtrapdp_service, gbif_service, hfh_service, zenodo_service

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
        # gbif only: None until its own lock phase runs; then True/False once
        # an auto-sync into HFH's CITATION.cff was actually attempted (see
        # the sync step after the main per-repo loop in start_publish_all_task).
        "doi_synced_to_hfh": None,
    }


def get_publish_task_status(task_id: str) -> dict[str, Any] | None:
    return _publish_tasks.get(task_id)


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
) -> None:
    """Phase 1 (and re-run as-is during phase 2 for a changed repo, minus
    the 'preparing' half — see _reupload_one): prepare + upload a single
    repo into its own build_dir.

    prepare_*_export always runs for real, dry_run or not — it's pure local
    file generation (no network), and it's what gives doi_populate() and the
    UI real files to work with. Only the actual network upload is
    swapped out for a simulated one in dry_run (see the _dry_run_* helpers)."""
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
            mirror_images=cfg["mirror_images"],
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
        # Nothing to prepare/upload — see the module's own docstring. Its
        # one real network call happens later, in _lock_one.
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
        )
        repo_status["stage"] = "uploading"
        if dry_run:
            record = _dry_run_zenodo_record(cfg)
            (build_dir / zenodo_cli.RECORD_FILENAME).write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            await asyncio.to_thread(
                zenodo_cli.upload_to_zenodo, build_dir, token=cfg["token"], environment=cfg["environment"],
                communities=cfg.get("communities"), hfh_repo_id=hfh_repo_id,
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
        )
        repo_status["stage"] = "uploading"
        if dry_run:
            record = _dry_run_b2share_record(cfg)
            (build_dir / b2share_cli.RECORD_FILENAME).write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            await asyncio.to_thread(
                b2share_cli.upload_to_b2share, build_dir, token=cfg["token"], environment=cfg["environment"],
                community_id=cfg["community_id"], hfh_repo_id=hfh_repo_id,
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


async def _lock_one(cfg: dict, *, input_dir: Path, build_dir: Path, repo_status: dict, dry_run: bool) -> None:
    """Phase 3: release_on_zenodo/release_on_b2share, or
    tag_release_on_huggingface+release_on_huggingface for HFH — or, for
    GBIF, the one and only network call it ever makes (see the module's own
    docstring).

    In dry_run, Zenodo/B2SHARE just flip their own simulated record's
    "published" flag (same doi/pid reserved back in _upload_one — a real
    release never changes the identifier, just publishes it); HFH has
    nothing to tag/release for real, so repo_status is filled from the
    repo_url _dry_run_upload_hfh already set; GBIF fakes a plausible
    dataset_page_url instead of calling the Registry API.

    `input_dir` is this repo's OWN input directory, as of its own turn in the
    chain (see _run's `input_dirs`) — only GBIF reads it, for the product's
    title/description/license/homepage, since its own build_dir was never
    populated (see _upload_one). Deliberately NOT the publish task's
    original input_dir: if a repo publishing in mirror mode ahead of GBIF
    (e.g. HFH) already set metadata.json's own "homepage" (see
    product.write_homepage), that update lives in the chained copy, not the
    original — reading the original here would send GBIF's registration a
    stale/missing homepage even though the run just set a real one."""
    repo = cfg["repo"]
    repo_status["stage"] = "releasing"
    if repo == "hfh":
        if dry_run:
            return
        meta = await asyncio.to_thread(product.read_metadata_json, build_dir)
        version = meta.get("version") or hfh_cli.DEFAULT_VERSION
        await asyncio.to_thread(
            hfh_cli.tag_release_on_huggingface, repo_id=cfg["repo_id"], token=cfg["token"], version=version,
        )
        await asyncio.to_thread(
            hfh_cli.release_on_huggingface, repo_id=cfg["repo_id"], token=cfg["token"],
            dry_run=False, verify_only=False,
        )
    elif repo == "zenodo":
        if dry_run:
            record_path = build_dir / zenodo_cli.RECORD_FILENAME
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["published"] = True
            record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            record = await asyncio.to_thread(zenodo_cli.release_on_zenodo, build_dir, token=cfg["token"])
        repo_status["doi"] = record.get("doi")
        repo_status["repo_url"] = record.get("record_url")
    elif repo == "b2share":
        if dry_run:
            record_path = build_dir / b2share_cli.RECORD_FILENAME
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["published"] = True
            record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        else:
            record = await asyncio.to_thread(b2share_cli.release_on_b2share, build_dir, token=cfg["token"])
        repo_status["pid"] = record.get("pid")
        repo_status["repo_url"] = record.get("record_url")
    elif repo == "gbif":
        if dry_run:
            dataset_key = f"dry-run-{_dry_run_id()}"
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
        )
        repo_status["repo_url"] = record.get("dataset_page_url")
        # Only some organizations have their own DataCite arrangement
        # configured with GBIF, which makes it auto-mint one — see
        # gbif.register_gbif_dataset. None otherwise, same as HFH's own
        # doi field, which the frontend already treats as "nothing to sync".
        repo_status["doi"] = record.get("doi")


async def _extract_chain_input(build_dir: Path) -> Path:
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
    extract_core_files)."""
    meta = await asyncio.to_thread(product.read_metadata_json, build_dir)
    adapter = product.get_adapter(meta["product_type"])
    chain_dir = Path(tempfile.mkdtemp(prefix="chain-"))
    await asyncio.to_thread(adapter.extract_core_files, build_dir, chain_dir)
    await asyncio.to_thread(product.copy_metadata_json, build_dir, chain_dir)
    return chain_dir


async def _finalize_one(cfg: dict, *, build_dir: Path, previous_output_dir: str, dry_run: bool) -> str:
    """Copies the product's own core files (see each web service's own
    copy_prepared_output_files) into this repo's user-configured
    output_dir, then resolves output_mode — same three choices each
    single-repo publish endpoint already offered, just computed here since
    chaining is now internal (see the module's own docstring).

    output_mode == "downloaded" means "fetch a fresh copy back from the
    repo" — meaningless in dry_run (nothing was actually uploaded there to
    fetch back), so it falls through to the same result as "prepared"
    instead of hitting the network."""
    repo = cfg["repo"]
    output_dir = Path(cfg["output_dir"])
    output_mode = cfg.get("output_mode", "prepared")

    if repo == "gbif":
        # register_gbif_dataset already wrote gbif_linked_dataset_record.json
        # straight into output_dir itself (see _lock_one) — there's no
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
        if repo == "hfh":
            await asyncio.to_thread(hfh_service.download_from_repo, repo_id=cfg["repo_id"], token=cfg["token"], target_dir=download_dir)
            return str(download_dir)
        if repo == "zenodo":
            record = json.loads((build_dir / zenodo_cli.RECORD_FILENAME).read_text(encoding="utf-8"))
            await asyncio.to_thread(
                zenodo_service.download_files_from_zenodo, environment=cfg["environment"],
                deposition_id=record["deposition_id"], token=cfg["token"], target_dir=download_dir,
            )
            return str(download_dir)
        if repo == "b2share":
            record = json.loads((build_dir / b2share_cli.RECORD_FILENAME).read_text(encoding="utf-8"))
            if record.get("pid"):
                await asyncio.to_thread(
                    b2share_service.download_files_from_b2share, environment=cfg["environment"],
                    record_id=record["record_id"], token=cfg["token"], target_dir=download_dir,
                )
                return str(download_dir)
    return str(output_dir)


def start_publish_all_task(
    *, input_dir: Path, repos: list[dict], primary_doi_source: str | None, dry_run: bool = False,
) -> str:
    task_id = str(uuid.uuid4())
    _publish_tasks[task_id] = {
        "status": "running", "dry_run": dry_run,
        "repos": {cfg["repo"]: _initial_repo_status() for cfg in repos},
    }
    settings = load_settings()

    async def _run() -> None:
        build_dirs: dict[str, Path] = {}
        chain_dirs: list[Path] = []
        # Each repo's own input_dir, as of its OWN turn in the chain — GBIF's
        # is what matters most, since its build_dir is never populated (see
        # _upload_one) and _lock_one falls back to reading metadata.json from
        # here instead; a repo publishing in mirror mode ahead of it (e.g.
        # HFH) may have just updated metadata.json's own "homepage" (see
        # product.write_homepage), and that update only reaches this dict's
        # entry, never the very first input_dir.
        input_dirs: dict[str, Path] = {}
        try:
            current_input_dir = input_dir
            for i, cfg in enumerate(repos):
                repo = cfg["repo"]
                repo_status = _publish_tasks[task_id]["repos"][repo]
                repo_status["status"] = "running"
                input_dirs[repo] = current_input_dir
                build_dir = Path(tempfile.mkdtemp(prefix=f"{repo}-build-"))
                build_dirs[repo] = build_dir
                await _upload_one(
                    cfg, input_dir=current_input_dir, build_dir=build_dir, settings=settings,
                    repo_status=repo_status, dry_run=dry_run,
                )
                # GBIF never transforms the product (see _upload_one) — the
                # next repo in the chain keeps whatever input the CURRENT one
                # got, rather than trying to extract core files out of GBIF's
                # own (empty) build_dir.
                if i < len(repos) - 1 and repo != "gbif":
                    current_input_dir = await _extract_chain_input(build_dir)
                    chain_dirs.append(current_input_dir)

            # GBIF has no CITATION.cff of its own to cross-reference DOIs
            # into — excluded here so doi_populate.populate() (which only
            # knows about hfh/zenodo/b2share) never sees it.
            doi_dirs = {repo: d for repo, d in build_dirs.items() if repo != "gbif"}
            changed = await asyncio.to_thread(doi_populate.populate, doi_dirs, primary_doi_source=primary_doi_source)
            for cfg in repos:
                if changed.get(cfg["repo"]):
                    await _reupload_one(cfg, build_dir=build_dirs[cfg["repo"]], dry_run=dry_run)

            previous_output_dir = str(input_dir)
            for cfg in repos:
                repo = cfg["repo"]
                repo_status = _publish_tasks[task_id]["repos"][repo]
                build_dir = build_dirs[repo]
                await _lock_one(cfg, input_dir=input_dirs[repo], build_dir=build_dir, repo_status=repo_status, dry_run=dry_run)
                final_output_dir = await _finalize_one(
                    cfg, build_dir=build_dir, previous_output_dir=previous_output_dir, dry_run=dry_run,
                )
                repo_status["output_dir"] = final_output_dir
                repo_status["status"] = "done"
                repo_status["stage"] = "done"
                previous_output_dir = final_output_dir

            if not dry_run:
                gbif_status = _publish_tasks[task_id]["repos"].get("gbif")
                hfh_cfg = next((c for c in repos if c["repo"] == "hfh"), None)
                if gbif_status and gbif_status.get("doi") and hfh_cfg is not None:
                    gbif_cfg = next(c for c in repos if c["repo"] == "gbif")
                    try:
                        await asyncio.to_thread(
                            gbif_service.sync_doi_to_hfh,
                            gbif_output_dir=Path(gbif_cfg["output_dir"]),
                            hfh_output_dir=Path(hfh_cfg["output_dir"]),
                            hfh_repo_id=hfh_cfg["repo_id"], hfh_token=hfh_cfg["token"],
                        )
                        gbif_status["doi_synced_to_hfh"] = True
                    except Exception:
                        # Best-effort — the manual "Sync DOI" section is
                        # still there for the user to retry by hand.
                        gbif_status["doi_synced_to_hfh"] = False

            _publish_tasks[task_id]["status"] = "done"
        except Exception as exc:
            _publish_tasks[task_id]["status"] = "error"
            _publish_tasks[task_id]["error"] = str(exc)
            for repo, repo_status in _publish_tasks[task_id]["repos"].items():
                if repo_status["status"] == "running":
                    repo_status["status"] = "error"
                    repo_status["error"] = str(exc)
        finally:
            for build_dir in build_dirs.values():
                shutil.rmtree(build_dir, ignore_errors=True)
            for chain_dir in chain_dirs:
                shutil.rmtree(chain_dir, ignore_errors=True)

    asyncio.create_task(_run())
    return task_id
