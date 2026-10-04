export type ProductType = 'camtrapdp' | 'yolo' | 'software' | 'ai_model' | 'ebv' | 'image_gallery'

export interface ResearchProject {
  pk: number
  name: string
  acronym: string
}

export interface ClassificationProject {
  pk: number
  name: string
  is_active: boolean
}

export interface Deployment {
  pk: number
  deployment_id: string
  location_id: string
}

/** Everything needed to start a Camtrap DP download once a deployment has
 * been chosen in TrapperConnectionForm — url/username/password may be blank,
 * in which case the backend reuses what's already saved in settings.toml. */
export interface TrapperDownloadSelection {
  url: string
  username: string
  password: string
  projectId: number
  deploymentId: string
  /** Whether the generated package includes event-level (aggregated)
   * observations, in addition to the media-level ones. Defaults to true in
   * TrapperConnectionForm — Trapper's own API defaults it to false. */
  includeEvents: boolean
}

export interface ProductLicense {
  id?: string
  name?: string
  url?: string
}

/** Shape of metadata.json's "publisher" (see product.ProductPublisher in
 * the backend) — a CFF entity. */
export interface ProductPublisher {
  name: string
  website?: string | null
  email?: string | null
}

/** GET /api/version — whether a newer release of the web app exists. `error`
 * is set when that couldn't be found out (offline...), distinct from "up to date". */
export interface VersionCheck {
  current: string
  latest: string | null
  update_available: boolean
  release_url: string | null
  download_url: string | null
  error: string | null
}

/** One settings file the app can run on (see the backend's core.config.ConfigInfo). */
export interface ConfigInfo {
  id: string
  name: string
  path: string
  active: boolean
}

export interface ProductAuthor {
  name?: string
  affiliation?: string | null
}

/** Headline fields read from an already-obtained product's metadata.json
 * (see services.product.generate_metadata_json in the backend) — generic
 * across product types (Camtrap DP, YOLO...), not specific to any one
 * underlying format. */
export interface DatapackageSummary {
  product_type?: string
  title?: string
  description?: string
  version?: string
  license?: ProductLicense | null
  authors: ProductAuthor[]
  /** Set once a previous publish step in mirror mode has given this product
   * a genuine home (see product.write_homepage in the backend) — null/absent
   * otherwise, e.g. before any publish has happened or after a link-mode
   * publish. */
  homepage?: string | null
  /** HuggingFace Hub repo_id ("user_or_org/dataset") detected from
   * metadata.json's "homepage", if a previous HFH publish step in mirror
   * mode already set it — null if the product was never mirror-published
   * to HFH. */
  hfh_repo_id?: string | null
  /** Software Application only (see ProductAdapter.checkout_release in the
   * backend) — the git tag actually checked out to match CITATION.cff's own
   * "version", or null if none matched (so the default branch's latest
   * commit was published instead) or this product type has no git checkout
   * to begin with. Reporting-only, never part of metadata.json itself. */
  checked_out_tag?: string | null
}

/** Camtrap DP's 5 allowed values for a contributor's "role" (see the
 * official profile's "contributors" schema) — "contributor" is the
 * standard's own default when none is set. */
export const CAMTRAPDP_CONTRIBUTOR_ROLES = [
  'contact', 'principalInvestigator', 'rightsHolder', 'publisher', 'contributor',
] as const
export type CamtrapdpContributorRole = typeof CAMTRAPDP_CONTRIBUTOR_ROLES[number]

/** A single entry of datapackage.json's own "contributors" array — kept
 * loose (only `role` is ever edited by the wizard, see WizardPage's
 * dpContributors state) so whatever other fields a contributor already has
 * (title/email/organization/path...) survive a round-trip untouched. */
export interface DatapackageContributor {
  title?: string | null
  email?: string | null
  organization?: string | null
  role?: string | null
  [key: string]: unknown
}

/** One selectable entry from settings.toml's own PRODUCT.organizations
 * (see the backend's wildintel_publisher.config.ProductSettings) —
 * WizardPage's own Publisher/Rights holder dropdowns both draw from the
 * same fetched list (see api.organizations), instead of two
 * separate hardcoded ones. GBIFPublishForm fetches the same list
 * independently for its own "Publishing organization UUID" quick-fill
 * dropdown, using gbif_sandbox_organization_key/
 * gbif_production_organization_key instead. */
export interface Organization {
  title: string
  path?: string | null
  email?: string | null
  gbif_sandbox_organization_key?: string | null
  gbif_production_organization_key?: string | null
}

/** One selectable entry from settings.toml's own GBIF.installations (see
 * the backend's wildintel_publisher.config.GBIFInstallation) —
 * GBIFPublishForm's own "Installation UUID" quick-fill dropdown, same
 * pattern as Organization's own gbif_*_organization_key fields
 * above but for a GBIF installation instead of an organization — a
 * distinct GBIF concept with no Camtrap DP equivalent, so it isn't part of
 * that same shared list. */
export interface GBIFInstallation {
  title: string
  sandbox_installation_key?: string | null
  production_installation_key?: string | null
}

/** settings.toml, as the settings page reads it (GET /api/settings) — see
 * the backend's wildintel_publisher.config.Settings and its router,
 * api.routers.app_settings. A secret field (config.py's
 * json_schema_extra={"secret": True}) never comes back as a value, only as
 * a has_<field> boolean. */
export type LogLevel = 'ERROR' | 'WARNING' | 'INFO' | 'DEBUG'

/** One saved S3-compatible remote — the secrets only show up as has_<field>. */
export interface S3Remote {
  id: string
  name: string
  endpoint_url: string | null
  region: string | null
  bucket: string | null
  prefix: string | null
  public_base_url: string | null
  verify_ssl: boolean
  has_access_key: boolean
  has_secret_key: boolean
}

/** A remote as PUT: the secrets become real (writable) fields, null/blank keeping the saved one. */
export type S3RemoteUpdate = Omit<S3Remote, 'has_access_key' | 'has_secret_key'> & {
  access_key: string | null
  secret_key: string | null
}

export interface AppSettings {
  GENERAL: {
    log_level: LogLevel
    /** Where the log goes (read-only). */
    log_file: string
    config_file: string
    /** The level WILDINTEL_PUBLISHER_LOG_LEVEL sets instead, if any (read-only). */
    log_level_override: LogLevel | null
  }
  TRAPPER: {
    base_url: string | null
    has_user_name: boolean
    has_user_password: boolean
    project_id: number | null
    retry_attempts: number
    retry_wait_seconds: number
  }
  CAMTRAPDP: {
    license_id: string | null
    license_name: string | null
    license_url: string | null
    dataset_slug: string | null
    dataset_name: string | null
    description: string | null
  }
  HFH: {
    message: string | null
    repository_code: string | null
    repo_id: string | null
    username: string | null
    has_token: boolean
  }
  ZENODO: {
    environment: 'sandbox' | 'production' | null
    sandbox_communities: string | null
    production_communities: string | null
    has_sandbox_token: boolean
    has_production_token: boolean
  }
  B2SHARE: {
    environment: 'sandbox' | 'production' | null
    sandbox_community_id: string | null
    production_community_id: string | null
    has_sandbox_token: boolean
    has_production_token: boolean
  }
  GBIF: {
    environment: 'sandbox' | 'production' | null
    sandbox_publishing_organization_key: string | null
    production_publishing_organization_key: string | null
    sandbox_installation_key: string | null
    production_installation_key: string | null
    registry_language: string | null
    has_sandbox_username: boolean
    has_sandbox_password: boolean
    has_production_username: boolean
    has_production_password: boolean
    installations: GBIFInstallation[]
  }
  S3: {
    remotes: S3Remote[]
    retry_attempts: number
    retry_wait_seconds: number
  }
  PRODUCT: {
    organizations: Organization[]
    authors: ProductAuthor[]
  }
}

/** PUT /api/settings's own body — same shape as AppSettings, but each
 * has_<field> boolean becomes the real (writable) field: a secret left
 * blank keeps the one already saved, same rule as everywhere else in this
 * app (see TrapperConnectionForm). */
export interface AppSettingsUpdate {
  GENERAL: { log_level: LogLevel }
  CAMTRAPDP: AppSettings['CAMTRAPDP']
  TRAPPER: Omit<AppSettings['TRAPPER'], 'has_user_name' | 'has_user_password'> & {
    user_name: string | null
    user_password: string | null
  }
  HFH: Omit<AppSettings['HFH'], 'has_token'> & { token: string | null }
  ZENODO: Omit<AppSettings['ZENODO'], 'has_sandbox_token' | 'has_production_token'> & {
    sandbox_token: string | null
    production_token: string | null
  }
  B2SHARE: Omit<AppSettings['B2SHARE'], 'has_sandbox_token' | 'has_production_token'> & {
    sandbox_token: string | null
    production_token: string | null
  }
  GBIF: Omit<
    AppSettings['GBIF'],
    'has_sandbox_username' | 'has_sandbox_password' | 'has_production_username' | 'has_production_password'
  > & {
    sandbox_username: string | null
    sandbox_password: string | null
    production_username: string | null
    production_password: string | null
  }
  S3: Omit<AppSettings['S3'], 'remotes'> & { remotes: S3RemoteUpdate[] }
  PRODUCT: AppSettings['PRODUCT']
}

/** name/title/description/version/homepage/contributors read straight from
 * datapackage.json itself (see services.common.read_datapackage_metadata in
 * the backend) — distinct from DatapackageSummary above, which comes from
 * metadata.json (the app's own publish-pipeline wrapper) and only exists
 * once generate-metadata has run. Used to pre-fill the wizard's
 * metadata-editing step right after the source is downloaded/resolved,
 * before any preprocessing happens. */
export interface DatapackageFields {
  name?: string | null
  title?: string | null
  description?: string | null
  version?: string | null
  homepage?: string | null
  contributors?: DatapackageContributor[] | null
}

/** YOLO only — the metadata keys this tool adds to data.yaml (see
 * yolo_adapter.YoloEditableMetadata in the backend), as edited by the
 * wizard's metadata step. An empty value removes that key. */
export interface YoloDataYamlMetadata {
  title?: string | null
  description?: string | null
  version?: string | null
  homepage?: string | null
  /** Appended to the README's Funding section, after the standard text. */
  funding?: string | null
  license?: ProductLicense | null
  authors: ProductAuthor[]
  /** Picked from PRODUCT.organizations, same as a Camtrap DP's own
   * publisher/rightsHolder contributors. */
  publisher?: ProductPublisher | null
  copyright_holders: string[]
}

/** YoloDataYamlMetadata as read back from the working copy's data.yaml,
 * plus read-only facts about the dataset and its validation warnings. */
export interface YoloDataYamlFields extends YoloDataYamlMetadata {
  class_names: string[]
  split_image_counts: Record<string, number>
  warnings: string[]
}

/** Which of DatapackageSummary's required fields the extractor couldn't
 * determine from the product itself (see services.product.
 * missing_required_fields in the backend) — homepage is deliberately not
 * part of this: it's allowed to stay unset indefinitely. */
export type RequiredSummaryField = 'title' | 'description' | 'version' | 'license' | 'authors'

export function missingRequiredFields(summary: DatapackageSummary): RequiredSummaryField[] {
  const missing: RequiredSummaryField[] = []
  if (!summary.title) missing.push('title')
  if (!summary.description) missing.push('description')
  if (!summary.version) missing.push('version')
  if (!summary.license) missing.push('license')
  if (summary.authors.length === 0) missing.push('authors')
  return missing
}

export interface BrowseEntry {
  name: string
  path: string
}

/** Result of browsing one directory with the local directory picker. */
export interface BrowseResult {
  current: string
  parent: string | null
  dirs: BrowseEntry[]
}

/** What a publish task's final output_dir is (used to chain the next repo's
 * inputDir when publishing to more than one repository):
 * - 'prepared' (default): the local directory prepare/upload wrote to.
 * - 'passthrough': inputDir itself, unchanged — nothing new is written.
 * - 'downloaded': a fresh copy downloaded back from the repo after a
 *   successful publish. */
export type OutputMode = 'prepared' | 'passthrough' | 'downloaded'

/** One repo's worth of publish configuration — shared shape between
 * api.publishAllStart and api.resumePublishStart (see PublishSessionSummary
 * below: a resumed session pre-fills every field except `token`/`password`,
 * which are never persisted and must always be re-entered). */
export interface PublishRepoConfig {
  repo: 'hfh' | 'zenodo' | 'b2share' | 'gbif'
  outputDir: string
  token?: string
  mirrorImages: boolean
  outputMode: OutputMode
  repoId?: string
  private?: boolean
  environment?: string
  communities?: string
  communityId?: string
  // zenodo-only — numeric id of an already-published Zenodo deposition to
  // create a proper linked NEW VERSION of, instead of an unrelated fresh
  // deposition. Undefined (the default) creates a brand new deposition,
  // same as before this field existed — see ZenodoPublishForm's own
  // "Search existing depositions" button.
  existingDepositionId?: string
  // b2share-only — id of an already-published B2SHARE record to create a
  // proper linked NEW VERSION of, instead of an unrelated fresh draft.
  // Undefined (the default) creates a brand new draft, same as before this
  // field existed — see B2SharePublishForm's own "Search existing records"
  // button.
  existingRecordId?: string
  // zenodo/b2share, Camtrap DP + mirror only — see common.fit_images_to_size
  fitArchiveSize?: boolean
  maxZipFile?: number
  minImageEdge?: number
  // gbif-only
  archiveUrl?: string
  publishingOrganizationKey?: string
  installationKey?: string
  registryLanguage?: string
  username?: string
  password?: string
  // UUID of an existing GBIF dataset to update — takes priority over
  // whatever the backend's own gbif_linked_dataset_record.json remembers.
  // Undefined (the default) falls back to that file, or creates a brand
  // new dataset if there's nothing there either — see GBIFPublishForm's
  // own dataset-picker/search button.
  datasetKey?: string
}

/** A per-repo publish status entry — same shape api.publishAllStatus polls,
 * reused by PublishSessionSummary since a session's repo_status is exactly
 * what was last polled before the interruption. */
export interface PublishRepoStatus {
  status: 'pending' | 'running' | 'done' | 'error'
  stage: string
  error: string | null
  repo_url: string | null
  doi: string | null
  pid: string | null
  output_dir: string | null
  doi_synced_to_hfh?: boolean | null
}

/** Every phase a session (see the backend's services.session_store) can be
 * in — a session starts at "fetching" for a Trapper/git/public-URL source
 * (skipped straight to "fetched" for a Local Directory one, resolved
 * synchronously — see SourceType below) and, if the user gets that far,
 * ends at "publishing"/"done"; "done" is never actually seen (the backend
 * deletes the whole session as soon as it's reached). */
export type SessionPhase = 'fetching' | 'fetched' | 'preprocessing' | 'preprocessed' | 'publishing' | 'done'

/** A session's source-fetch section — present from the moment a Trapper/
 * git/public-URL fetch starts (or a Local Directory resolves — instantly,
 * so this always lands "fetched" already), kept (unscrubbed of its own
 * non-secret fields) through every later phase. `params` never includes
 * Trapper's username/password — see services.session_store.write_fetch_phase. */
export interface SessionFetch {
  source_type: 'trapper' | 'git' | 'archive' | 'local'
  params: Record<string, unknown>
  output_dir: string
  input_dir: string | null
}

/** A session's preprocessing section — present once generate-metadata has
 * run at least once for it (see services.session_store.
 * write_preprocessing_phase) — informational only, the real field values
 * live in metadata.json/datapackage.json at `fetch.input_dir`. */
export interface SessionPreprocessing {
  status: 'running' | 'done' | 'error'
  anonymize_coordinates?: boolean
  coordinate_decimals?: number
  randomize_media_ids?: boolean
  media_id_domain?: string
}

interface SessionSummaryBase {
  task_id: string
  created_at: string
  // "done" here means only THIS session's OWN latest phase succeeded
  // (write_fetch_phase/write_preprocessing_phase reuse "status" for
  // that) — NOT that the whole run is finished; that's `phase` reaching
  // the literal "done" instead, which a session never survives to report
  // (see SessionPhase above and services.session_store.list_sessions).
  status: 'running' | 'done' | 'error'
  phase: SessionPhase
  product_type: ProductType | null
  source_type: 'trapper' | 'git' | 'archive' | 'local' | null
  error?: string | null
}

/** A session still at (or that failed during) the source-fetch phase —
 * nothing preprocessed yet. */
export interface FetchSession extends SessionSummaryBase {
  phase: 'fetching' | 'fetched'
  fetch: SessionFetch
}

/** A session whose source is already fetched and is at (or failed during)
 * the preprocessing phase. */
export interface PreprocessingSession extends SessionSummaryBase {
  phase: 'preprocessing' | 'preprocessed'
  fetch: SessionFetch
  preprocessing: SessionPreprocessing | null
}

/** A publish session an earlier interrupted run left on disk (see the
 * backend's services.publish_orchestrator — GET /api/publish/sessions) —
 * offered on web app startup so the user can resume or discard it instead
 * of starting over. Never carries credentials: `repos` only has whatever
 * services.publish_orchestrator._scrub_secrets keeps, so `token`/`password`
 * always come back empty and must be re-entered before resuming. May also
 * carry its own `fetch`/`preprocessing` sections, if this same session
 * started earlier than the publish phase (see SessionFetch/
 * SessionPreprocessing above) — informational only at this point. */
export interface PublishSessionSummary extends SessionSummaryBase {
  phase: 'publishing'
  dry_run: boolean
  input_dir: string
  media_dir: string | null
  primary_doi_source: 'zenodo' | 'b2share' | null
  repos: Array<{
    repo: 'hfh' | 'zenodo' | 'b2share' | 'gbif'
    output_dir?: string | null
    mirror_images?: boolean
    output_mode?: OutputMode
    repo_id?: string | null
    private?: boolean
    environment?: string | null
    communities?: string | null
    community_id?: string | null
    existing_deposition_id?: string | null
    existing_record_id?: string | null
    fit_archive_size?: boolean
    max_zip_file?: number | null
    min_image_edge?: number
    archive_url?: string | null
    publishing_organization_key?: string | null
    installation_key?: string | null
    registry_language?: string | null
    username?: string | null
    dataset_key?: string | null
    version?: string | null
    timeout?: number | null
  }>
  repo_status: Record<string, PublishRepoStatus>
  fetch?: SessionFetch
  preprocessing?: SessionPreprocessing | null
}

/** Any session GET /api/publish/sessions can return, at whichever phase it
 * was interrupted — see ResumeSessionsPage/WizardPage's own resumeSession
 * prop, which branches on `phase` to decide what to pre-fill and which
 * wizard step to land on. */
export type SessionSummary = FetchSession | PreprocessingSession | PublishSessionSummary

/** Whether the wizard is publishing a brand new dataset, or a new version
 * of one already published (see PublicationKindPicker) — asked before the
 * metadata step's editor. */
export type PublicationKind = 'new' | 'version'

export interface FoundHfh {
  repo_id: string
  url: string
  /** Its highest version tag — the version last published there. */
  version?: string | null
}

export interface FoundRecord {
  /** Always the LATEST version's own record id — a new version is created
   * from it (see services.previous_version_service in the backend). */
  record_id: string
  environment: 'sandbox' | 'production'
  url: string
  doi?: string | null
  title?: string | null
  version?: string | null
}

/** The previous version, found on every repository reachable from one
 * identifier (api.previousVersion). */
/** GBIF datasets have no versions of their own — a new version updates
 * this same dataset (see gbif.register_gbif_dataset's dataset_key). */
export interface FoundGbif {
  dataset_key: string
  environment: 'sandbox' | 'production'
  url: string
  doi?: string | null
  title?: string | null
}

export interface PreviousVersion {
  title?: string | null
  version?: string | null
  hfh?: FoundHfh | null
  zenodo?: FoundRecord | null
  b2share?: FoundRecord | null
  gbif?: FoundGbif | null
  warnings: string[]
}

export interface Publication {
  kind: PublicationKind
  /** Only for kind 'version' — null until it's been looked up. */
  previous: PreviousVersion | null
}
