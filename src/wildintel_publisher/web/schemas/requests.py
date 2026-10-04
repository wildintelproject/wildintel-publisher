from typing import Any, Literal, Optional

from pydantic import BaseModel

from wildintel_publisher.core.services.product import ProductAuthor, ProductLicense
from wildintel_publisher.core.services.yolo_adapter import YoloEditableMetadata

# What ends up in a publish task's final output_dir, used by the frontend to
# chain the next repo's inputDir (see services.hfh_service.start_publish_task
# and its zenodo_service/b2share_service counterparts):
# - "prepared" (default): only the core Camtrap DP files (datapackage.json/
#   deployments.csv/media.csv/observations.csv), with prepare/upload's
#   modifications applied — none of the repo-specific extras (README,
#   LICENSE, CITATION.cff, checksums, images/, zip) that were also written to
#   the local staging directory.
# - "passthrough": input_dir itself, unchanged — nothing new is written.
# - "downloaded": a fresh copy downloaded back from the repo after a
#   successful upload.
OutputMode = Literal["prepared", "passthrough", "downloaded"]


class TrapperCredentials(BaseModel):
    # All optional: a blank field means "use what's already saved in
    # settings.toml" — see services.trapper_service.resolve_credentials.
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class ClassificationProjectsRequest(TrapperCredentials):
    research_project_pk: int


class DeploymentsRequest(TrapperCredentials):
    classification_project_pk: int


class DownloadRequest(TrapperCredentials):
    project_id: int
    deployment_id: str
    clear_cache: bool = False
    # Whether the generated package includes event-level (aggregated)
    # observations, in addition to the media-level ones — Trapper's own API
    # defaults this to false; wildintel-publisher defaults it to true
    # instead (see services.trapper.fetch_camtrapdp_package).
    include_events: bool = True


class OpenFolderRequest(BaseModel):
    path: str


class SoftwareCloneRequest(BaseModel):
    url: str
    # If true, discards any previously cloned copy at the derived
    # destination and re-clones from scratch (see services.git_source.
    # clone_repository) — same "clear_cache" contract DownloadRequest's own
    # flag has for Trapper.
    clear_cache: bool = False


class CamtrapDPArchiveFetchRequest(BaseModel):
    url: str
    # If true, discards any previously fetched extraction at the derived
    # destination and re-fetches from scratch (see services.camtrapdp_source.
    # fetch_camtrap_dp_archive) — same "clear_cache" contract as Trapper's/
    # software's own source-fetching requests.
    clear_cache: bool = False


class LocalSourceResolveRequest(BaseModel):
    # Raw path the user typed/picked for a local Camtrap DP source — never
    # used directly as input_dir afterwards (see services.camtrapdp_source.
    # resolve_local_camtrapdp_source): only its core files get copied into a
    # working directory the app owns, so later steps (generate-metadata's
    # anonymize/randomize, which mutate their input in place) never touch
    # this original path.
    path: str
    # The session an earlier call for THIS SAME form already minted (see
    # services.camtrapdp_source_service.resolve_local_source) — reused so
    # every re-resolve while the user is still typing/editing the path (see
    # the frontend's own debounced live-preview) lands in the same
    # session_dir instead of minting a fresh one per keystroke. None on the
    # very first call for a given LocalDirectoryForm instance.
    session_task_id: Optional[str] = None


class GenerateMetadataRequest(BaseModel):
    # Which services.product.ProductAdapter to validate/extract metadata
    # with — "camtrapdp" or "yolo" today (see services.product.get_adapter).
    input_dir: str
    product_type: str
    # Camtrap DP only — rounds deployments.csv's latitude/longitude to
    # coordinate_decimals places, in input_dir itself, before metadata is
    # extracted. A privacy option for sensitive camera-trap locations,
    # applied once here (a product-level preprocessing step) so every repo
    # that later prepares its own export from this same input_dir inherits
    # the same already-anonymized coordinates automatically. See
    # wildintel_publisher.core.services.common.anonymize_deployment_coordinates.
    anonymize_coordinates: bool = False
    coordinate_decimals: int = 2
    # Camtrap DP only — replaces every mediaID in media.csv (and matching
    # observations.csv references) that isn't already a UUID with one
    # derived from media_id_domain, in input_dir itself, before metadata is
    # extracted. Same "applied once here" shape as anonymize_coordinates,
    # and just as safe to call again later (a mediaID that's already a UUID
    # is left alone). See wildintel_publisher.core.services.common.randomize_media_ids.
    randomize_media_ids: bool = False
    # Namespace for the UUIDs randomize_media_ids derives — typically the
    # domain of the Trapper server or public URL this product came from
    # (the wizard auto-fills this from the chosen source), so two different
    # sources' own numbering never collides. "localhost" by default for a
    # local-directory source, where there's no server domain to use.
    media_id_domain: str = "localhost"
    # The session a prior Trapper/git/archive fetch — or a Local Directory
    # resolve — started (see services.session_store). None only for a
    # request that predates this feature. When given, flips that session's
    # own phase to "preprocessing"/"preprocessed" (see
    # services.camtrapdp_service.generate_metadata's router).
    session_task_id: Optional[str] = None


class UpdateMetadataRequest(BaseModel):
    # Fills in whatever generate-metadata's best-effort extraction couldn't
    # determine from the product itself (see
    # services.product.missing_required_fields) — only the fields the
    # caller actually provides get merged into the existing metadata.json.
    input_dir: str
    title: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    license: Optional[ProductLicense] = None
    authors: Optional[list[ProductAuthor]] = None
    homepage: Optional[str] = None


class UpdateDatapackageRequest(BaseModel):
    # Camtrap DP only — patches datapackage.json ITSELF (not metadata.json,
    # see UpdateMetadataRequest above) with whatever fields the caller
    # provides, only those. Meant to run BEFORE generate-metadata (see
    # /generate-metadata below): CamtrapDPAdapter.extract_metadata re-reads
    # these same fields from datapackage.json every time it runs, so
    # patching first is enough for metadata.json (and everything generated
    # from it — README.md, CITATION.cff, Zenodo/B2SHARE/HFH records) to pick
    # up the new values with no separate sync step. See
    # wildintel_publisher.core.services.common.update_datapackage_fields.
    input_dir: str
    # Data Package's own machine-readable slug identifier — distinct from
    # "title" (the human-readable one) and not part of metadata.json's own
    # schema, since nothing in the publish pipeline reads it from there.
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    homepage: Optional[str] = None
    version: Optional[str] = None
    # The full contributors array, sent back as-is except for whatever the
    # wizard's "change role only" editor actually changed — each entry is
    # datapackage.json's own contributor object (title/email/organization/
    # role/...) untouched, so nothing beyond role is ever lost on round-trip.
    # Not validated against Camtrap DP's 5-value role enum here — the
    # frontend's <select> already constrains it to a valid value.
    contributors: Optional[list[dict[str, Any]]] = None


class UpdateDataYamlRequest(YoloEditableMetadata):
    # YOLO only — the working copy's own data.yaml (see
    # services.yolo_service.resolve_local_source), never the user's
    # original. Every YoloEditableMetadata field is sent, always: an empty
    # one removes that key from data.yaml.
    input_dir: str

    def fields(self) -> YoloEditableMetadata:
        return YoloEditableMetadata.model_validate(self.model_dump(exclude={"input_dir"}))


class HFHTestTokenRequest(BaseModel):
    # Blank means "use what's already saved in settings.toml" — see
    # services.hfh_service.resolve_token.
    repo_id: Optional[str] = None
    token: Optional[str] = None
    # If given together with repo_id, checks upfront whether this version
    # was already published there (see services.hfh_service.test_token) —
    # just a heads-up, publishing still enforces it for real.
    version: Optional[str] = None


class HFHPublishRequest(BaseModel):
    input_dir: str
    output_dir: Optional[str] = None
    version: Optional[str] = None
    timeout: Optional[int] = None
    repo_id: Optional[str] = None
    private: bool = True
    token: Optional[str] = None
    # mirror (default): downloads/uploads the images and rewrites media.csv's
    # filePath to point to them. link: leaves media.csv untouched.
    mirror_images: bool = True
    output_mode: OutputMode = "prepared"


class ZenodoTestTokenRequest(BaseModel):
    # Blank means "use what's already saved in settings.toml" — see
    # services.zenodo_service.resolve_token.
    token: Optional[str] = None
    environment: Optional[str] = None


class ZenodoPublishRequest(BaseModel):
    input_dir: str
    output_dir: Optional[str] = None
    version: Optional[str] = None
    timeout: Optional[int] = None
    # mirror: downloads the public images and bundles them inside Zenodo's
    # own camtrapdp.zip (self_contained=True). link: doesn't download
    # anything — rewrites media.csv's filePath to hfh_repo_id's HuggingFace
    # Hub URLs (self_contained=False). Mirrors the same two-mode choice as
    # HFH's own mirror_images.
    mirror_images: bool = True
    hfh_repo_id: Optional[str] = None
    environment: Optional[str] = None
    communities: Optional[str] = None
    token: Optional[str] = None
    output_mode: OutputMode = "prepared"


class S3TestConnectionRequest(BaseModel):
    # Blank credentials mean "the ones saved for remote_id" (or, failing
    # that, the S3_ACCESS_KEY/S3_SECRET_KEY environment variables) — see
    # services.s3_service.resolve_credentials. Lets the settings page test a
    # remote's form before it's saved.
    remote_id: Optional[str] = None
    endpoint_url: Optional[str] = None
    region: Optional[str] = None
    bucket: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    verify_ssl: Optional[bool] = None


class S3UploadRequest(BaseModel):
    """Starts the image download+upload step (see
    services.s3_service.start_upload_task) against input_dir — the wizard
    sends it right after the metadata step has been applied, before the user
    chooses where to publish. The connection is the saved remote remote_id
    (settings page); retries follow S3Settings.retry_attempts/
    retry_wait_seconds."""
    input_dir: str
    remote_id: str
    # Where media.csv's locally-referenced (non-URL) filePath entries live,
    # when that isn't input_dir itself — a local Camtrap DP source, where
    # input_dir is only a working copy of the core files (same meaning as
    # PublishAllRequest.media_dir). None for every other source type.
    media_dir: Optional[str] = None
    # Downloads/hashes/rewrites for real, but uploads nothing — the status's
    # "log" lists each file and the object key it would get.
    dry_run: bool = False


class ZenodoSyncDoiRequest(BaseModel):
    zenodo_output_dir: str
    hfh_output_dir: str
    hfh_repo_id: str
    hfh_token: Optional[str] = None


class ZenodoDepositionsRequest(BaseModel):
    """See services.zenodo.search_my_depositions — ZenodoPublishForm's own
    "Search existing depositions" button, so the user can pick an
    existing_deposition_id instead of typing/tracking a numeric id by hand.
    Unlike GBIF's public Registry search (scoped by organization_key),
    Zenodo's deposit API is always scoped to the caller's own token."""
    environment: str
    # Blank means "use what's already saved in settings.toml" — see
    # services.zenodo_service.resolve_token.
    token: Optional[str] = None
    query: Optional[str] = None


class B2ShareTestTokenRequest(BaseModel):
    # Blank means "use what's already saved in settings.toml" — see
    # services.b2share_service.resolve_token.
    token: Optional[str] = None
    environment: Optional[str] = None


class B2SharePublishRequest(BaseModel):
    input_dir: str
    output_dir: Optional[str] = None
    version: Optional[str] = None
    timeout: Optional[int] = None
    # mirror: downloads the public images and bundles them inside B2SHARE's
    # own camtrapdp.zip (self_contained=True, exactly like Zenodo — B2SHARE
    # caps each record at 100 files, so images can't be uploaded loose).
    # link: doesn't download anything — rewrites media.csv's filePath to
    # hfh_repo_id's HuggingFace Hub URLs (self_contained=False).
    mirror_images: bool = True
    hfh_repo_id: Optional[str] = None
    environment: Optional[str] = None
    community_id: Optional[str] = None
    token: Optional[str] = None
    output_mode: OutputMode = "prepared"


class B2ShareSyncPidRequest(BaseModel):
    b2share_output_dir: str
    hfh_output_dir: str
    hfh_repo_id: str
    hfh_token: Optional[str] = None


class B2ShareRecordsRequest(BaseModel):
    """See services.b2share.search_my_records — B2SharePublishForm's own
    "Search existing records" button, so the user can pick an
    existing_record_id instead of typing/tracking one by hand. Unlike
    GBIF's public Registry search (scoped by organization_key), B2SHARE's
    (InvenioRDM) user-records API is always scoped to the caller's own
    token."""
    environment: str
    # Blank means "use what's already saved in settings.toml" — see
    # services.b2share_service.resolve_token.
    token: Optional[str] = None
    query: Optional[str] = None


class GBIFTestCredentialsRequest(BaseModel):
    # Blank means "use what's already saved in settings.toml" — see
    # services.gbif_service.resolve_credentials.
    username: Optional[str] = None
    password: Optional[str] = None
    environment: Optional[str] = None


class GBIFValidateArchiveRequest(BaseModel):
    # See services.gbif.validate_camtrap_dp_archive — downloads this URL,
    # checks it's a zip, and validates the extracted Camtrap DP against the
    # official schema, catching upfront the exact failure GBIF's own
    # CAMTRAP_DP crawler otherwise hits silently (ABORT, nothing indexed).
    archive_url: str


class GBIFSyncDoiRequest(BaseModel):
    gbif_output_dir: str
    hfh_output_dir: str
    hfh_repo_id: str
    hfh_token: Optional[str] = None


class RepoPublishConfig(BaseModel):
    """One repo's worth of already-collected configuration — the wizard
    gathers one of these per selected repo (see each PublishForm's
    onConfigured) before starting the actual multi-repo publish (see
    PublishAllRequest/services.publish_orchestrator). hfh_repo_id is
    deliberately absent: in link mode it's resolved live, right before that
    repo's own turn to prepare/upload, from whatever the PREVIOUS repo in
    `repos` actually published (see services.publish_orchestrator) — it
    can't be known ahead of time the way it could when each repo published
    fully on its own, one at a time.

    GBIF never uploads or hosts anything of its own — unlike hfh/zenodo/
    b2share it doesn't prepare a build directory, and archive_url must
    already point somewhere public (typically another repo in this same
    list, once it has published — the wizard prefills it from HFH's repo_id
    when available, see WizardPage's suggestedArchiveUrl)."""
    repo: Literal["hfh", "zenodo", "b2share", "gbif"]
    output_dir: Optional[str] = None
    token: Optional[str] = None
    mirror_images: bool = True
    output_mode: OutputMode = "prepared"
    # hfh-only
    repo_id: Optional[str] = None
    private: bool = True
    # zenodo/b2share
    environment: Optional[str] = None
    communities: Optional[str] = None  # zenodo
    community_id: Optional[str] = None  # b2share
    # zenodo-only — numeric id of an already-published Zenodo deposition to
    # create a proper linked NEW VERSION of (see
    # wildintel_publisher.core.services.zenodo.upload_to_zenodo's own docstring),
    # instead of an unrelated fresh deposition. Only consulted the first
    # time (no zenodo_record.json yet under this repo's own output_dir).
    # None (the default) creates a brand new deposition, same as before this
    # field existed — see ZenodoPublishForm.tsx's own search button.
    existing_deposition_id: Optional[str] = None
    # b2share-only — id of an already-published B2SHARE record to create a
    # proper linked NEW VERSION of (see
    # wildintel_publisher.core.services.b2share.upload_to_b2share's own
    # docstring), instead of an unrelated fresh draft. Only consulted the
    # first time (no b2share_record.json yet under this repo's own
    # output_dir). None (the default) creates a brand new draft, same as
    # before this field existed — see B2SharePublishForm.tsx's own search
    # button.
    existing_record_id: Optional[str] = None
    # zenodo/b2share, Camtrap DP + mirror_images only — see
    # common.fit_images_to_size/zenodo.DEFAULT_MAX_ZIP_BYTES. Ignored (no-op)
    # for any other product type or publishing mode.
    fit_archive_size: bool = True
    max_zip_file: Optional[float] = None  # GiB — None means "the repo's own real cap"
    min_image_edge: int = 640
    # gbif-only — see services.gbif_service/wildintel_publisher.core.services.gbif
    archive_url: Optional[str] = None
    publishing_organization_key: Optional[str] = None
    installation_key: Optional[str] = None
    registry_language: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    # UUID of an existing GBIF dataset to update — takes priority over
    # whatever output_dir's own gbif_linked_dataset_record.json remembers
    # (see wildintel_publisher.core.services.gbif.register_gbif_dataset's own
    # docstring). None (the default) falls back to that file, or creates a
    # brand new dataset if there's nothing there either — see
    # GBIFPublishForm.tsx's own dataset-picker/search button.
    dataset_key: Optional[str] = None


class GBIFOrganizationDatasetsRequest(BaseModel):
    """See services.gbif.search_organization_datasets — GBIFPublishForm's
    own "search existing datasets" button, so the user can pick a
    dataset_key instead of typing/tracking a UUID by hand."""
    organization_key: str
    environment: str


class PublishAllRequest(BaseModel):
    """Publishes the same product to every repo in `repos`, in order:
    prepare+upload for ALL of them first, THEN a generic cross-repo DOI
    populate pass (see services.doi_populate), and only THEN release/lock
    ALL of them — see services.publish_orchestrator for the full flow."""
    input_dir: str
    # Where to actually read locally-referenced media (media.csv's filePath,
    # for entries that aren't a plain URL) from when preparing the FIRST
    # repo in `repos` — distinct from input_dir only for a local-directory
    # Camtrap DP source, where input_dir is itself just a working copy of
    # the small core files (see services.camtrapdp_source.
    # resolve_local_camtrapdp_source) and the actual media still lives at
    # the original path the user picked. None for every other source type
    # (URL/Trapper/git), where input_dir already is that place.
    media_dir: Optional[str] = None
    version: Optional[str] = None
    timeout: Optional[int] = None
    repos: list[RepoPublishConfig]
    # Which repo's DOI HFH's own CITATION.cff should treat as primary, if
    # more than one is available (HFH never has one of its own — see
    # hfh.py's PROVIDES_DOI). Irrelevant if HFH isn't in `repos`, or if at
    # most one DOI ends up available.
    primary_doi_source: Optional[Literal["zenodo", "b2share"]] = None
    # If true, nothing is actually uploaded/created/released on any real
    # repository — see services.publish_orchestrator's dry-run branches.
    # Zenodo/B2SHARE's DOI reservation is simulated (a synthetic doi/pid
    # written into their own record file) so the real doi_populate.populate()
    # cross-referencing step still has something real to work with. No
    # token/repo_id/community_id is required in this mode, and nothing gets
    # persisted to settings.toml.
    dry_run: bool = False
    # The session a prior Trapper/git/archive fetch or Local Directory
    # resolve (and, usually, preprocessing) already started (see
    # services.session_store) — when given, start_publish_all_task reuses
    # that exact session_dir instead of minting a new one, so the fetched
    # source, the preprocessing choices, and this publish's own build dirs
    # all end up under the same folder. None only for a request that
    # predates this feature — behaves exactly as before in that case.
    session_task_id: Optional[str] = None


class ResumePublishRequest(BaseModel):
    """Resumes a publish session an earlier interrupted run left on disk
    (see services.publish_orchestrator.resume_publish_all_task) — the
    task_id comes from the URL path, not this body. `repos` must name the
    same repos, in the same order, as the original run; session.json never
    stores credentials (by design — see the module docstring), so `token`/
    `password` must always be re-supplied here. `version`/`timeout` apply
    only to whichever repos hadn't finished uploading yet — same meaning as
    PublishAllRequest's own fields; the frontend pre-fills them from the
    session's own summary."""
    repos: list[RepoPublishConfig]
    version: Optional[str] = None
    timeout: Optional[int] = None
