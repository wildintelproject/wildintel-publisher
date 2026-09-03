from typing import Literal, Optional

from pydantic import BaseModel

from wildintel_publisher.services.product import ProductAuthor, ProductLicense

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
    # wildintel_publisher.services.common.anonymize_deployment_coordinates.
    anonymize_coordinates: bool = False
    coordinate_decimals: int = 2
    # Camtrap DP only — replaces every mediaID in media.csv (and matching
    # observations.csv references) that isn't already a UUID with a freshly
    # generated one, in input_dir itself, before metadata is extracted.
    # Same "applied once here" shape as anonymize_coordinates, and just as
    # safe to call again later (a mediaID that's already a UUID is left
    # alone). See wildintel_publisher.services.common.randomize_media_ids.
    randomize_media_ids: bool = False


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


class ZenodoSyncDoiRequest(BaseModel):
    zenodo_output_dir: str
    hfh_output_dir: str
    hfh_repo_id: str
    hfh_token: Optional[str] = None


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
    # zenodo/b2share, Camtrap DP + mirror_images only — see
    # common.fit_images_to_size/zenodo.DEFAULT_MAX_ZIP_BYTES. Ignored (no-op)
    # for any other product type or publishing mode.
    fit_archive_size: bool = True
    max_zip_file: Optional[float] = None  # GiB — None means "the repo's own real cap"
    min_image_edge: int = 640
    # gbif-only — see services.gbif_service/wildintel_publisher.services.gbif
    archive_url: Optional[str] = None
    publishing_organization_key: Optional[str] = None
    installation_key: Optional[str] = None
    registry_language: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class PublishAllRequest(BaseModel):
    """Publishes the same product to every repo in `repos`, in order:
    prepare+upload for ALL of them first, THEN a generic cross-repo DOI
    populate pass (see services.doi_populate), and only THEN release/lock
    ALL of them — see services.publish_orchestrator for the full flow."""
    input_dir: str
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
