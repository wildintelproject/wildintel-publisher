import { useEffect, useState } from 'react'
import B2SharePublishForm, { SyncPidSection } from '../components/B2SharePublishForm'
import type { B2SharePublishConfig } from '../components/B2SharePublishForm'
import CamtrapDPArchiveForm from '../components/CamtrapDPArchiveForm'
import CompleteMetadataForm from '../components/CompleteMetadataForm'
import GBIFPublishForm, { GBIFSyncDoiSection } from '../components/GBIFPublishForm'
import type { GBIFPublishConfig } from '../components/GBIFPublishForm'
import GitCloneForm from '../components/GitCloneForm'
import HFHPublishForm from '../components/HFHPublishForm'
import type { HfhPublishConfig } from '../components/HFHPublishForm'
import LocalDirectoryForm from '../components/LocalDirectoryForm'
import type { LocalSourceSelection } from '../components/LocalDirectoryForm'
import TrapperConnectionForm from '../components/TrapperConnectionForm'
import ZenodoPublishForm, { SyncDoiSection } from '../components/ZenodoPublishForm'
import type { ZenodoPublishConfig } from '../components/ZenodoPublishForm'
import { api } from '../api'
import { missingRequiredFields } from '../types'
import { CAMTRAPDP_CONTRIBUTOR_ROLES } from '../types'
import type { DatapackageContributor, DatapackageSummary, ProductType, TrapperDownloadSelection } from '../types'

const STEP_LABELS = ['Product Type', 'Source', 'Metadata', 'Download', 'Publish']

// Data Package spec's own constraints on these two fields (the others —
// title/description/homepage — are free text, nothing to validate).
const DP_NAME_PATTERN = /^[a-z0-9._-]+$/
const DP_VERSION_PATTERN = /^\d+(\.\d+){0,2}$/

// The "publisher" contributor is always wildintel-publisher itself, never
// user-editable — any other contributor's own "publisher" role gets
// demoted (see the effect that loads datapackage.json's contributors).
const CAMTRAPDP_PUBLISHER: DatapackageContributor = {
  title: 'WildINTEL', email: 'wildintelproject@gmail.com', path: 'https://wildintel.eu/', role: 'publisher',
}

// The only organizations selectable as "rightsHolder" — exactly one of
// these at a time (see dpRightsHolder state). Websites verified 2026-09.
const CAMTRAPDP_RIGHTS_HOLDER_OPTIONS: { title: string; path: string }[] = [
  { title: 'Institute of Nature Conservation PAS', path: 'https://www.iop.krakow.pl/' },
  { title: 'University of Huelva', path: 'https://www.uhu.es/' },
  { title: 'University of South-Eastern Norway', path: 'https://www.usn.no/' },
  { title: 'German Centre for Integrative Biodiversity Research', path: 'https://www.idiv.de/' },
  { title: 'Spanish National Research Council', path: 'https://www.csic.es/' },
  { title: 'Massachusetts Institute of Technology', path: 'https://www.mit.edu/' },
  { title: 'Spanish Node of the Global Biodiversity Information Facility', path: 'https://www.gbif.es/' },
]

// "publisher" and "rightsHolder" are reserved for the two fixed rows above
// — every OTHER contributor (from the source itself, e.g. Trapper) can
// only ever be assigned one of these three roles.
const EDITABLE_CONTRIBUTOR_ROLES = CAMTRAPDP_CONTRIBUTOR_ROLES.filter(
  (role) => role !== 'publisher' && role !== 'rightsHolder',
)

interface ProductOption {
  value: ProductType
  emoji: string
  title: string
  description: string
  available: boolean
}

// AI Model/EBV/Image Gallery have no adapter (or wizard/backend wiring) of
// their own yet — flip to true once one exists (see developer-guide.md's
// "Adding a new product type").
const PRODUCT_OPTIONS: ProductOption[] = [
  { value: 'camtrapdp', emoji: '📦', title: 'Camtrap DP', description: 'A camera-trap data package fetched from Trapper.', available: true },
  { value: 'yolo', emoji: '🗂️', title: 'AI Dataset', description: 'An image dataset in YOLO training format (images/train, val, test + data.yaml).', available: true },
  { value: 'software', emoji: '💻', title: 'Software Application', description: 'A software application published from its own git repository.', available: true },
  { value: 'ai_model', emoji: '🤖', title: 'AI Model', description: 'A trained AI model artifact.', available: false },
  { value: 'ebv', emoji: '🌍', title: 'EBV', description: 'Essential Biodiversity Variables derived from the project data.', available: false },
  { value: 'image_gallery', emoji: '🖼️', title: 'Image Gallery', description: 'A curated gallery of camera-trap images.', available: false },
]

type SourceType = 'local' | 'trapper' | 'git' | 'archive'

interface SourceOption {
  value: SourceType
  emoji: string
  title: string
  description: string
  available: boolean
}

// Trapper fetch is only relevant for productType === 'camtrapdp' — other
// product types (e.g. YOLO) only support a local directory the user already
// has on this machine, so this is a lookup keyed by productType rather than
// a single flat list.
const SOURCE_OPTIONS_BY_PRODUCT_TYPE: Record<ProductType, SourceOption[]> = {
  camtrapdp: [
    { value: 'local', emoji: '📁', title: 'Local Directory', description: 'Use a Camtrap DP package already available on this machine.', available: true },
    { value: 'trapper', emoji: '🌐', title: 'Trapper Instance', description: 'Fetch a Camtrap DP package from a Trapper classification project.', available: true },
    { value: 'archive', emoji: '🔗', title: 'Public URL', description: 'Fetch an already-published Camtrap DP zip archive from a public URL.', available: true },
  ],
  yolo: [
    { value: 'local', emoji: '📁', title: 'Local Directory', description: 'Use a YOLO dataset already available on this machine.', available: true },
  ],
  software: [
    { value: 'git', emoji: '🔗', title: 'Git Repository', description: 'Clone a software application from a git repository URL.', available: true },
  ],
  ai_model: [],
  ebv: [],
  image_gallery: [],
}

type RepoId = 'hfh' | 'zenodo' | 'b2share' | 'gbif'

interface RepoOption {
  value: RepoId
  emoji: string
  title: string
  description: string
  implemented: boolean
}

const REPO_OPTIONS: RepoOption[] = [
  { value: 'hfh', emoji: '🤗', title: 'Hugging Face Hub', description: 'Publish as a dataset repository on Hugging Face Hub.', implemented: true },
  { value: 'zenodo', emoji: '📚', title: 'Zenodo', description: 'Archive the package with a DOI on Zenodo.', implemented: true },
  { value: 'b2share', emoji: '🗄️', title: 'B2SHARE', description: 'Deposit the package into a EUDAT B2SHARE record.', implemented: true },
  { value: 'gbif', emoji: '🌐', title: 'GBIF', description: 'Register a Camtrap DP already hosted elsewhere with GBIF, so it gets crawled and indexed.', implemented: true },
]

// Which repositories accept which product type. GBIF only ever accepts
// Camtrap DP (biodiversity occurrence data) — YOLO training datasets/models
// aren't a fit (see docs/publishing-gbif.md). Camtrap DP itself now offers
// all four repositories (Zenodo/B2SHARE joined Hugging Face Hub + GBIF here
// — see GBIFPublishForm's own suggestedArchiveUrl wiring below for how its
// Archive URL behaves when Zenodo/B2SHARE publish without Hugging Face Hub
// in the same run). A software application has no biodiversity/media
// content to speak of, so HFH and GBIF aren't a fit for it either — it only
// ever goes to Zenodo/B2SHARE (see MANDATORY_REPOS_BY_PRODUCT_TYPE: Zenodo
// is required for it, since its DOI is always the one that ends up citing
// the software). The other product types aren't selectable yet, so they
// have no supported repositories of their own for now.
const REPOS_BY_PRODUCT_TYPE: Record<ProductType, RepoId[]> = {
  camtrapdp: ['hfh', 'zenodo', 'b2share', 'gbif'],
  yolo: ['hfh', 'zenodo', 'b2share'],
  software: ['zenodo', 'b2share'],
  ai_model: [],
  ebv: [],
  image_gallery: [],
}

// Repos that, once their product type is picked, are pre-selected and
// can't be deselected — Zenodo is always published for both AI Dataset
// and Software Application (its DOI is the one used to cite the dataset/
// software), and for Camtrap DP, GBIF is always registered (see the
// "Required" badge in the repo-selection grid, and toggleRepo's own guard
// below). Every other product type has none.
const MANDATORY_REPOS_BY_PRODUCT_TYPE: Partial<Record<ProductType, RepoId[]>> = {
  camtrapdp: ['gbif'],
  yolo: ['zenodo'],
  software: ['zenodo'],
}

const btnOutline = 'px-4 py-2 text-sm border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50'
const btnPrimary = 'px-6 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-blue-600 flex items-center gap-2'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-white/60 border-t-white rounded-full animate-spin" />
}

function DryRunBadge() {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-200 dark:bg-amber-900 text-amber-800 dark:text-amber-200">
      Dry run
    </span>
  )
}

type DownloadStatus = 'idle' | 'running' | 'done' | 'error'

interface DownloadState {
  status: DownloadStatus
  path: string | null
  // Where locally-referenced media actually lives — only different from
  // `path` when sourceType === 'local' (path is then an app-owned working
  // copy of just the core files; sourcePath is the user's original
  // directory, never mutated — see LocalDirectoryForm/resolveLocalSource).
  // Equal to `path` for every other source type.
  sourcePath: string | null
  error: string | null
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
}

const IMAGE_TIMEOUT = 60

const STAGE_LABELS: Record<string, string> = {
  preparing: 'Preparing…',
  uploading: 'Uploading…',
  releasing: 'Publishing…',
  done: 'Done',
}

type RepoProgressStatus = 'pending' | 'running' | 'done' | 'error'

interface RepoProgress {
  status: RepoProgressStatus
  stage: string
  error: string | null
  repoUrl: string | null
  doi: string | null
  pid: string | null
  doiSyncedToHfh: boolean | null
}

const IDLE_PROGRESS: RepoProgress = {
  status: 'pending', stage: '', error: null, repoUrl: null, doi: null, pid: null, doiSyncedToHfh: null,
}

interface RepoConfigs {
  hfh?: HfhPublishConfig
  zenodo?: ZenodoPublishConfig
  b2share?: B2SharePublishConfig
  gbif?: GBIFPublishConfig
}

export default function WizardPage() {
  const [step, setStep] = useState(0)
  const [productType, setProductType] = useState<ProductType | null>(null)
  const [sourceType, setSourceType] = useState<SourceType | null>(null)
  const [trapperSelection, setTrapperSelection] = useState<TrapperDownloadSelection | null>(null)
  const [localSelection, setLocalSelection] = useState<LocalSourceSelection | null>(null)
  const [gitUrl, setGitUrl] = useState<string | null>(null)
  // The URL used to fetch a Camtrap DP directly (sourceType === 'archive')
  // — kept around (not just used to fetch) so it can be suggested straight
  // back as GBIF's own archive_url later, when GBIF publishes standalone:
  // it's already confirmed public and a valid Camtrap DP by the same fetch
  // (see WizardPage's suggestedArchiveUrl for the GBIF form).
  const [archiveSourceUrl, setArchiveSourceUrl] = useState<string | null>(null)
  // Camtrap DP only — rounds deployments.csv's latitude/longitude, once, as
  // part of generateProductMetadata (a product-level preprocessing step —
  // see the useEffect below), so every repo that later prepares its own
  // export from this same download.path inherits the same already-
  // anonymized coordinates automatically, with no flag of its own.
  const [anonymizeCoordinates, setAnonymizeCoordinates] = useState(false)
  const [coordinateDecimals, setCoordinateDecimals] = useState(2)
  // Camtrap DP only — replaces every mediaID that isn't already a UUID,
  // once, as part of generateProductMetadata, same shape as
  // anonymizeCoordinates above.
  const [randomizeMediaIds, setRandomizeMediaIds] = useState(false)
  // Namespace for those derived UUIDs — auto-suggested from the chosen
  // source (see the effect below) unless the user has edited it by hand.
  const [mediaIdDomain, setMediaIdDomain] = useState('localhost')
  const [mediaIdDomainEdited, setMediaIdDomainEdited] = useState(false)
  // Camtrap DP only — datapackage.json's own name/title/description/
  // homepage/version, editable in the new step between download and
  // preprocessing (see step === 2 below). Pre-filled from
  // api.datapackageFields once the source resolves; edits are written back
  // with api.updateDatapackageFields BEFORE generateProductMetadata runs,
  // so metadata.json (and everything generated from it) picks them up too —
  // see services.common.update_datapackage_fields's own docstring.
  const [dpName, setDpName] = useState('')
  const [dpTitle, setDpTitle] = useState('')
  const [dpDescription, setDpDescription] = useState('')
  const [dpHomepage, setDpHomepage] = useState('')
  const [dpVersion, setDpVersion] = useState('')
  // Every OTHER contributor from datapackage.json (i.e. not the fixed
  // publisher/rightsHolder rows below) — the wizard only ever edits each
  // entry's own "role" (see the dropdown in step === 2 below); everything
  // else about each contributor round-trips untouched.
  const [dpContributors, setDpContributors] = useState<DatapackageContributor[]>([])
  // The single selected rightsHolder organization's title — always one of
  // CAMTRAPDP_RIGHTS_HOLDER_OPTIONS. The "publisher" row has no state of
  // its own: it's always CAMTRAPDP_PUBLISHER, never user-editable.
  const [dpRightsHolder, setDpRightsHolder] = useState(CAMTRAPDP_RIGHTS_HOLDER_OPTIONS[0].title)
  // Explains, when non-empty, which of the source's own contributors got
  // silently excluded above (a "publisher" that isn't WildINTEL, or a
  // "rightsHolder" not on the fixed list) — set once by the effect that
  // loads datapackage.json's contributors below.
  const [dpContributorWarnings, setDpContributorWarnings] = useState<string[]>([])
  // Both fields are optional — only validated once the user has actually
  // typed something in them (an empty value just means "leave as-is").
  const dpNameValid = dpName === '' || DP_NAME_PATTERN.test(dpName)
  const dpVersionValid = dpVersion === '' || DP_VERSION_PATTERN.test(dpVersion)
  // True while handleContinueToPreprocessing (step === 2's "Continue"
  // button) is running.
  const [preprocessing, setPreprocessing] = useState(false)
  const [download, setDownload] = useState<DownloadState>({ status: 'idle', path: null, sourcePath: null, error: null })
  const [summary, setSummary] = useState<DatapackageSummary | null>(null)
  // Set whenever generateProductMetadata itself fails (e.g. a Software
  // Application git clone with no CITATION.cff at its root — see
  // ProductAdapter.validate) — without this, summary just stays null and
  // Next stays silently, permanently disabled, with no indication why.
  const [metadataError, setMetadataError] = useState<string | null>(null)
  const [folderError, setFolderError] = useState<string | null>(null)
  const [selectedRepos, setSelectedRepos] = useState<Set<RepoId>>(new Set())
  // The order in which the selected repos will be published — determines
  // each step's input: the first uses the original downloaded package, each
  // next one uses whatever the previous step wrote to its own output
  // directory (see outputDirs/getInputDirFor below).
  const [publishOrder, setPublishOrder] = useState<RepoId[]>([])
  const [outputDirs, setOutputDirs] = useState<Partial<Record<RepoId, string>>>({})
  // Simulates the whole publish flow with no real uploads/creations on any
  // repository — Zenodo/B2SHARE's DOI is faked so the cross-repo DOI
  // populate step still has something real to cross-reference (see
  // services.publish_orchestrator's dry-run branches). No token is required
  // in this mode.
  const [dryRun, setDryRun] = useState(false)

  // Once the user starts publishing, the wizard first COLLECTS each
  // repository's configuration (token, mode, etc.), one at a time, without
  // publishing anything yet — only once every selected repository has been
  // configured does a confirmation screen appear, and only after that does
  // the actual publish sequence run, automatically and without further
  // pauses, one repository after another (see runPublishSequence).
  const [publishStarted, setPublishStarted] = useState(false)
  const [configureIndex, setConfigureIndex] = useState(0)
  const [repoConfigs, setRepoConfigs] = useState<RepoConfigs>({})
  // Only relevant when hfh + zenodo + b2share are ALL selected — HFH never
  // has a DOI of its own, so with two possible DOI sources the user picks
  // which one is primary (see the "choose primary DOI" screen below).
  // Stays null (never asked) otherwise, and publishAllStart's own
  // primary_doi_source ends up undefined in that case.
  const [primaryDoiSource, setPrimaryDoiSource] = useState<'zenodo' | 'b2share' | null>(null)
  const [executing, setExecuting] = useState(false)
  const [executionDone, setExecutionDone] = useState(false)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const [progress, setProgress] = useState<Partial<Record<RepoId, RepoProgress>>>({})

  const canProceed = (sourceType === 'trapper' && trapperSelection !== null) || (sourceType === 'local' && localSelection !== null) || (sourceType === 'git' && gitUrl !== null) || (sourceType === 'archive' && archiveSourceUrl !== null)
  const isDownloading = download.status === 'running'
  const supportedRepos = productType ? REPOS_BY_PRODUCT_TYPE[productType] : []
  const sourceOptions = productType ? SOURCE_OPTIONS_BY_PRODUCT_TYPE[productType] : []
  const metadataComplete = summary !== null && missingRequiredFields(summary).length === 0
  const allConfigured = publishStarted && configureIndex >= publishOrder.length
  const needsPrimaryDoiChoice = publishOrder.includes('hfh') && publishOrder.includes('zenodo') && publishOrder.includes('b2share')
  const readyToConfirm = allConfigured && (!needsPrimaryDoiChoice || primaryDoiSource !== null)
  // When HFH+GBIF are the only two repos selected, toggleRepo already forces
  // HFH first — so there's genuinely nothing to reorder for that specific
  // pair. Once Zenodo/B2SHARE join the selection too, the general reorder
  // UI below takes over instead (toggleRepo still keeps HFH ahead of GBIF
  // within it).
  const hfhGbifOrderLocked = publishOrder.length === 2 && publishOrder.includes('hfh') && publishOrder.includes('gbif')
  // Rendered by each PublishForm itself, next to its own Continue button —
  // spread as-is (empty object for the first repository in the order,
  // which has nothing to go back to) rather than a separate button placed
  // above the form, so Back and Continue end up in the same row instead of
  // at very different heights on the page.
  const backProps = configureIndex > 0
    ? {
        onBack: () => setConfigureIndex((i) => i - 1),
        backLabel: `← Back to ${REPO_OPTIONS.find((o) => o.value === publishOrder[configureIndex - 1])?.title}`,
      }
    : {}

  function toggleRepo(repo: RepoId) {
    if (productType && MANDATORY_REPOS_BY_PRODUCT_TYPE[productType]?.includes(repo)) return
    setSelectedRepos((prev) => {
      const next = new Set(prev)
      if (next.has(repo)) next.delete(repo)
      else next.add(repo)
      return next
    })
    setPublishOrder((prev) => {
      const next = prev.includes(repo) ? prev.filter((r) => r !== repo) : [...prev, repo]
      // GBIF's archive URL is deterministically derived from HFH's own
      // repo_id once HFH has published in this same run — there's no valid
      // order other than HFH first, so it's enforced here rather than left
      // to manual reordering (see the "Publish order" section below, which
      // hides its reorder controls for exactly this pair).
      if (next.includes('hfh') && next.includes('gbif')) {
        return ['hfh' as const, ...next.filter((r) => r !== 'hfh')]
      }
      return next
    })
  }

  function moveInOrder(repo: RepoId, delta: number) {
    setPublishOrder((prev) => {
      const index = prev.indexOf(repo)
      const targetIndex = index + delta
      if (index === -1 || targetIndex < 0 || targetIndex >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[targetIndex]] = [next[targetIndex], next[index]]
      return next
    })
  }

  function startConfiguring() {
    setConfigureIndex(0)
    setRepoConfigs({})
    setPublishStarted(true)
  }

  function handleConfigured(repo: RepoId, config: HfhPublishConfig | ZenodoPublishConfig | B2SharePublishConfig | GBIFPublishConfig) {
    setRepoConfigs((c) => ({ ...c, [repo]: config }))
    setConfigureIndex((i) => i + 1)
  }

  // Resets every piece of wizard state back to its initial value, so
  // "Publish again" starts from a completely clean step 0 — same as a fresh
  // page load, rather than reusing anything from the just-finished publish.
  function handlePublishAgain() {
    setStep(0)
    setProductType(null)
    setSourceType(null)
    setTrapperSelection(null)
    setLocalSelection(null)
    setGitUrl(null)
    setArchiveSourceUrl(null)
    setAnonymizeCoordinates(false)
    setCoordinateDecimals(2)
    setRandomizeMediaIds(false)
    setMediaIdDomain('localhost')
    setMediaIdDomainEdited(false)
    setDpName('')
    setDpTitle('')
    setDpDescription('')
    setDpHomepage('')
    setDpVersion('')
    setDpContributors([])
    setDpRightsHolder(CAMTRAPDP_RIGHTS_HOLDER_OPTIONS[0].title)
    setDpContributorWarnings([])
    setPreprocessing(false)
    setDownload({ status: 'idle', path: null, sourcePath: null, error: null })
    setSummary(null)
    setMetadataError(null)
    setFolderError(null)
    setSelectedRepos(new Set())
    setPublishOrder([])
    setOutputDirs({})
    setDryRun(false)
    setPublishStarted(false)
    setConfigureIndex(0)
    setRepoConfigs({})
    setPrimaryDoiSource(null)
    setExecuting(false)
    setExecutionDone(false)
    setExecutionError(null)
    setProgress({})
  }

  // Builds one repo's config payload for publishAllStart, from whatever
  // that repo's own PublishForm collected during configuration (see
  // handleConfigured) — hfhRepoId is deliberately never included here: in
  // link mode it's resolved server-side, live, right before that repo's
  // own turn to prepare/upload (see the backend's
  // services.publish_orchestrator._detect_hfh_repo_id).
  function buildRepoPayload(repo: RepoId) {
    if (repo === 'hfh') {
      const cfg = repoConfigs.hfh!
      return {
        repo: 'hfh' as const, outputDir: cfg.outputDir, token: cfg.token,
        mirrorImages: cfg.mirrorImages, outputMode: cfg.outputMode, repoId: cfg.repoId, private: cfg.priv,
      }
    }
    if (repo === 'zenodo') {
      const cfg = repoConfigs.zenodo!
      return {
        repo: 'zenodo' as const, outputDir: cfg.outputDir, token: cfg.token,
        mirrorImages: cfg.mirrorImages, outputMode: cfg.outputMode, environment: cfg.environment, communities: cfg.communities,
        fitArchiveSize: cfg.fitArchiveSize, maxZipFile: cfg.maxZipFile, minImageEdge: cfg.minImageEdge,
      }
    }
    if (repo === 'b2share') {
      const cfg = repoConfigs.b2share!
      return {
        repo: 'b2share' as const, outputDir: cfg.outputDir, token: cfg.token,
        mirrorImages: cfg.mirrorImages, outputMode: cfg.outputMode, environment: cfg.environment, communityId: cfg.communityId,
        fitArchiveSize: cfg.fitArchiveSize, maxZipFile: cfg.maxZipFile, minImageEdge: cfg.minImageEdge,
      }
    }
    const cfg = repoConfigs.gbif!
    return {
      repo: 'gbif' as const, outputDir: cfg.outputDir, mirrorImages: true, outputMode: 'prepared' as const,
      archiveUrl: cfg.archiveUrl, environment: cfg.environment,
      publishingOrganizationKey: cfg.publishingOrganizationKey, installationKey: cfg.installationKey,
      registryLanguage: cfg.registryLanguage, username: cfg.username, password: cfg.password,
    }
  }

  // Publishes `repos` (a subset of, or the full, publishOrder) in one
  // backend call: upload phase for all of them, then a cross-repo DOI
  // populate pass, then release/lock for all of them (see
  // services.publish_orchestrator) — polls a single task_id for a per-repo
  // progress dict. Only touches `progress`/`outputDirs` entries for the
  // repos actually being (re)run here, so a retry of just the failed ones
  // (see retryFailedRepos) doesn't clobber what earlier repos already
  // reported — e.g. Hugging Face Hub's "✓ Done" and its repo_url stay
  // exactly as they were while GBIF alone retries.
  async function publish(repos: RepoId[], inputDir: string, mediaDir?: string) {
    setExecuting(true)
    setExecutionError(null)
    setProgress((p) => ({ ...p, ...Object.fromEntries(repos.map((repo) => [repo, IDLE_PROGRESS])) }))
    try {
      const { task_id } = await api.publishAllStart({
        inputDir,
        mediaDir,
        version: summary?.version,
        timeout: IMAGE_TIMEOUT,
        repos: repos.map(buildRepoPayload),
        primaryDoiSource: primaryDoiSource ?? undefined,
        dryRun,
      })

      while (true) {
        await sleep(2000)
        const status = await api.publishAllStatus(task_id)

        // progressRef captures what THIS poll makes the full picture look
        // like (untouched repos keep their prior — already-rendered —
        // state, since `progress` here closes over the value from whenever
        // `publish` was called) — used below to decide whether every
        // repository in publishOrder is now actually done, not just the
        // subset this particular call covered.
        const progressAfterThisPoll = { ...progress }
        for (const repo of repos) {
          const r = status.repos[repo]
          if (!r) continue
          progressAfterThisPoll[repo] = {
            status: r.status, stage: r.stage, error: r.error,
            repoUrl: r.repo_url, doi: r.doi, pid: r.pid,
            doiSyncedToHfh: r.doi_synced_to_hfh ?? null,
          }
        }
        setProgress((p) => ({ ...p, ...progressAfterThisPoll }))
        setOutputDirs((o) => {
          const next = { ...o }
          for (const repo of repos) {
            const outputDir = status.repos[repo]?.output_dir
            if (outputDir) next[repo] = outputDir
          }
          return next
        })

        if (status.status === 'done') {
          const allDone = publishOrder.every((repo) => progressAfterThisPoll[repo]?.status === 'done')
          setExecutionDone(allDone)
          if (!allDone) setExecuting(false)
          return
        }
        if (status.status === 'error') {
          setExecutionError(status.error ?? 'The publish failed.')
          return
        }
      }
    } catch (e) {
      setExecutionError(e instanceof Error ? e.message : 'Could not start publishing.')
    }
  }

  function runPublishSequence() {
    return publish(publishOrder, download.path ?? '', download.sourcePath ?? undefined)
  }

  // Retries only the repositories that haven't succeeded yet — everything
  // in publishOrder from the first non-"done" one onward (a failed one,
  // plus any still-pending ones after it in the order). Re-running
  // everything, including an already fully-published Hugging Face Hub,
  // isn't just wasteful: HFH's own upload rejects re-publishing a version
  // that's already been tagged/released, so it would actively fail the
  // retry for no reason. Reuses the last already-done repo's own
  // (finalized) output_dir as input, same chaining the first run used.
  function retryFailedRepos() {
    const firstNotDoneIndex = publishOrder.findIndex((repo) => progress[repo]?.status !== 'done')
    if (firstNotDoneIndex === -1) return
    const reposToRetry = publishOrder.slice(firstNotDoneIndex)
    const inputDir = firstNotDoneIndex === 0
      ? (download.path ?? '')
      : (outputDirs[publishOrder[firstNotDoneIndex - 1]] ?? download.path ?? '')
    // mediaDir only makes sense when this retry's first repo is genuinely
    // the chain's first repo (input_dir === download.path) — otherwise
    // inputDir is already a later repo's own build_dir, which has no
    // separate original media location of its own.
    const mediaDir = firstNotDoneIndex === 0 ? (download.sourcePath ?? undefined) : undefined
    return publish(reposToRetry, inputDir, mediaDir)
  }

  // Suggests a domain for randomize-media-ids as soon as the chosen source
  // resolves one — the actual Trapper server's host, or the public
  // archive URL's host — without overwriting anything the user already
  // typed by hand. Local/git sources have no server of their own, so they
  // keep the "localhost" default (still editable).
  useEffect(() => {
    if (mediaIdDomainEdited) return
    const urlToHost = (url: string) => {
      try { return new URL(url).hostname } catch { return null }
    }
    if (sourceType === 'trapper' && trapperSelection?.url) {
      const host = urlToHost(trapperSelection.url)
      if (host) setMediaIdDomain(host)
    } else if (sourceType === 'archive' && archiveSourceUrl) {
      const host = urlToHost(archiveSourceUrl)
      if (host) setMediaIdDomain(host)
    }
  }, [sourceType, trapperSelection, archiveSourceUrl, mediaIdDomainEdited])

  // Pre-fills datapackage.json's own name/title/description/homepage/
  // version as soon as the source resolves, so the user can review/edit
  // them (step === 2 below) before preprocessing runs. Camtrap DP only —
  // other product types have no datapackage.json of their own. Only
  // depends on download.path, so it won't clobber the user's edits on a
  // later re-render (e.g. going Back and Next again without re-downloading).
  useEffect(() => {
    if (download.status !== 'done' || !download.path || productType !== 'camtrapdp') return
    api.datapackageFields(download.path).then((fields) => {
      setDpName(fields.name ?? '')
      setDpTitle(fields.title ?? '')
      setDpDescription(fields.description ?? '')
      setDpHomepage(fields.homepage ?? '')
      setDpVersion(fields.version ?? '')
      const allContributors = fields.contributors ?? []
      // Pre-select whichever known institution is already the rightsHolder,
      // if any — otherwise fall back to the first option. Any OTHER
      // rightsHolder (not one of our known institutions) or any other
      // "publisher" than wildintel-publisher itself gets excluded below:
      // neither of those roles is ever left in the generic, per-contributor
      // list. Warn about it whenever that actually changes something, so
      // it's never a silent surprise once "Continue" overwrites it.
      const warnings: string[] = []
      const existingPublisher = allContributors.find((c) => c.role === 'publisher')
      if (existingPublisher && existingPublisher.title !== CAMTRAPDP_PUBLISHER.title) {
        warnings.push(
          `"${existingPublisher.title || 'Unnamed'}" was listed as publisher in the source, but only ` +
          `WildINTEL can be the publisher — it will be replaced when you continue.`,
        )
      }
      const existingRightsHolder = allContributors.find((c) => c.role === 'rightsHolder')
      const matchedRightsHolder = CAMTRAPDP_RIGHTS_HOLDER_OPTIONS.find((o) => o.title === existingRightsHolder?.title)
      if (existingRightsHolder && !matchedRightsHolder) {
        warnings.push(
          `"${existingRightsHolder.title || 'Unnamed'}" was listed as rights holder in the source, but ` +
          `isn't one of the selectable institutions — choose one below, or it will default to ` +
          `"${CAMTRAPDP_RIGHTS_HOLDER_OPTIONS[0].title}" when you continue.`,
        )
      }
      setDpContributorWarnings(warnings)
      setDpRightsHolder(matchedRightsHolder?.title ?? CAMTRAPDP_RIGHTS_HOLDER_OPTIONS[0].title)
      setDpContributors(allContributors.filter((c) => c.role !== 'publisher' && c.role !== 'rightsHolder'))
    }).catch(() => { /* best-effort — the fields just stay blank/editable */ })
  }, [download.status, download.path, productType])

  // Triggered by the new step's own "Continue" button (step === 2 below) —
  // no longer automatic, so the user gets to review/edit datapackage.json's
  // fields and the anonymize/randomize options before anything actually
  // runs. Idempotent: re-running this (e.g. after "Back") is safe — an
  // already-rounded coordinate or an already-UUID mediaID is a no-op, and
  // update_datapackage_fields/generate_metadata_json both just overwrite
  // with whatever's currently in the form.
  async function handleContinueToPreprocessing() {
    if (!download.path || !productType) return
    setPreprocessing(true)
    setSummary(null)
    setMetadataError(null)
    try {
      if (productType === 'camtrapdp') {
        const rightsHolderOption = CAMTRAPDP_RIGHTS_HOLDER_OPTIONS.find((o) => o.title === dpRightsHolder)
          ?? CAMTRAPDP_RIGHTS_HOLDER_OPTIONS[0]
        await api.updateDatapackageFields(download.path, {
          name: dpName, title: dpTitle, description: dpDescription, homepage: dpHomepage, version: dpVersion,
          contributors: [
            CAMTRAPDP_PUBLISHER,
            { title: rightsHolderOption.title, path: rightsHolderOption.path, role: 'rightsHolder' },
            ...dpContributors,
          ],
        })
      }
      const newSummary = await api.generateProductMetadata(
        download.path, productType, anonymizeCoordinates, coordinateDecimals, randomizeMediaIds, mediaIdDomain,
      )
      setSummary(newSummary)
      setStep(3)
    } catch (e) {
      setSummary(null)
      setMetadataError(e instanceof Error ? e.message : 'Could not read this package.')
    } finally {
      setPreprocessing(false)
    }
  }

  async function handleOpenFolder() {
    if (!download.path) return
    setFolderError(null)
    try {
      await api.openFolder(download.path)
    } catch (e) {
      setFolderError(e instanceof Error ? e.message : 'Could not open the folder.')
    }
  }

  async function handleNext() {
    if (sourceType === 'local') {
      if (!localSelection) return
      setDownload({ status: 'done', path: localSelection.path, sourcePath: localSelection.sourcePath, error: null })
      setStep(2)
      return
    }
    if (sourceType === 'git') {
      if (!gitUrl) return
      setDownload({ status: 'running', path: null, sourcePath: null, error: null })
      try {
        const { task_id } = await api.softwareCloneStart(gitUrl)
        // Poll until the background task finishes
        while (true) {
          await sleep(2000)
          const status = await api.softwareCloneStatus(task_id)
          if (status.status === 'done') {
            setDownload({ status: 'done', path: status.path, sourcePath: status.path, error: null })
            setStep(2)
            break
          }
          if (status.status === 'error') {
            setDownload({ status: 'error', path: null, sourcePath: null, error: status.error ?? 'The clone failed.' })
            break
          }
        }
      } catch (e) {
        setDownload({ status: 'error', path: null, sourcePath: null, error: e instanceof Error ? e.message : 'Could not start the clone.' })
      }
      return
    }
    if (sourceType === 'archive') {
      if (!archiveSourceUrl) return
      setDownload({ status: 'running', path: null, sourcePath: null, error: null })
      try {
        const { task_id } = await api.camtrapdpFetchArchiveStart(archiveSourceUrl)
        // Poll until the background task finishes
        while (true) {
          await sleep(2000)
          const status = await api.camtrapdpFetchArchiveStatus(task_id)
          if (status.status === 'done') {
            setDownload({ status: 'done', path: status.path, sourcePath: status.path, error: null })
            setStep(2)
            break
          }
          if (status.status === 'error') {
            setDownload({ status: 'error', path: null, sourcePath: null, error: status.error ?? 'The fetch failed.' })
            break
          }
        }
      } catch (e) {
        setDownload({ status: 'error', path: null, sourcePath: null, error: e instanceof Error ? e.message : 'Could not start the fetch.' })
      }
      return
    }
    if (!trapperSelection) return
    setDownload({ status: 'running', path: null, sourcePath: null, error: null })
    try {
      const { task_id } = await api.trapperStartDownload(
        trapperSelection.url, trapperSelection.username, trapperSelection.password,
        trapperSelection.projectId, trapperSelection.deploymentId, trapperSelection.includeEvents,
      )
      // Poll until the background task finishes
      while (true) {
        await sleep(2000)
        const status = await api.trapperDownloadStatus(task_id)
        if (status.status === 'done') {
          setDownload({ status: 'done', path: status.path, sourcePath: status.path, error: null })
          setStep(2)
          break
        }
        if (status.status === 'error') {
          setDownload({ status: 'error', path: null, sourcePath: null, error: status.error ?? 'The download failed.' })
          break
        }
      }
    } catch (e) {
      setDownload({ status: 'error', path: null, sourcePath: null, error: e instanceof Error ? e.message : 'Could not start the download.' })
    }
  }

  return (
    <div className="mx-auto px-4 py-4" style={{ maxWidth: 700 }}>

      {/* Step indicator */}
      <div className="flex items-start mb-10">
        {STEP_LABELS.map((label, i) => (
          <div key={i} className="flex items-start flex-1">
            <div className="flex flex-col items-center" style={{ minWidth: 56 }}>
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center font-bold mb-1 text-sm ${
                  i < step
                    ? 'bg-emerald-600 text-white'
                    : i === step
                    ? 'bg-blue-600 text-white'
                    : 'bg-zinc-700 text-zinc-400'
                }`}
              >
                {i < step ? '✓' : i + 1}
              </div>
              <small className={`text-xs whitespace-nowrap ${
                i === step ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-500 dark:text-zinc-400'
              }`}>
                {label}
              </small>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div className={`flex-1 border-t mx-1 mt-[18px] ${i < step ? 'border-emerald-500' : 'border-zinc-700'}`} />
            )}
          </div>
        ))}
      </div>

      {/* ── Step 0: product type ── */}
      {step === 0 && (
        <div>
          <h4 className="text-lg font-semibold mb-1">What do you want to publish?</h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">Choose the type of product you want to fetch and publish.</p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {PRODUCT_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={!option.available}
                onClick={() => {
                  setProductType(option.value)
                  // Reset repo selection for the newly-chosen product type
                  // rather than carrying over whatever was picked for a
                  // previous one (e.g. going Back from Software's own
                  // mandatory Zenodo to pick Camtrap DP instead) — seeded
                  // with that type's own mandatory repos, if any.
                  const mandatory = MANDATORY_REPOS_BY_PRODUCT_TYPE[option.value] ?? []
                  setSelectedRepos(new Set(mandatory))
                  setPublishOrder(mandatory)
                  setStep(1)
                }}
                className={[
                  'relative flex flex-col items-center gap-3 p-6 rounded-xl border-2 text-center transition-colors',
                  !option.available
                    ? 'border-zinc-200 dark:border-zinc-800 opacity-50 cursor-not-allowed'
                    : productType === option.value
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 cursor-pointer'
                    : 'border-zinc-300 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950/30 cursor-pointer',
                ].join(' ')}
              >
                {!option.available && (
                  <span className="absolute top-2 right-2 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700 text-zinc-500 dark:text-zinc-400">
                    Coming soon
                  </span>
                )}
                <span className="text-4xl">{option.emoji}</span>
                <strong className="text-zinc-900 dark:text-zinc-100">{option.title}</strong>
                <span className="text-zinc-500 dark:text-zinc-400 text-sm">{option.description}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Step 1: source ── */}
      {step === 1 && (
        <div>
          <h4 className="text-lg font-semibold mb-1">Where is it located?</h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">Choose where to fetch the package from.</p>

          <div className={`grid grid-cols-1 gap-4 ${sourceOptions.length >= 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
            {sourceOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={!option.available}
                onClick={() => setSourceType(option.value)}
                className={[
                  'relative flex flex-col items-center gap-3 p-6 rounded-xl border-2 text-center transition-colors',
                  !option.available
                    ? 'border-zinc-200 dark:border-zinc-800 opacity-50 cursor-not-allowed'
                    : sourceType === option.value
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 cursor-pointer'
                    : 'border-zinc-300 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950/30 cursor-pointer',
                ].join(' ')}
              >
                <span className="text-4xl">{option.emoji}</span>
                <strong className="text-zinc-900 dark:text-zinc-100">{option.title}</strong>
                <span className="text-zinc-500 dark:text-zinc-400 text-sm">{option.description}</span>
              </button>
            ))}
          </div>

          {sourceType === 'trapper' && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <TrapperConnectionForm onSelectionChange={setTrapperSelection} />
            </div>
          )}

          {sourceType === 'local' && productType && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <LocalDirectoryForm productType={productType} onSelectionChange={setLocalSelection} />
            </div>
          )}

          {sourceType === 'git' && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <GitCloneForm onSelectionChange={setGitUrl} />
            </div>
          )}

          {sourceType === 'archive' && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <CamtrapDPArchiveForm onSelectionChange={setArchiveSourceUrl} />
            </div>
          )}
        </div>
      )}

      {/* ── Step 2: metadata review + anonymize/randomize, before preprocessing ── */}
      {step === 2 && download.status === 'done' && (
        <div>
          <h4 className="text-lg font-semibold mb-1">Review metadata</h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            {productType === 'camtrapdp'
              ? "Edit the package's own datapackage.json fields if needed, then choose any preprocessing before continuing."
              : 'Ready to process this package.'}
          </p>

          {productType === 'camtrapdp' && (
            <div className="space-y-4">
              <div>
                <label htmlFor="dp-name" className="block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Name</label>
                <input
                  id="dp-name" type="text" value={dpName} onChange={(e) => setDpName(e.target.value)}
                  aria-invalid={!dpNameValid}
                  className={`w-full px-3 py-2 text-sm rounded border bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-mono ${dpNameValid ? 'border-zinc-300 dark:border-zinc-700' : 'border-red-500 dark:border-red-500'}`}
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  A short, url-usable (and preferably human-readable) name of the package.
                </p>
                {!dpNameValid && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                    Must be lower-case and contain only alphanumeric characters along with "." "_" or "-".
                  </p>
                )}
              </div>
              <div>
                <label htmlFor="dp-title" className="block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Title</label>
                <input
                  id="dp-title" type="text" value={dpTitle} onChange={(e) => setDpTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  A string providing a title or one sentence description for this package.
                </p>
              </div>
              <div>
                <label htmlFor="dp-description" className="block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Description</label>
                <textarea
                  id="dp-description" rows={3} value={dpDescription} onChange={(e) => setDpDescription(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  A description of the package. The description MUST be Markdown formatted. A WildINTEL
                  attribution paragraph is always appended automatically — no need to add it here.
                </p>
              </div>
              <div>
                <label htmlFor="dp-homepage" className="block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Homepage</label>
                <input
                  id="dp-homepage" type="text" value={dpHomepage} onChange={(e) => setDpHomepage(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-mono"
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  A URL for the home on the web that is related to this data package.
                </p>
              </div>
              <div>
                <label htmlFor="dp-version" className="block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Version</label>
                <input
                  id="dp-version" type="text" value={dpVersion} onChange={(e) => setDpVersion(e.target.value)}
                  aria-invalid={!dpVersionValid}
                  className={`w-full sm:w-48 px-3 py-2 text-sm rounded border bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-mono ${dpVersionValid ? 'border-zinc-300 dark:border-zinc-700' : 'border-red-500 dark:border-red-500'}`}
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  A version string identifying the version of the package.
                </p>
                {!dpVersionValid && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                    Use the form N, N.N or N.N.N (e.g. 2, 2.1, 2.1.3) — only the first number is required.
                  </p>
                )}
              </div>
            </div>
          )}

          {productType === 'camtrapdp' && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <h5 className="text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Contributors</h5>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
                Publisher and rights holder are fixed roles, always present. For everyone else, only their
                role can be changed here — name, email and affiliation come from the source and are shown
                for reference only.
              </p>
              {dpContributorWarnings.length > 0 && (
                <div className="mb-3 space-y-1">
                  {dpContributorWarnings.map((warning, i) => (
                    <p key={i} className="text-sm text-amber-600 dark:text-amber-400">⚠ {warning}</p>
                  ))}
                </div>
              )}
              <div className="space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex-1 min-w-[10rem] text-sm">
                    <div className="text-zinc-900 dark:text-zinc-100">{CAMTRAPDP_PUBLISHER.title}</div>
                    <div className="text-xs text-zinc-500 dark:text-zinc-400">{CAMTRAPDP_PUBLISHER.email}</div>
                  </div>
                  <span className="px-2 py-1.5 text-sm rounded border border-zinc-200 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 text-zinc-500 dark:text-zinc-400">
                    publisher
                  </span>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex-1 min-w-[10rem] text-sm text-zinc-500 dark:text-zinc-400">
                    Rights holder
                  </div>
                  <select
                    aria-label="Rights holder"
                    value={dpRightsHolder}
                    onChange={(e) => setDpRightsHolder(e.target.value)}
                    className="px-2 py-1.5 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100"
                  >
                    {CAMTRAPDP_RIGHTS_HOLDER_OPTIONS.map((option) => (
                      <option key={option.title} value={option.title}>{option.title}</option>
                    ))}
                  </select>
                </div>
                {dpContributors.map((contributor, i) => (
                  <div key={i} className="flex items-center gap-3 flex-wrap">
                    <div className="flex-1 min-w-[10rem] text-sm">
                      <div className="text-zinc-900 dark:text-zinc-100">{contributor.title || 'Unnamed contributor'}</div>
                      {(contributor.email || contributor.organization) && (
                        <div className="text-xs text-zinc-500 dark:text-zinc-400">
                          {[contributor.email, contributor.organization].filter(Boolean).join(' · ')}
                        </div>
                      )}
                    </div>
                    <select
                      aria-label={`Role for ${contributor.title || 'this contributor'}`}
                      value={contributor.role ?? 'contributor'}
                      onChange={(e) => {
                        const role = e.target.value
                        setDpContributors((prev) => prev.map((c, j) => (j === i ? { ...c, role } : c)))
                      }}
                      className="px-2 py-1.5 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100"
                    >
                      {EDITABLE_CONTRIBUTOR_ROLES.map((role) => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          {productType === 'camtrapdp' && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={anonymizeCoordinates}
                  onChange={(e) => setAnonymizeCoordinates(e.target.checked)}
                  className="mt-1 w-4 h-4 rounded border-zinc-300 dark:border-zinc-600 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm">
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">Anonymize deployment coordinates</span>
                  <span className="block text-zinc-500 dark:text-zinc-400">
                    Rounds every deployment's latitude/longitude before publishing, instead of
                    publishing the exact camera-trap location — useful for sensitive sites (poaching
                    risk, protected species, private land). The same rounding is applied wherever
                    this package is published, so every repository ends up with identical
                    coordinates.
                  </span>
                </span>
              </label>
              {anonymizeCoordinates && (
                <div className="mt-3 ml-7 flex items-center gap-2">
                  <label htmlFor="coordinate-decimals" className="text-sm text-zinc-600 dark:text-zinc-400">
                    Decimal places:
                  </label>
                  <input
                    id="coordinate-decimals"
                    type="number"
                    min={0}
                    max={6}
                    value={coordinateDecimals}
                    onChange={(e) => setCoordinateDecimals(Number(e.target.value))}
                    className="w-16 rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1 text-sm"
                  />
                  <span className="text-sm text-zinc-500 dark:text-zinc-400">(2 ≈ 1.1 km, 1 ≈ 11 km)</span>
                </div>
              )}
              <label className="flex items-start gap-3 cursor-pointer mt-4">
                <input
                  type="checkbox"
                  checked={randomizeMediaIds}
                  onChange={(e) => setRandomizeMediaIds(e.target.checked)}
                  className="mt-1 w-4 h-4 rounded border-zinc-300 dark:border-zinc-600 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm">
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">Randomize media IDs</span>
                  <span className="block text-zinc-500 dark:text-zinc-400">
                    Replaces every mediaID that isn't already a UUID with one derived from the
                    domain below, keeping media.csv and observations.csv in sync — avoids leaking
                    the original export's own numbering convention, and stays consistent if this
                    same source is downloaded again later (re-running this produces the same ids,
                    it doesn't regenerate new ones).
                  </span>
                </span>
              </label>
              {randomizeMediaIds && (
                <div className="mt-3 ml-7">
                  <div className="flex items-center gap-2">
                    <label htmlFor="media-id-domain" className="text-sm text-zinc-600 dark:text-zinc-400">
                      Media ID domain:
                    </label>
                    <input
                      id="media-id-domain"
                      type="text"
                      value={mediaIdDomain}
                      onChange={(e) => { setMediaIdDomain(e.target.value); setMediaIdDomainEdited(true) }}
                      className="w-56 rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1 text-sm font-mono"
                    />
                  </div>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                    Distinguishes this source's own mediaID numbering from any other's — auto-filled
                    from the Trapper/archive URL when available. For a local directory, use a
                    different value per dataset if you plan to process more than one, so their ids
                    never collide with each other.
                  </p>
                </div>
              )}
            </div>
          )}

          {metadataError && (
            <p className="mt-6 text-sm text-red-600 dark:text-red-400">{metadataError}</p>
          )}
        </div>
      )}

      {/* ── Step 3: download result ── */}
      {step === 3 && download.status === 'done' && (
        <div>
          <h4 className="text-lg font-semibold mb-1">
            {sourceType === 'local' ? 'Package ready' : 'Package downloaded'}
          </h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            {sourceType === 'local' ? 'The package is ready to use.' : 'The package was fetched successfully.'}
          </p>

          <div className="flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 text-sm">
            <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span className="font-mono break-all">{download.path}</span>
          </div>

          <div className="flex flex-col items-start gap-2 mt-3">
            <button type="button" className={btnOutline} onClick={handleOpenFolder}>
              Open folder
            </button>
            {folderError && <p className="text-sm text-red-600 dark:text-red-400">{folderError}</p>}
          </div>

          {metadataError && (
            <p className="mt-6 text-sm text-red-600 dark:text-red-400">{metadataError}</p>
          )}

          {summary && !metadataComplete && (
            <CompleteMetadataForm
              inputDir={download.path ?? ''}
              summary={summary}
              onComplete={setSummary}
            />
          )}

          {summary && metadataComplete && (
            <div className="mt-6 p-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
              <h5 className="font-semibold text-zinc-900 dark:text-zinc-100 mb-3">
                {summary.title ?? 'metadata.json'}
              </h5>

              {summary.description && (
                <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-3">{summary.description}</p>
              )}

              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                {summary.version && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">Version</dt>
                    <dd className="text-zinc-800 dark:text-zinc-200">{summary.version}</dd>
                  </>
                )}
                {summary.license && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">License</dt>
                    <dd className="text-zinc-800 dark:text-zinc-200">
                      {summary.license.name ?? summary.license.id}
                    </dd>
                  </>
                )}
                {summary.authors.length > 0 && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">Authors</dt>
                    <dd className="text-zinc-800 dark:text-zinc-200">
                      {summary.authors.map((a) => a.name).filter(Boolean).join(', ')}
                    </dd>
                  </>
                )}
                {summary.homepage && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">Homepage</dt>
                    <dd className="text-zinc-800 dark:text-zinc-200 break-all">
                      <a href={summary.homepage} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">
                        {summary.homepage}
                      </a>
                    </dd>
                  </>
                )}
              </dl>

              {productType === 'software' && summary.version && (
                summary.checked_out_tag ? (
                  <p className="mt-3 text-sm text-emerald-600 dark:text-emerald-400">
                    ✓ Checked out tag <span className="font-mono">{summary.checked_out_tag}</span> — matches
                    CITATION.cff's own version.
                  </p>
                ) : (
                  <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">
                    ⚠ No git tag matches version <span className="font-mono">{summary.version}</span> —
                    publishing from the default branch's latest commit instead, which may not be what
                    CITATION.cff actually describes.
                  </p>
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Step 4: repository selection ── */}
      {step === 4 && !publishStarted && (
        <div>
          <h4 className="text-lg font-semibold mb-1">Where do you want to publish it?</h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            Choose one or more repositories to publish the package to.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {REPO_OPTIONS.map((option) => {
              const available = option.implemented && supportedRepos.includes(option.value)
              const selected = selectedRepos.has(option.value)
              const mandatory = productType ? (MANDATORY_REPOS_BY_PRODUCT_TYPE[productType] ?? []).includes(option.value) : false
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={!available || mandatory}
                  onClick={() => toggleRepo(option.value)}
                  className={[
                    'relative flex flex-col items-center gap-3 p-6 rounded-xl border-2 text-center transition-colors',
                    !available
                      ? 'border-zinc-200 dark:border-zinc-800 opacity-50 cursor-not-allowed'
                      : selected
                      ? `border-blue-500 bg-blue-50 dark:bg-blue-950/30 ${mandatory ? 'cursor-default' : 'cursor-pointer'}`
                      : 'border-zinc-300 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950/30 cursor-pointer',
                  ].join(' ')}
                >
                  {!option.implemented ? (
                    <span className="absolute top-2 right-2 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700 text-zinc-500 dark:text-zinc-400">
                      Coming soon
                    </span>
                  ) : mandatory ? (
                    <span className="absolute top-2 right-2 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300">
                      Required
                    </span>
                  ) : null}
                  {selected && (
                    <span className="absolute top-2 left-2 w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                  )}
                  <span className="text-4xl">{option.emoji}</span>
                  <strong className="text-zinc-900 dark:text-zinc-100">{option.title}</strong>
                  <span className="text-zinc-500 dark:text-zinc-400 text-sm">{option.description}</span>
                </button>
              )
            })}
          </div>

          {hfhGbifOrderLocked && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <h5 className="text-base font-semibold mb-1 text-zinc-700 dark:text-zinc-300">Publish order</h5>
              <p className="text-zinc-500 dark:text-zinc-400 text-sm">
                Hugging Face Hub always publishes first, then GBIF — its archive URL is derived from
                where Hugging Face Hub ends up, so there's nothing to reorder here.
              </p>
            </div>
          )}

          {publishOrder.length > 1 && !hfhGbifOrderLocked && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <h5 className="text-base font-semibold mb-1 text-zinc-700 dark:text-zinc-300">Publish order</h5>
              <p className="text-zinc-500 dark:text-zinc-400 mb-4 text-sm">
                The first repository publishes the downloaded package itself; each next one publishes
                whatever the previous one wrote to its own output directory.
              </p>
              <ol className="flex flex-col gap-2">
                {publishOrder.map((repoId, i) => {
                  const option = REPO_OPTIONS.find((o) => o.value === repoId)
                  if (!option) return null
                  return (
                    <li
                      key={repoId}
                      className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700"
                    >
                      <span className="text-sm text-zinc-800 dark:text-zinc-200">
                        <span className="font-semibold">{i + 1}.</span> {option.emoji} {option.title}
                      </span>
                      <div className="flex gap-1">
                        <button
                          type="button"
                          className={btnOutline + ' px-2 py-1'}
                          disabled={i === 0}
                          onClick={() => moveInOrder(repoId, -1)}
                          aria-label={`Move ${option.title} up`}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className={btnOutline + ' px-2 py-1'}
                          disabled={i === publishOrder.length - 1}
                          onClick={() => moveInOrder(repoId, 1)}
                          aria-label={`Move ${option.title} down`}
                        >
                          ↓
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </div>
          )}

          {selectedRepos.size > 0 && (
            <div className="mt-8">
              <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="mt-1 w-4 h-4 rounded border-zinc-300 dark:border-zinc-600 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm">
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">Dry run</span>
                  <span className="block text-zinc-500 dark:text-zinc-400">
                    Simulates the whole flow — nothing is actually uploaded to or created on Hugging
                    Face Hub, Zenodo, B2SHARE, or GBIF. Zenodo/B2SHARE's DOI is faked, and the DOI
                    cross-referencing step still runs against it, so you can preview exactly how
                    every repository's CITATION.cff would end up. No token/credentials are required
                    in this mode.
                  </span>
                </span>
              </label>
            </div>
          )}

        </div>
      )}

      {/* ── Step 4 (continued): collecting configuration, one repository at a time ── */}
      {step === 4 && publishStarted && !allConfigured && !executing && !executionDone && (
        <div>
          <div className="flex items-center gap-4 mb-6 flex-wrap">
            {publishOrder.map((repoId, i) => {
              const option = REPO_OPTIONS.find((o) => o.value === repoId)
              if (!option) return null
              const label = (
                <>
                  <span>{i < configureIndex ? '✓' : `${i + 1}.`}</span> {option.emoji} {option.title}
                </>
              )
              // Already-configured steps (and the current one) jump back
              // directly, same as the current step's own "Back to X"
              // button — steps not reached yet aren't clickable, since
              // there's nothing configured there to jump to.
              if (i <= configureIndex) {
                return (
                  <button
                    key={repoId}
                    type="button"
                    onClick={() => setConfigureIndex(i)}
                    className={`flex items-center gap-1.5 text-sm hover:underline ${
                      i === configureIndex
                        ? 'text-zinc-900 dark:text-zinc-100 font-semibold'
                        : 'text-emerald-600 dark:text-emerald-400'
                    }`}
                  >
                    {label}
                  </button>
                )
              }
              return (
                <div key={repoId} className="flex items-center gap-1.5 text-sm text-zinc-400 dark:text-zinc-600">
                  {label}
                </div>
              )
            })}
          </div>

          <h4 className="text-lg font-semibold mb-1">
            Configure {REPO_OPTIONS.find((o) => o.value === publishOrder[configureIndex])?.title}
          </h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            Step {configureIndex + 1} of {publishOrder.length}. Nothing is published yet — once every
            repository is configured, you'll get a chance to review before anything actually happens.
          </p>

          {publishOrder[configureIndex] === 'hfh' && (
            <HFHPublishForm
              productTitle={summary?.title}
              productVersion={summary?.version}
              dryRun={dryRun}
              onOutputDirChange={(dir) => setOutputDirs((o) => ({ ...o, hfh: dir }))}
              initialConfig={repoConfigs.hfh}
              {...backProps}
              onConfigured={(config) => handleConfigured('hfh', config)}
            />
          )}
          {publishOrder[configureIndex] === 'zenodo' && (
            <ZenodoPublishForm
              dryRun={dryRun}
              productType={productType}
              onOutputDirChange={(dir) => setOutputDirs((o) => ({ ...o, zenodo: dir }))}
              initialConfig={repoConfigs.zenodo}
              {...backProps}
              onConfigured={(config) => handleConfigured('zenodo', config)}
            />
          )}
          {publishOrder[configureIndex] === 'b2share' && (
            <B2SharePublishForm
              dryRun={dryRun}
              productType={productType}
              onOutputDirChange={(dir) => setOutputDirs((o) => ({ ...o, b2share: dir }))}
              initialConfig={repoConfigs.b2share}
              {...backProps}
              onConfigured={(config) => handleConfigured('b2share', config)}
            />
          )}
          {(() => {
            // camtrapdp-remote.zip is now generated by HFH's own
            // upload_to_huggingface regardless of Mirror/Link mode (see
            // hfh.py) — the zip's own HFH URL is permanent either way, only
            // its internal filePath entries differ (real HFH URLs in Mirror,
            // whatever the original source gave it in Link). toggleRepo
            // always forces HFH before GBIF whenever both are selected, so
            // repoConfigs.hfh is already collected by the time GBIF's own
            // form renders. Zenodo/B2SHARE also produce a camtrapdp-remote.zip
            // of their own now (Link mode) or a GBIF-ready camtrapdp.zip
            // (--self-contained) — but unlike HFH's user-chosen repo_id,
            // their own deposition/record id (and so the file's own public
            // URL) is only assigned by Zenodo/B2SHARE once THEY actually
            // upload, which hasn't happened yet at this configure step — so
            // there's nothing to suggest/lock from them here, only from HFH.
            const hfhWillProduceRemoteZip = publishOrder.includes('hfh')
            const zenodoOrB2shareWithoutHfh = !hfhWillProduceRemoteZip
              && (publishOrder.includes('zenodo') || publishOrder.includes('b2share'))
            return publishOrder[configureIndex] === 'gbif' && (
              <GBIFPublishForm
                dryRun={dryRun}
                {...backProps}
                suggestedArchiveUrl={
                  hfhWillProduceRemoteZip
                    ? `https://huggingface.co/datasets/${repoConfigs.hfh!.repoId}/resolve/main/camtrapdp-remote.zip`
                    // No HFH in this run at all — if the source itself was a
                    // public archive URL (see CamtrapDPArchiveForm), that URL
                    // is already confirmed public and a valid Camtrap DP (the
                    // fetch step validates it the same way GBIF itself would
                    // need it to be), so it's directly reusable here as-is.
                    : sourceType === 'archive' && archiveSourceUrl
                      ? archiveSourceUrl
                      : undefined
                }
                archiveUrlLocked={hfhWillProduceRemoteZip}
                archiveNotPublishedYet={hfhWillProduceRemoteZip}
                // The "this isn't the local copy" note only makes sense for a
                // local/Trapper source — a Public URL source IS already the
                // real archive, nothing to clarify.
                standaloneRegistration={!hfhWillProduceRemoteZip && !zenodoOrB2shareWithoutHfh && sourceType !== 'archive'}
                pendingFromOtherRepo={zenodoOrB2shareWithoutHfh}
                initialConfig={repoConfigs.gbif}
                onConfigured={(config) => handleConfigured('gbif', config)}
              />
            )
          })()}
        </div>
      )}

      {/* ── Step 4 (continued): hfh + zenodo + b2share all selected — choose which DOI is primary for HFH ── */}
      {step === 4 && allConfigured && needsPrimaryDoiChoice && primaryDoiSource === null && !executing && !executionDone && (
        <div>
          <h4 className="text-lg font-semibold mb-1">Which DOI should Hugging Face Hub cite as primary?</h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            Hugging Face Hub doesn't mint its own DOI — once Zenodo and B2SHARE each reserve
            theirs, both get cross-referenced into every repository's citation, but Hugging Face
            Hub needs one of them picked as the main one.
          </p>
          <div className="flex flex-col gap-2 mb-8">
            <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
              <input
                type="radio" name="primary-doi-source" className="mt-0.5"
                checked={primaryDoiSource === ('zenodo' as const)}
                onChange={() => setPrimaryDoiSource('zenodo')}
              />
              <span><strong>Zenodo</strong></span>
            </label>
            <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
              <input
                type="radio" name="primary-doi-source" className="mt-0.5"
                checked={primaryDoiSource === ('b2share' as const)}
                onChange={() => setPrimaryDoiSource('b2share')}
              />
              <span><strong>B2SHARE (EUDAT)</strong></span>
            </label>
          </div>
        </div>
      )}

      {/* ── Step 4 (continued): all configured — confirm before publishing ── */}
      {step === 4 && readyToConfirm && !executing && !executionDone && (
        <div>
          <h4 className="text-lg font-semibold mb-1 flex items-center gap-2">
            Ready to publish
            {dryRun && <DryRunBadge />}
          </h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            {dryRun
              ? 'All the information needed has been collected. This is a dry run — nothing will actually be uploaded or created for:'
              : 'All the information needed has been collected. Publishing will now start for:'}{' '}
            {publishOrder.map((repoId) => REPO_OPTIONS.find((o) => o.value === repoId)?.title).join(', ')}.
          </p>
          <div className="flex justify-end">
            <button type="button" className={btnPrimary} onClick={runPublishSequence}>
              {dryRun ? 'Start dry run now' : 'Start publishing now'}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 4 (continued): live progress while publishing runs automatically ── */}
      {step === 4 && executing && !executionDone && (
        <div>
          <h4 className="text-lg font-semibold mb-1 flex items-center gap-2">
            {dryRun ? 'Simulating…' : 'Publishing…'}
            {dryRun && <DryRunBadge />}
          </h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            Each repository {dryRun ? 'is simulated' : 'publishes automatically'}, one after another.
          </p>
          <ul className="flex flex-col gap-3">
            {publishOrder.map((repoId) => {
              const option = REPO_OPTIONS.find((o) => o.value === repoId)
              if (!option) return null
              const repoProgress = progress[repoId] ?? IDLE_PROGRESS
              return (
                <li key={repoId} className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 text-sm flex-wrap">
                  <span>{option.emoji}</span>
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">{option.title}</span>
                  <span className="flex-1" />
                  {repoProgress.status === 'pending' && <span className="text-zinc-400 dark:text-zinc-600">Waiting…</span>}
                  {repoProgress.status === 'running' && (
                    <span className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
                      <SmallSpinner /> {STAGE_LABELS[repoProgress.stage] ?? 'Publishing…'}
                    </span>
                  )}
                  {repoProgress.status === 'done' && (
                    <span className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                      ✓ Done
                      {repoProgress.repoUrl && (
                        <a
                          href={repoProgress.repoUrl} target="_blank" rel="noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline break-all font-normal"
                        >
                          {repoProgress.repoUrl}
                        </a>
                      )}
                    </span>
                  )}
                  {repoProgress.status === 'error' && <span className="text-red-600 dark:text-red-400">✘ {repoProgress.error}</span>}
                </li>
              )
            })}
          </ul>
          {executionError && (
            <div className="mt-6">
              <p className="text-sm text-red-600 dark:text-red-400 mb-3">{executionError}</p>
              <div className="flex justify-end gap-3">
                <button type="button" className={btnOutline} onClick={() => setExecuting(false)}>
                  Back
                </button>
                <button type="button" className={btnPrimary} onClick={retryFailedRepos}>
                  Retry failed repositories
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 4 (continued): all repositories published ── */}
      {step === 4 && executionDone && (
        <div>
          <h4 className="text-lg font-semibold mb-1 flex items-center gap-2">
            {dryRun ? 'Dry run complete!' : 'All done!'}
            {dryRun && <DryRunBadge />}
          </h4>
          <div className="flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 text-sm">
            <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span>
              {dryRun ? 'Simulated for' : 'Published to'}: {publishOrder.map((repoId) => REPO_OPTIONS.find((o) => o.value === repoId)?.title).join(', ')}.
              {dryRun && ' Nothing real was created — check each repo\'s output_dir below to inspect the generated files.'}
            </span>
          </div>

          {!dryRun && (
            <ul className="flex flex-col gap-2 mt-4">
              {publishOrder.map((repoId) => {
                const option = REPO_OPTIONS.find((o) => o.value === repoId)
                const repoUrl = progress[repoId]?.repoUrl
                if (!option || !repoUrl) return null
                return (
                  <li key={repoId} className="flex flex-col gap-1 text-sm">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span>{option.emoji}</span>
                      <span className="font-semibold text-zinc-800 dark:text-zinc-200">{option.title}:</span>
                      <a
                        href={repoUrl} target="_blank" rel="noreferrer"
                        className="text-blue-600 dark:text-blue-400 hover:underline break-all"
                      >
                        {repoUrl}
                      </a>
                    </div>
                    {repoId === 'gbif' && (
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 pl-6">
                        GBIF crawls new/updated endpoints within a few hours, not instantly — the dataset page
                        above is live now, but the images/occurrences themselves will only show up there once
                        that crawl finishes.
                      </p>
                    )}
                  </li>
                )
              })}
            </ul>
          )}

          {dryRun ? (
            <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
              DOI/PID sync isn't available for a dry run (it would perform a real Hugging Face Hub
              upload) — the DOI cross-referencing already ran, simulated, as part of this dry run.
            </p>
          ) : (
            <>
              {publishOrder.includes('zenodo') && <SyncDoiSection zenodoOutputDir={outputDirs.zenodo ?? ''} />}
              {publishOrder.includes('b2share') && <SyncPidSection b2shareOutputDir={outputDirs.b2share ?? ''} />}
              {/* Unlike Zenodo/B2SHARE, GBIF doesn't always have a DOI to
                  sync — most organizations don't get one automatically (see
                  gbif.register_gbif_dataset) — so this only shows up when
                  this run's registration actually came back with one. When
                  Hugging Face Hub published in the same run, the backend
                  already synced it automatically (see publish_orchestrator's
                  own post-lock step) — this then just confirms it happened
                  instead of asking again for directory/repo/token already
                  known from this same run. */}
              {publishOrder.includes('gbif') && progress.gbif?.doi && (
                <GBIFSyncDoiSection
                  gbifOutputDir={outputDirs.gbif ?? ''}
                  alreadySyncedRepoUrl={progress.gbif.doiSyncedToHfh ? progress.hfh?.repoUrl : null}
                />
              )}
            </>
          )}

          <button
            type="button"
            className="w-full mt-8 px-6 py-4 text-base font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            onClick={handlePublishAgain}
          >
            Publish again
          </button>
        </div>
      )}

      {/* Navigation */}
      {step > 0 && !(step === 4 && publishStarted) && (
        <div className="flex justify-between items-start mt-10">
          <button type="button" className={btnOutline} onClick={() => setStep((s) => s - 1)}>
            Back
          </button>

          {step === 1 && (
            <div className="flex flex-col items-end gap-2">
              <button
                type="button"
                className={btnPrimary}
                disabled={!canProceed || isDownloading}
                onClick={handleNext}
              >
                {isDownloading && <SmallSpinner />}
                {isDownloading ? 'Downloading…' : 'Next'}
              </button>
              {download.status === 'error' && (
                <p className="text-sm text-red-600 dark:text-red-400 text-right">{download.error}</p>
              )}
            </div>
          )}

          {step === 2 && download.status === 'done' && (
            <button
              type="button"
              className={btnPrimary}
              onClick={handleContinueToPreprocessing}
              disabled={preprocessing || (productType === 'camtrapdp' && (!dpNameValid || !dpVersionValid))}
            >
              {preprocessing && <SmallSpinner />}
              {preprocessing ? 'Processing…' : 'Continue'}
            </button>
          )}

          {step === 3 && download.status === 'done' && (
            <button type="button" className={btnPrimary} disabled={!metadataComplete} onClick={() => setStep(4)}>
              Next
            </button>
          )}

          {step === 4 && !publishStarted && selectedRepos.size > 0 && (
            <button type="button" className={btnPrimary} onClick={startConfiguring}>
              Start publishing{dryRun ? ' (dry run)' : ''}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
