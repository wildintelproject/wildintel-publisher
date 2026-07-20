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
