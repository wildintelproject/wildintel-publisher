import { useEffect, useState } from 'react'
import { api } from '../api'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnOutline = 'px-4 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50 flex items-center gap-2'
const btnPrimary = 'px-6 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

/** Everything GBIFPublishForm collects — handed to the wizard via
 * onConfigured, and later replayed by the wizard's own execution runner
 * (see WizardPage's runPublishSequence) to actually publish once every
 * selected repository has been configured.
 *
 * Unlike HFH/Zenodo/B2SHARE, there's no mirrorImages/outputMode choice here:
 * GBIF never hosts a copy of the package, so there's nothing to mirror and
 * nothing to download back — see services.publish_orchestrator (backend)
 * for how repo == "gbif" is handled differently throughout. */
export interface GBIFPublishConfig {
  archiveUrl: string
  environment: string
  publishingOrganizationKey: string
  installationKey: string
  registryLanguage: string
  username: string
  password: string
  outputDir: string
}

interface Props {
  /** No credentials/keys are required, and "Test credentials" is pointless,
   * when the whole publish is a simulation (see WizardPage's dryRun) —
   * nothing is ever actually registered with GBIF's Registry; a plausible
   * dataset URL is faked instead (see services.publish_orchestrator's
   * dry-run branch). */
  dryRun?: boolean
  /** Prefills the archive URL once, if given — the wizard derives this from
   * an earlier Hugging Face Hub step's repo_id in the same publish order
   * (see WizardPage), since that URL is fully deterministic ahead of time.
   * Always editable, and never overwrites what the user already typed. */
  suggestedArchiveUrl?: string
  /** Called once the user confirms this repository's configuration is
   * complete — the wizard collects one of these per selected repository
   * before actually publishing anything (see WizardPage). */
  onConfigured: (config: GBIFPublishConfig) => void
}

type TestStatus = 'idle' | 'testing' | 'ok' | 'error'

export default function GBIFPublishForm({ dryRun, suggestedArchiveUrl, onConfigured }: Props) {
  const [form, setForm] = useState({
    outputDir: '', archiveUrl: '', environment: 'sandbox',
    publishingOrganizationKey: '', installationKey: '', registryLanguage: 'eng',
    username: '', password: '',
  })
  const [hasSavedCredentials, setHasSavedCredentials] = useState(false)
  const [test, setTest] = useState<{ status: TestStatus; message: string }>({ status: 'idle', message: '' })

  // Prefill from settings.toml — the same file 'gbif config' reads/writes on
  // the CLI. The credentials themselves are never sent to the frontend;
  // leaving them blank later reuses whatever is already saved.
  useEffect(() => {
    api.gbifGetConfig()
      .then((config) => {
        setForm((f) => ({
          ...f,
          outputDir: config.output_dir,
          environment: config.environment,
          publishingOrganizationKey: config.publishing_organization_key ?? f.publishingOrganizationKey,
          installationKey: config.installation_key ?? f.installationKey,
          registryLanguage: config.registry_language ?? f.registryLanguage,
        }))
        setHasSavedCredentials(config.has_credentials)
      })
      .catch(() => {})
  }, [])

  // Only fills archiveUrl the first time a suggestion becomes available
  // (form.archiveUrl still blank) — never overwrites something the user
  // already typed themselves.
  useEffect(() => {
    if (suggestedArchiveUrl && form.archiveUrl === '') {
      setForm((f) => ({ ...f, archiveUrl: suggestedArchiveUrl }))
    }
    // Deliberately depends only on suggestedArchiveUrl: including
    // form.archiveUrl here would refire this every time the user types.
  }, [suggestedArchiveUrl])

  function setField(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
    if (key === 'username' || key === 'password') setTest({ status: 'idle', message: '' })
  }

  const hasTypedCredentials = form.username !== '' && form.password !== ''
  const canTest = hasTypedCredentials || hasSavedCredentials
  const isTesting = test.status === 'testing'
  const canContinue = dryRun
    ? true
    : form.archiveUrl !== '' && form.publishingOrganizationKey !== '' && form.installationKey !== ''
      && (hasTypedCredentials || hasSavedCredentials)

  async function handleTestCredentials() {
    setTest({ status: 'testing', message: '' })
    try {
      await api.gbifTestCredentials(form.username, form.password, form.environment)
      setHasSavedCredentials(true) // the backend saves environment/username/password on a successful test
      setTest({ status: 'ok', message: 'Credentials verified.' })
    } catch (e) {
      setTest({ status: 'error', message: e instanceof Error ? e.message : 'Could not verify the credentials.' })
    }
  }

  function handleContinue() {
    onConfigured({
      archiveUrl: form.archiveUrl, environment: form.environment,
      publishingOrganizationKey: form.publishingOrganizationKey, installationKey: form.installationKey,
      registryLanguage: form.registryLanguage, username: form.username, password: form.password,
      outputDir: form.outputDir,
    })
  }

  return (
    <div>
      <p className={hintClass + ' mb-4'}>
        GBIF never hosts a copy of the package — it only registers, in its Registry, a dataset
        whose endpoint points at a URL where the Camtrap DP is already publicly hosted (e.g. a
        Hugging Face Hub repository published earlier in this run).
      </p>

      <div className="mb-4">
        <label className={labelClass} htmlFor="gbif-archive-url">Archive URL</label>
        <input
          id="gbif-archive-url"
          className={inputClass}
          placeholder="https://huggingface.co/datasets/.../resolve/main/datapackage.json"
          value={form.archiveUrl}
          onChange={(e) => setField('archiveUrl', e.target.value)}
        />
        <p className={hintClass}>Public URL where the Camtrap DP is already hosted — GBIF will crawl it from there.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className={labelClass} htmlFor="gbif-environment">Environment</label>
          <select
            id="gbif-environment"
            className={inputClass}
            value={form.environment}
            onChange={(e) => setField('environment', e.target.value)}
          >
            <option value="sandbox">Sandbox (gbif-test.org, testing)</option>
            <option value="production">Production (gbif.org)</option>
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="gbif-registry-language">Registry language</label>
          <input
            id="gbif-registry-language"
            className={inputClass}
            value={form.registryLanguage}
            onChange={(e) => setField('registryLanguage', e.target.value)}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-1">
        <div>
          <label className={labelClass} htmlFor="gbif-org-key">Publishing organization UUID</label>
          <input
            id="gbif-org-key"
            className={inputClass}
            placeholder="UUID"
            value={form.publishingOrganizationKey}
            onChange={(e) => setField('publishingOrganizationKey', e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="gbif-installation-key">Installation UUID</label>
          <input
            id="gbif-installation-key"
            className={inputClass}
            placeholder="UUID"
            value={form.installationKey}
            onChange={(e) => setField('installationKey', e.target.value)}
          />
        </div>
      </div>
      <p className={hintClass + ' mb-6'}>
        Both come from an organization endorsed by a GBIF Participant Node, and an installation
        registered under it — created by hand at{' '}
        <a href="https://www.gbif.org/become-a-publisher" target="_blank" rel="noreferrer" className="underline">
          gbif.org/become-a-publisher
        </a>{' '}
        (manual review, cannot be automated).
      </p>

      <div className="mb-6">
        <div className="grid grid-cols-2 gap-4 mb-1">
          <div>
            <label className={labelClass} htmlFor="gbif-username">GBIF username</label>
            <input
              id="gbif-username"
              className={inputClass}
              value={form.username}
              onChange={(e) => setField('username', e.target.value)}
              autoComplete="username"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="gbif-password">GBIF password</label>
            <input
              id="gbif-password"
              type="password"
              className={inputClass}
              placeholder="••••••••"
              value={form.password}
              onChange={(e) => setField('password', e.target.value)}
              autoComplete="current-password"
            />
          </div>
        </div>
        {hasSavedCredentials && !hasTypedCredentials && (
          <p className={hintClass}>Already saved — leave blank to reuse them.</p>
        )}
        <p className={hintClass}>
          Sign up at{' '}
          <a href="https://www.gbif.org/user/profile" target="_blank" rel="noreferrer" className="underline">
            gbif.org/user/profile
          </a>{' '}
          (or gbif-test.org for the sandbox — a separate account).
        </p>

        {dryRun ? (
          <p className={hintClass + ' text-right'}>Not required for a dry run.</p>
        ) : (
          <>
            <div className="flex justify-end mt-2">
              <button type="button" className={btnOutline} disabled={!canTest || isTesting} onClick={handleTestCredentials}>
                {isTesting && <SmallSpinner />}
                {isTesting ? 'Testing…' : 'Test credentials'}
              </button>
            </div>
            {test.status === 'ok' && (
              <p className="text-sm text-emerald-600 dark:text-emerald-400 text-right mt-2">{test.message}</p>
            )}
            {test.status === 'error' && (
              <p className="text-sm text-red-600 dark:text-red-400 text-right mt-2">{test.message}</p>
            )}
          </>
        )}
      </div>

      <div className="flex justify-end">
        <button type="button" className={btnPrimary} disabled={!canContinue} onClick={handleContinue}>
          Continue
        </button>
      </div>
    </div>
  )
}
