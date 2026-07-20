import { useEffect, useState } from 'react'
import { api } from '../api'
import type { OutputMode } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnOutline = 'px-4 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50 flex items-center gap-2'
const btnPrimary = 'px-6 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2'
const successPanel = 'flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 text-sm'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

function PrimarySpinner() {
  return <div className="w-4 h-4 border border-white/60 border-t-white rounded-full animate-spin" />
}

function CheckIcon() {
  return (
    <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  )
}

/** Everything ZenodoPublishForm collects — handed to the wizard via
 * onConfigured, and later replayed by the wizard's own execution runner
 * (see WizardPage's runPublishSequence) to actually call
 * api.zenodoStartPublish once every selected repository has been
 * configured. hfhRepoId is deliberately NOT part of this: in link mode it's
 * only known once the previous repository in the publish order has
 * actually published, so the wizard resolves it live, right before this
 * repo's turn to publish — see WizardPage. */
export interface ZenodoPublishConfig {
  token: string
  environment: string
  communities: string
  mirrorImages: boolean
  outputMode: OutputMode
  outputDir: string
}

interface Props {
  /** Reports this form's current output directory whenever it changes, so a
   * later step in the publish order can use it as its own inputDir. */
  onOutputDirChange?: (dir: string) => void
  /** Called once the user confirms this repository's configuration is
   * complete — the wizard collects one of these per selected repository
   * before actually publishing anything (see WizardPage). */
  onConfigured: (config: ZenodoPublishConfig) => void
}

type TestStatus = 'idle' | 'testing' | 'ok' | 'error'

export default function ZenodoPublishForm({ onOutputDirChange, onConfigured }: Props) {
  const [form, setForm] = useState({
    outputDir: '', token: '', environment: 'sandbox', communities: '',
  })
  const [mirrorImages, setMirrorImages] = useState(true)
  const [outputMode, setOutputMode] = useState<OutputMode>('prepared')
  const [hasSavedToken, setHasSavedToken] = useState(false)

  const [test, setTest] = useState<{ status: TestStatus; message: string }>({ status: 'idle', message: '' })

  const zenodoTokenUrl = `https://${form.environment === 'sandbox' ? 'sandbox.zenodo.org' : 'zenodo.org'}/account/settings/applications/tokens/new/`

  // Prefill from settings.toml — the same file 'zenodo config' reads/writes
  // on the CLI. The token itself is never sent to the frontend; leaving it
  // blank later reuses whatever is already saved.
  useEffect(() => {
    api.zenodoGetConfig()
      .then((config) => {
        setForm((f) => ({
          ...f,
          outputDir: config.output_dir,
          environment: config.environment,
          communities: config.communities ?? f.communities,
        }))
        setHasSavedToken(config.has_token)
      })
      .catch(() => {})
  }, [])

  // Deliberately depends only on form.outputDir, not onOutputDirChange: the
  // parent passes a fresh inline function on every render, so including it
  // here would refire this effect (and the parent setState it triggers) on
  // every render, looping forever.
  useEffect(() => {
    onOutputDirChange?.(form.outputDir)
  }, [form.outputDir])

  function setField(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
    if (key === 'token') setTest({ status: 'idle', message: '' })
  }

  const canTest = form.token !== '' || hasSavedToken
  const isTesting = test.status === 'testing'
  const canContinue = form.outputDir !== '' && (form.token !== '' || hasSavedToken)

  async function handleTestToken() {
    setTest({ status: 'testing', message: '' })
    try {
      await api.zenodoTestToken(form.token, form.environment)
      setHasSavedToken(true) // the backend saves environment/token on a successful test
      setTest({ status: 'ok', message: 'Token verified.' })
    } catch (e) {
      setTest({ status: 'error', message: e instanceof Error ? e.message : 'Could not verify the token.' })
    }
  }

  function handleContinue() {
    onConfigured({
      token: form.token, environment: form.environment, communities: form.communities,
      mirrorImages, outputMode, outputDir: form.outputDir,
    })
  }

  return (
    <div>
      {!mirrorImages && (
        <p className={hintClass + ' mb-4'}>
          The linked Hugging Face Hub repository will be detected automatically once the previous
          repository in the publish order has published — nothing to fill in here.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className={labelClass} htmlFor="zenodo-environment">Environment</label>
          <select
            id="zenodo-environment"
            className={inputClass}
            value={form.environment}
            onChange={(e) => setField('environment', e.target.value)}
          >
            <option value="sandbox">Sandbox (testing, no real DOI)</option>
            <option value="production">Production</option>
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="zenodo-communities">Communities</label>
          <input
            id="zenodo-communities"
            className={inputClass}
            placeholder="comma-separated"
            value={form.communities}
            onChange={(e) => setField('communities', e.target.value)}
          />
        </div>
      </div>

      <div className="mb-6">
        <label className={labelClass} htmlFor="zenodo-token">Zenodo token</label>
        <input
          id="zenodo-token"
          type="password"
          className={inputClass}
          placeholder="••••••••"
          value={form.token}
          onChange={(e) => setField('token', e.target.value)}
          autoComplete="current-password"
        />
        {hasSavedToken && form.token === '' && (
          <p className={hintClass}>Already saved — leave blank to reuse it.</p>
        )}
        <p className={hintClass}>
          Get one at{' '}
          <a href={zenodoTokenUrl} target="_blank" rel="noreferrer" className="underline">
            {zenodoTokenUrl.replace('https://', '')}
          </a>
        </p>

        <div className="flex justify-end mt-2">
          <button type="button" className={btnOutline} disabled={!canTest || isTesting} onClick={handleTestToken}>
            {isTesting && <SmallSpinner />}
            {isTesting ? 'Testing…' : 'Test token'}
          </button>
        </div>
        {test.status === 'ok' && (
          <p className="text-sm text-emerald-600 dark:text-emerald-400 text-right mt-2">{test.message}</p>
        )}
        {test.status === 'error' && (
          <p className="text-sm text-red-600 dark:text-red-400 text-right mt-2">{test.message}</p>
        )}
      </div>

      <div className="mb-4">
        <span className={labelClass}>Mode</span>
        <p className={hintClass + ' mb-2'}>What gets copied to the repository.</p>
        <div className="flex flex-col gap-2">
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="zenodo-mode"
              className="mt-0.5"
              checked={mirrorImages}
              onChange={() => setMirrorImages(true)}
            />
            <span><strong>Mirror</strong> - makes a self-contained copy of the product: downloads the
              public images and bundles them inside Zenodo's own camtrapdp.zip.</span>
          </label>
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="zenodo-mode"
              className="mt-0.5"
              checked={!mirrorImages}
              onChange={() => setMirrorImages(false)}
            />
            <span><strong>Link</strong> - the repository stores links to where the product's items
              (the images) already live on Hugging Face Hub, instead of a copy.</span>
          </label>
        </div>
      </div>

      <div className="mb-4">
        <span className={labelClass}>Flow mode</span>
        <p className={hintClass + ' mb-2'}>What you'll get back once publishing finishes.</p>
        <div className="flex flex-col gap-2">
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="zenodo-output-mode"
              className="mt-0.5"
              checked={outputMode === 'prepared'}
              onChange={() => setOutputMode('prepared')}
            />
            <span><strong>Prepared package</strong> - just the Camtrap DP files (datapackage.json,
              deployments.csv, media.csv, observations.csv) with the changes made while preparing
              and uploading, plus the Zenodo record data (needed to sync the DOI here later) — no
              README, LICENSE, CITATION.cff, checksums, images or zip.</span>
          </label>
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="zenodo-output-mode"
              className="mt-0.5"
              checked={outputMode === 'passthrough'}
              onChange={() => setOutputMode('passthrough')}
            />
            <span><strong>Same as input</strong> - exactly what came in as input, unchanged.</span>
          </label>
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="zenodo-output-mode"
              className="mt-0.5"
              checked={outputMode === 'downloaded'}
              onChange={() => setOutputMode('downloaded')}
            />
            <span><strong>Downloaded from repository</strong> - re-download the files from Zenodo
              after publishing.</span>
          </label>
        </div>
      </div>

      <div className="flex justify-end">
        <button type="button" className={btnPrimary} disabled={!canContinue} onClick={handleContinue}>
          Continue
        </button>
      </div>
    </div>
  )
}

type SyncStatus = 'idle' | 'running' | 'done' | 'error'

/** Rendered by the wizard's final "All done!" screen for any Zenodo
 * repository that actually published in this run (see WizardPage) —
 * reflects the just-obtained DOI into an already-published HFH export's
 * CITATION.cff. Self-contained: only needs the Zenodo output directory,
 * everything else (HFH export dir/username/token) is read from settings.toml
 * or typed in here. */
export function SyncDoiSection({ zenodoOutputDir }: { zenodoOutputDir: string }) {
  const [hfhOutputDir, setHfhOutputDir] = useState('')
  const [hfUser, setHfUser] = useState('')
  const [repoName, setRepoName] = useState('')
  const [token, setToken] = useState('')
  const [hasSavedToken, setHasSavedToken] = useState(false)
  const [sync, setSync] = useState<{ status: SyncStatus; repoUrl: string | null; error: string | null }>(
    { status: 'idle', repoUrl: null, error: null },
  )

  const hfhRepoId = hfUser && repoName ? `${hfUser}/${repoName}` : ''

  useEffect(() => {
    api.hfhGetConfig()
      .then((config) => {
        setHfhOutputDir(config.output_dir)
        setHfUser(config.username || '')
        setHasSavedToken(config.has_token)
      })
      .catch(() => {})
  }, [])

  const canSync = hfhOutputDir !== '' && hfhRepoId !== '' && (token !== '' || hasSavedToken) && sync.status !== 'running'

  async function handleSync() {
    setSync({ status: 'running', repoUrl: null, error: null })
    try {
      const result = await api.zenodoSyncDoi({ zenodoOutputDir, hfhOutputDir, hfhRepoId, hfhToken: token })
      setSync({ status: 'done', repoUrl: result.repo_url, error: null })
    } catch (e) {
      setSync({ status: 'error', repoUrl: null, error: e instanceof Error ? e.message : 'Could not sync the DOI.' })
    }
  }

  if (sync.status === 'done') {
    return (
      <div className={successPanel + ' mt-6'}>
        <CheckIcon />
        <span>
          DOI synced to{' '}
          <a href={sync.repoUrl ?? ''} target="_blank" rel="noreferrer" className="underline font-mono">
            {sync.repoUrl}
          </a>
        </span>
      </div>
    )
  }

  return (
    <div className="mt-8">
      <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />
      <h5 className="text-base font-semibold mb-1 text-zinc-700 dark:text-zinc-300">Sync DOI to Hugging Face Hub</h5>
      <p className={hintClass + ' mb-4'}>
        Reflects the Zenodo DOI in the CITATION.cff of an already-published Hugging Face Hub dataset.
      </p>

      <div className="mb-4">
        <span className={labelClass}>Hugging Face Hub export directory</span>
        <p className="text-sm font-mono text-zinc-600 dark:text-zinc-400 break-all">{hfhOutputDir}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className={labelClass} htmlFor="sync-hfh-user">User or organization</label>
          <input
            id="sync-hfh-user"
            className={inputClass}
            placeholder="user_or_org"
            value={hfUser}
            onChange={(e) => setHfUser(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="sync-hfh-repo-name">Repository name</label>
          <input
            id="sync-hfh-repo-name"
            className={inputClass}
            placeholder="dataset"
            value={repoName}
            onChange={(e) => setRepoName(e.target.value)}
          />
        </div>
      </div>

      <div className="mb-4">
        <label className={labelClass} htmlFor="sync-hfh-token">HuggingFace Hub token</label>
        <input
          id="sync-hfh-token"
          type="password"
          className={inputClass}
          placeholder="••••••••"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoComplete="current-password"
        />
        {hasSavedToken && token === '' && (
          <p className={hintClass}>Already saved — leave blank to reuse it.</p>
        )}
        <p className={hintClass}>
          Get one at{' '}
          <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer" className="underline">
            huggingface.co/settings/tokens
          </a>{' '}
          (write permission).
        </p>
      </div>

      <div className="flex justify-end">
        <button type="button" className={btnPrimary} disabled={!canSync} onClick={handleSync}>
          {sync.status === 'running' && <PrimarySpinner />}
          {sync.status === 'running' ? 'Syncing…' : 'Sync DOI'}
        </button>
      </div>
      {sync.status === 'error' && (
        <p className="text-sm text-red-600 dark:text-red-400 text-right mt-2">{sync.error}</p>
      )}
    </div>
  )
}
