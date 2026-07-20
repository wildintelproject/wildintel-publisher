import { useEffect, useState } from 'react'
import B2SharePublishForm, { SyncPidSection } from '../components/B2SharePublishForm'
import type { B2SharePublishConfig } from '../components/B2SharePublishForm'
import CompleteMetadataForm from '../components/CompleteMetadataForm'
import GBIFPublishForm from '../components/GBIFPublishForm'
import type { GBIFPublishConfig } from '../components/GBIFPublishForm'
import HFHPublishForm from '../components/HFHPublishForm'
import type { HfhPublishConfig } from '../components/HFHPublishForm'
import LocalDirectoryForm from '../components/LocalDirectoryForm'
import TrapperConnectionForm from '../components/TrapperConnectionForm'
import ZenodoPublishForm, { SyncDoiSection } from '../components/ZenodoPublishForm'
import type { ZenodoPublishConfig } from '../components/ZenodoPublishForm'
import { api } from '../api'
import { missingRequiredFields } from '../types'
import type { DatapackageSummary, TrapperDownloadSelection } from '../types'

const STEP_LABELS = ['Product Type', 'Source', 'Download', 'Publish']

type ProductType = 'camtrapdp' | 'yolo' | 'ai_model' | 'ebv' | 'image_gallery'

interface ProductOption {
  value: ProductType
  emoji: string
  title: string
  description: string
  available: boolean
}

const PRODUCT_OPTIONS: ProductOption[] = [
  { value: 'camtrapdp', emoji: '📦', title: 'Camtrap DP', description: 'A camera-trap data package fetched from Trapper.', available: true },
  { value: 'yolo', emoji: '🗂️', title: 'YOLO Dataset', description: 'An image dataset in YOLO training format (images/train, val, test + data.yaml).', available: true },
  { value: 'ai_model', emoji: '🤖', title: 'AI Model', description: 'A trained AI model artifact.', available: false },
  { value: 'ebv', emoji: '🌍', title: 'EBV', description: 'Essential Biodiversity Variables derived from the project data.', available: false },
  { value: 'image_gallery', emoji: '🖼️', title: 'Image Gallery', description: 'A curated gallery of camera-trap images.', available: false },
]

type SourceType = 'local' | 'trapper'

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
  ],
  yolo: [
    { value: 'local', emoji: '📁', title: 'Local Directory', description: 'Use a YOLO dataset already available on this machine.', available: true },
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
// aren't a fit (see docs/publishing-gbif.md). The other product types aren't
// selectable yet, so they have no supported repositories of their own for now.
const REPOS_BY_PRODUCT_TYPE: Record<ProductType, RepoId[]> = {
  camtrapdp: ['hfh', 'zenodo', 'b2share', 'gbif'],
  yolo: ['hfh', 'zenodo', 'b2share'],
  ai_model: [],
  ebv: [],
  image_gallery: [],
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
}

const IDLE_PROGRESS: RepoProgress = { status: 'pending', stage: '', error: null, repoUrl: null, doi: null, pid: null }

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
  const [localPath, setLocalPath] = useState<string | null>(null)
  const [download, setDownload] = useState<DownloadState>({ status: 'idle', path: null, error: null })
  const [summary, setSummary] = useState<DatapackageSummary | null>(null)
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

  const canProceed = (sourceType === 'trapper' && trapperSelection !== null) || (sourceType === 'local' && localPath !== null)
  const isDownloading = download.status === 'running'
  const supportedRepos = productType ? REPOS_BY_PRODUCT_TYPE[productType] : []
  const sourceOptions = productType ? SOURCE_OPTIONS_BY_PRODUCT_TYPE[productType] : []
  const metadataComplete = summary !== null && missingRequiredFields(summary).length === 0
  const allConfigured = publishStarted && configureIndex >= publishOrder.length
  const needsPrimaryDoiChoice = publishOrder.includes('hfh') && publishOrder.includes('zenodo') && publishOrder.includes('b2share')
  const readyToConfirm = allConfigured && (!needsPrimaryDoiChoice || primaryDoiSource !== null)

  function toggleRepo(repo: RepoId) {
    setSelectedRepos((prev) => {
      const next = new Set(prev)
      if (next.has(repo)) next.delete(repo)
      else next.add(repo)
      return next
    })
    setPublishOrder((prev) => (prev.includes(repo) ? prev.filter((r) => r !== repo) : [...prev, repo]))
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
    setLocalPath(null)
    setDownload({ status: 'idle', path: null, error: null })
    setSummary(null)
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
      }
    }
    if (repo === 'b2share') {
      const cfg = repoConfigs.b2share!
      return {
        repo: 'b2share' as const, outputDir: cfg.outputDir, token: cfg.token,
        mirrorImages: cfg.mirrorImages, outputMode: cfg.outputMode, environment: cfg.environment, communityId: cfg.communityId,
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

  // Publishes every selected repository in one backend call: upload phase
  // for all of them, then a cross-repo DOI populate pass, then release/
  // lock for all of them (see services.publish_orchestrator) — polls a
  // single task_id for a per-repo progress dict, no client-side
  // sequencing anymore.
  async function runPublishSequence() {
    setExecuting(true)
    setExecutionError(null)
    setProgress(Object.fromEntries(publishOrder.map((repo) => [repo, IDLE_PROGRESS])))
    try {
      const { task_id } = await api.publishAllStart({
        inputDir: download.path ?? '',
        version: summary?.version,
        timeout: IMAGE_TIMEOUT,
        repos: publishOrder.map(buildRepoPayload),
        primaryDoiSource: primaryDoiSource ?? undefined,
        dryRun,
      })

      while (true) {
        await sleep(2000)
        const status = await api.publishAllStatus(task_id)
        setProgress((p) => {
          const next = { ...p }
          for (const repo of publishOrder) {
            const r = status.repos[repo]
            if (!r) continue
            next[repo] = {
              status: r.status, stage: r.stage, error: r.error,
              repoUrl: r.repo_url, doi: r.doi, pid: r.pid,
            }
          }
          return next
        })
        if (status.status === 'done') {
          setOutputDirs((o) => {
            const next = { ...o }
            for (const repo of publishOrder) {
              const outputDir = status.repos[repo]?.output_dir
              if (outputDir) next[repo] = outputDir
            }
            return next
          })
          setExecutionDone(true)
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

  useEffect(() => {
    if (download.status !== 'done' || !download.path || !productType) return
    setSummary(null)
    // Idempotent: (re)writes metadata.json from the product's own files, so
    // this works whether or not LocalDirectoryForm already generated it.
    api.generateProductMetadata(download.path, productType).then(setSummary).catch(() => setSummary(null))
  }, [download.status, download.path, productType])

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
      if (!localPath) return
      setDownload({ status: 'done', path: localPath, error: null })
      setStep(2)
      return
    }
    if (!trapperSelection) return
    setDownload({ status: 'running', path: null, error: null })
    try {
      const { task_id } = await api.trapperStartDownload(
        trapperSelection.url, trapperSelection.username, trapperSelection.password,
        trapperSelection.projectId, trapperSelection.deploymentId,
      )
      // Poll until the background task finishes
      while (true) {
        await sleep(2000)
        const status = await api.trapperDownloadStatus(task_id)
        if (status.status === 'done') {
          setDownload({ status: 'done', path: status.path, error: null })
          setStep(2)
          break
        }
        if (status.status === 'error') {
          setDownload({ status: 'error', path: null, error: status.error ?? 'The download failed.' })
          break
        }
      }
    } catch (e) {
      setDownload({ status: 'error', path: null, error: e instanceof Error ? e.message : 'Could not start the download.' })
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
                onClick={() => { setProductType(option.value); setStep(1) }}
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

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
              <LocalDirectoryForm productType={productType} onSelectionChange={setLocalPath} />
            </div>
          )}
        </div>
      )}

      {/* ── Step 2: download result ── */}
      {step === 2 && download.status === 'done' && (
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
            </div>
          )}
        </div>
      )}

      {/* ── Step 3: repository selection ── */}
      {step === 3 && !publishStarted && (
        <div>
          <h4 className="text-lg font-semibold mb-1">Where do you want to publish it?</h4>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
            Choose one or more repositories to publish the package to.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {REPO_OPTIONS.map((option) => {
              const available = option.implemented && supportedRepos.includes(option.value)
              const selected = selectedRepos.has(option.value)
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={!available}
                  onClick={() => toggleRepo(option.value)}
                  className={[
                    'relative flex flex-col items-center gap-3 p-6 rounded-xl border-2 text-center transition-colors',
                    !available
                      ? 'border-zinc-200 dark:border-zinc-800 opacity-50 cursor-not-allowed'
                      : selected
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 cursor-pointer'
                      : 'border-zinc-300 dark:border-zinc-700 hover:border-blue-500 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950/30 cursor-pointer',
                  ].join(' ')}
                >
                  {!option.implemented && (
                    <span className="absolute top-2 right-2 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700 text-zinc-500 dark:text-zinc-400">
                      Coming soon
                    </span>
                  )}
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

          {publishOrder.length > 1 && (
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

          {selectedRepos.size > 0 && (
            <div className="flex justify-end mt-8">
              <button type="button" className={btnPrimary} onClick={startConfiguring}>
                Start publishing{dryRun ? ' (dry run)' : ''}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Step 3 (continued): collecting configuration, one repository at a time ── */}
      {step === 3 && publishStarted && !allConfigured && !executing && !executionDone && (
        <div>
          <div className="flex items-center gap-4 mb-6 flex-wrap">
            {publishOrder.map((repoId, i) => {
              const option = REPO_OPTIONS.find((o) => o.value === repoId)
              if (!option) return null
              return (
                <div
                  key={repoId}
                  className={`flex items-center gap-1.5 text-sm ${
                    i === configureIndex
                      ? 'text-zinc-900 dark:text-zinc-100 font-semibold'
                      : i < configureIndex
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-zinc-400 dark:text-zinc-600'
                  }`}
                >
                  <span>{i < configureIndex ? '✓' : `${i + 1}.`}</span> {option.emoji} {option.title}
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
              onConfigured={(config) => handleConfigured('hfh', config)}
            />
          )}
          {publishOrder[configureIndex] === 'zenodo' && (
            <ZenodoPublishForm
              dryRun={dryRun}
              onOutputDirChange={(dir) => setOutputDirs((o) => ({ ...o, zenodo: dir }))}
              onConfigured={(config) => handleConfigured('zenodo', config)}
            />
          )}
          {publishOrder[configureIndex] === 'b2share' && (
            <B2SharePublishForm
              dryRun={dryRun}
              onOutputDirChange={(dir) => setOutputDirs((o) => ({ ...o, b2share: dir }))}
              onConfigured={(config) => handleConfigured('b2share', config)}
            />
          )}
          {publishOrder[configureIndex] === 'gbif' && (
            <GBIFPublishForm
              dryRun={dryRun}
              suggestedArchiveUrl={
                repoConfigs.hfh?.repoId
                  ? `https://huggingface.co/datasets/${repoConfigs.hfh.repoId}/resolve/main/datapackage.json`
                  : undefined
              }
              onConfigured={(config) => handleConfigured('gbif', config)}
            />
          )}
        </div>
      )}

      {/* ── Step 3 (continued): hfh + zenodo + b2share all selected — choose which DOI is primary for HFH ── */}
      {step === 3 && allConfigured && needsPrimaryDoiChoice && primaryDoiSource === null && !executing && !executionDone && (
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

      {/* ── Step 3 (continued): all configured — confirm before publishing ── */}
      {step === 3 && readyToConfirm && !executing && !executionDone && (
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

      {/* ── Step 3 (continued): live progress while publishing runs automatically ── */}
      {step === 3 && executing && !executionDone && (
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
                <li key={repoId} className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 text-sm">
                  <span>{option.emoji}</span>
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">{option.title}</span>
                  <span className="flex-1" />
                  {repoProgress.status === 'pending' && <span className="text-zinc-400 dark:text-zinc-600">Waiting…</span>}
                  {repoProgress.status === 'running' && (
                    <span className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
                      <SmallSpinner /> {STAGE_LABELS[repoProgress.stage] ?? 'Publishing…'}
                    </span>
                  )}
                  {repoProgress.status === 'done' && <span className="text-emerald-600 dark:text-emerald-400">✓ Done</span>}
                  {repoProgress.status === 'error' && <span className="text-red-600 dark:text-red-400">✘ {repoProgress.error}</span>}
                </li>
              )
            })}
          </ul>
          {executionError && (
            <div className="mt-6">
              <p className="text-sm text-red-600 dark:text-red-400 mb-3">{executionError}</p>
              <div className="flex justify-end">
                <button type="button" className={btnOutline} onClick={() => setExecuting(false)}>
                  Back
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 3 (continued): all repositories published ── */}
      {step === 3 && executionDone && (
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

          {dryRun ? (
            <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
              DOI/PID sync isn't available for a dry run (it would perform a real Hugging Face Hub
              upload) — the DOI cross-referencing already ran, simulated, as part of this dry run.
            </p>
          ) : (
            <>
              {publishOrder.includes('zenodo') && <SyncDoiSection zenodoOutputDir={outputDirs.zenodo ?? ''} />}
              {publishOrder.includes('b2share') && <SyncPidSection b2shareOutputDir={outputDirs.b2share ?? ''} />}
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
      {step > 0 && !(step === 3 && publishStarted) && (
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
            <button type="button" className={btnPrimary} disabled={!metadataComplete} onClick={() => setStep(3)}>
              Next
            </button>
          )}
        </div>
      )}
    </div>
  )
}
