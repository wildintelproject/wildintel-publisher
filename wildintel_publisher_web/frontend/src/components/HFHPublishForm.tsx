import { useEffect, useState } from 'react'
import { api } from '../api'
import type { OutputMode } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnOutline = 'px-4 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50 flex items-center gap-2'
const btnPrimary = 'px-6 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

/** Everything HFHPublishForm collects — handed to the wizard via
 * onConfigured, and later replayed by the wizard's own execution runner
 * (see WizardPage's runPublishSequence) to actually call
 * api.hfhStartPublish once every selected repository has been configured. */
export interface HfhPublishConfig {
  repoId: string
  token: string
  priv: boolean
  mirrorImages: boolean
  outputMode: OutputMode
  outputDir: string
}

interface Props {
  /** metadata.json's title (see product.missing_required_fields), used to
   * prefill the repository name field — slugified (lowercased, spaces
   * stripped) since it's what's read as-is from the product. */
  productTitle?: string
  /** metadata.json's version — sent along with "Test token" so the backend
   * can warn if it was already published to this repo (a tag with that
   * name would already exist; see services.hfh_service.test_token). Actual
   * publishing enforces this for real regardless (hfh.upload_to_huggingface's
   * own check) — this is just an early heads-up. */
  productVersion?: string
  /** Reports this form's current output directory whenever it changes, so a
   * later step in the publish order can use it as its own inputDir. */
  onOutputDirChange?: (dir: string) => void
  /** Called once the user confirms this repository's configuration is
   * complete — the wizard collects one of these per selected repository
   * before actually publishing anything (see WizardPage). */
  onConfigured: (config: HfhPublishConfig) => void
}

type TestStatus = 'idle' | 'testing' | 'ok' | 'warning' | 'error'

function slugifyRepoName(title: string): string {
  return title.toLowerCase().replace(/\s+/g, '')
}

export default function HFHPublishForm({ productTitle, productVersion, onOutputDirChange, onConfigured }: Props) {
  const [form, setForm] = useState({ outputDir: '', hfUser: '', repoName: '', token: '' })
  const [mirrorImages, setMirrorImages] = useState(true)
  const [outputMode, setOutputMode] = useState<OutputMode>('prepared')
  const [priv, setPriv] = useState(true)
  const [hasSavedToken, setHasSavedToken] = useState(false)

  const [test, setTest] = useState<{ status: TestStatus; message: string }>({ status: 'idle', message: '' })

  const repoId = form.hfUser && form.repoName ? `${form.hfUser}/${form.repoName}` : ''

  // Prefill the username/org from settings.toml — the same file 'hfh
  // config' reads/writes on the CLI. Only the username is remembered
  // across products (see services.hfh_service.save_config): the dataset
  // name itself comes from the product's own title (see the effect below),
  // not from whatever was last used. The token itself is never sent to the
  // frontend; leaving the token field blank later reuses whatever is
  // already saved.
  useEffect(() => {
    api.hfhGetConfig()
      .then((config) => {
        setForm((f) => ({
          ...f,
          outputDir: config.output_dir,
          hfUser: config.username || f.hfUser,
        }))
        setHasSavedToken(config.has_token)
      })
      .catch(() => {})
  }, [])

  // Prefill the repository name from the product's own title — only if the
  // user hasn't already typed something in that field.
  useEffect(() => {
    if (!productTitle) return
    setForm((f) => (f.repoName ? f : { ...f, repoName: slugifyRepoName(productTitle) }))
  }, [productTitle])

  // Deliberately depends only on form.outputDir, not onOutputDirChange: the
  // parent passes a fresh inline function on every render, so including it
  // here would refire this effect (and the parent setState it triggers) on
  // every render, looping forever.
  useEffect(() => {
    onOutputDirChange?.(form.outputDir)
  }, [form.outputDir])

  function setField(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
    if (key === 'token' || key === 'hfUser' || key === 'repoName') setTest({ status: 'idle', message: '' })
  }

  const canTest = repoId !== '' && (form.token !== '' || hasSavedToken)
  const isTesting = test.status === 'testing'
  const canContinue = repoId !== '' && form.outputDir !== '' && (form.token !== '' || hasSavedToken)

  async function handleTestToken() {
    setTest({ status: 'testing', message: '' })
    try {
      const result = await api.hfhTestToken(repoId, form.token, productVersion)
      setHasSavedToken(true) // the backend saves repo_id/token on a successful test
      if (result.version_conflict) {
        setTest({
          status: 'warning',
          message: `Connected as ${result.username}. Version ${productVersion} has already been published to `
            + `${repoId} — bump metadata.json's version before publishing again.`,
        })
      } else {
        setTest({ status: 'ok', message: `Connected as ${result.username}.` })
      }
    } catch (e) {
      setTest({ status: 'error', message: e instanceof Error ? e.message : 'Could not verify the token.' })
    }
  }

  function handleContinue() {
    onConfigured({ repoId, token: form.token, priv, mirrorImages, outputMode, outputDir: form.outputDir })
  }

  return (
    <div>
      <div className="grid grid-cols-2 gap-4 mb-1.5">
        <div>
          <label className={labelClass} htmlFor="hfh-user">User or organization</label>
          <input
            id="hfh-user"
            className={inputClass}
            placeholder="user_or_org"
            value={form.hfUser}
            onChange={(e) => setField('hfUser', e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="hfh-repo-name">Repository name</label>
          <input
            id="hfh-repo-name"
            className={inputClass}
            placeholder="dataset"
            value={form.repoName}
            onChange={(e) => setField('repoName', e.target.value)}
          />
        </div>
      </div>
      <p className={hintClass + ' mb-4'}>
        {repoId ? <>The repository identifier will be: <span className="font-mono">{repoId}</span></> : ' '}
      </p>

      <div className="flex items-center gap-6 mb-4">
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input type="checkbox" checked={priv} onChange={(e) => setPriv(e.target.checked)} />
          Create as private
        </label>
      </div>

      <div className="mb-6">
        <label className={labelClass} htmlFor="hfh-token">HuggingFace Hub token</label>
        <input
          id="hfh-token"
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
          <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer" className="underline">
            huggingface.co/settings/tokens
          </a>{' '}
          (write permission).
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
        {test.status === 'warning' && (
          <p className="text-sm text-amber-600 dark:text-amber-400 text-right mt-2">⚠ {test.message}</p>
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
              name="hfh-mode"
              className="mt-0.5"
              checked={mirrorImages}
              onChange={() => setMirrorImages(true)}
            />
            <span><strong>Mirror</strong> - makes a self-contained copy of the product: downloads the
              images and re-uploads them to Hugging Face Hub, rewriting media.csv to point to them.</span>
          </label>
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="hfh-mode"
              className="mt-0.5"
              checked={!mirrorImages}
              onChange={() => setMirrorImages(false)}
            />
            <span><strong>Link</strong> - the repository stores links to where the product's items
              (the images) already live, instead of a copy; media.csv keeps pointing at the original
              file locations.</span>
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
              name="hfh-output-mode"
              className="mt-0.5"
              checked={outputMode === 'prepared'}
              onChange={() => setOutputMode('prepared')}
            />
            <span><strong>Prepared package</strong> - just the Camtrap DP files (datapackage.json,
              deployments.csv, media.csv, observations.csv) with the changes made while preparing
              and uploading, plus CITATION.cff/checksums (needed to sync a DOI/PID here later) — no
              README, LICENSE, images or the local zip.</span>
          </label>
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="hfh-output-mode"
              className="mt-0.5"
              checked={outputMode === 'passthrough'}
              onChange={() => setOutputMode('passthrough')}
            />
            <span><strong>Same as input</strong> - exactly what came in as input, unchanged.</span>
          </label>
          <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="radio"
              name="hfh-output-mode"
              className="mt-0.5"
              checked={outputMode === 'downloaded'}
              onChange={() => setOutputMode('downloaded')}
            />
            <span><strong>Downloaded from repository</strong> - re-download the files from Hugging Face
              Hub after publishing.</span>
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
