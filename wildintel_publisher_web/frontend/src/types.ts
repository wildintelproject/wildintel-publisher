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

export interface ProductAuthor {
  name?: string
  affiliation?: string
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

/** A publish session an earlier interrupted run left on disk (see the
 * backend's services.publish_orchestrator — GET /api/publish/sessions) —
 * offered on web app startup so the user can resume or discard it instead
 * of starting over. Never carries credentials: `repos` only has whatever
 * services.publish_orchestrator._scrub_secrets keeps, so `token`/`password`
 * always come back empty and must be re-entered before resuming. */
export interface PublishSessionSummary {
  task_id: string
  created_at: string
  status: 'running' | 'error'
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
    fit_archive_size?: boolean
    max_zip_file?: number | null
    min_image_edge?: number
    archive_url?: string | null
    publishing_organization_key?: string | null
    installation_key?: string | null
    registry_language?: string | null
    username?: string | null
    version?: string | null
    timeout?: number | null
  }>
  repo_status: Record<string, PublishRepoStatus>
}
