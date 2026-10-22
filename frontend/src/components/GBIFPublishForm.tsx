import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Organization, GBIFInstallation, Publication } from '../types'
import { Section } from './FormSection'
import InstancePicker from './InstancePicker'

// This organization's own UUID for `environment` — sandbox and production
// are separate GBIF Registry systems, each with its own UUID for the same
// real-world organization (see wildintel_publisher.config.
// Organization's own docstring) — never derived from one another.
function gbifKeyForEnv(org: Organization, environment: string): string | null {
  return (environment === 'production' ? org.gbif_production_organization_key : org.gbif_sandbox_organization_key) ?? null
}

// Same idea as gbifKeyForEnv above, but for a GBIF installation (see
// wildintel_publisher.config.GBIFInstallation) instead of an organization.
function installationKeyForEnv(installation: GBIFInstallation, environment: string): string | null {
  return (
    environment === 'production' ? installation.production_installation_key : installation.sandbox_installation_key
  ) ?? null
}

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
  // UUID of an existing GBIF dataset to update — takes priority over
  // whatever the backend's own gbif_linked_dataset_record.json remembers
  // (see wildintel_publisher.services.gbif.register_gbif_dataset's own
  // docstring). Blank creates a brand new dataset instead. Pick one from
  // the "Search existing datasets" button below, or type it by hand.
  datasetKey: string
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
   * (see WizardPage), since that URL is fully deterministic ahead of time. */
  suggestedArchiveUrl?: string
  /** True when Hugging Face Hub is ALSO selected in this run (see WizardPage,
   * which forces HFH to publish first whenever both are picked) — the
   * archive URL is then fully determined by HFH's own repo_id, so editing
   * it to anything else would just be wrong. Makes the field read-only
   * instead of merely pre-filled. */
  archiveUrlLocked?: boolean
  /** True when Hugging Face Hub is scheduled to publish in this SAME run,
   * before GBIF's own turn (see WizardPage) — the suggested archive URL is
   * fully known ahead of time, but the file itself won't actually exist on
   * Hugging Face Hub until the publish sequence really runs. Used only to
   * show a caveat next to Validate archive, so a 404 at this stage doesn't
   * read as something being wrong. */
  archiveNotPublishedYet?: boolean
  /** True when there's no Hugging Face Hub repo in this run at all (see
   * WizardPage) — camtrapdp-remote.zip is now generated regardless of
   * Mirror/Link mode, so this is only about HFH being absent entirely, not
   * which mode it publishes in. Without it, the locally fetched/downloaded
   * copy (step "Where is it located?") only ever served to extract
   * metadata.json's title/description/license here; it's never what GBIF
   * will actually crawl. Shown as a clarifying note next to Archive URL, so
   * it's clear a different, already-public copy needs to be pointed at by
   * hand. */
  standaloneRegistration?: boolean
  /** True when Zenodo and/or B2SHARE are selected in this same run instead
   * of Hugging Face Hub (see WizardPage) — both now also produce a
   * camtrapdp-remote.zip/camtrapdp.zip of their own, but unlike Hugging Face
   * Hub's user-chosen repo_id, their deposition/record id (and so the
   * file's own public URL) is only assigned once THEY actually upload,
   * which hasn't happened yet at this step. Shown instead of
   * standaloneRegistration's more generic note, since the archive isn't
   * really "unrelated" here — it just isn't known yet. */
  pendingFromOtherRepo?: boolean
  /** A previously-collected config for this same repository — given when
   * the user goes Back to re-visit a step they already configured (see
   * WizardPage's Back button in the "configuring one repository at a time"
   * screen). Seeds every field from it instead of settings.toml/blank, so
   * going back doesn't throw away what was already typed. */
  initialConfig?: GBIFPublishConfig
  /** Renders a "Back to X" button next to Continue, at the same height,
   * instead of Continue alone — omitted for the first repository in the
   * publish order (see WizardPage), which has nothing to go back to. */
  onBack?: () => void
  backLabel?: string
  /** Text of the button that confirms this form. */
  continueLabel?: string
  /** Called once the user confirms this repository's configuration is
   * complete — the wizard collects one of these per selected repository
   * before actually publishing anything (see WizardPage). */
  /** New dataset vs. new version (see PublicationKindPicker) — hides the
   * existing-dataset field for a new dataset, and pre-fills it (plus its
   * environment) from the previous version's own GBIF dataset otherwise. */
  publication?: Publication | null
  onConfigured: (config: GBIFPublishConfig) => void
}

type TestStatus = 'idle' | 'testing' | 'ok' | 'error'

export default function GBIFPublishForm({
  dryRun, suggestedArchiveUrl, archiveUrlLocked, archiveNotPublishedYet, standaloneRegistration,
  pendingFromOtherRepo, initialConfig, onBack, backLabel, continueLabel = 'Continue', onConfigured, publication,
}: Props) {
  const found = publication?.kind === 'version' ? publication.previous?.gbif ?? null : null
  const [form, setForm] = useState(() => ({
    outputDir: initialConfig?.outputDir ?? '', archiveUrl: initialConfig?.archiveUrl ?? '',
    environment: initialConfig?.environment ?? found?.environment ?? 'sandbox',
    datasetKey: initialConfig?.datasetKey ?? found?.dataset_key ?? '',
  }))
  // The organization, installation, language and account of each environment come from the settings.
  const [registryLanguage, setRegistryLanguage] = useState(initialConfig?.registryLanguage ?? 'eng')
  // Saved per environment (sandbox/production have their own account, organization and installation).
  const [savedCredentials, setSavedCredentials] = useState<Record<'sandbox' | 'production', boolean>>({ sandbox: false, production: false })
  const [savedKeys, setSavedKeys] = useState<Record<string, { publishing_organization_key: string | null; installation_key: string | null }>>({})
  const hasSavedCredentials = savedCredentials[form.environment as 'sandbox' | 'production'] ?? false
  const [archiveCheck, setArchiveCheck] = useState<{ status: TestStatus; message: string }>({ status: 'idle', message: '' })
  // Results of the "Search existing datasets" button below (see
  // handleSearchDatasets) — datasets already published by
  // form.publishingOrganizationKey on form.environment, so the user can
  // pick a dataset_key from a list instead of typing/tracking a UUID by
  // hand. Cleared (back to 'idle') whenever the org or environment change,
  // since a stale result list would no longer reflect either.
  const [datasetSearch, setDatasetSearch] = useState<{
    status: TestStatus; message: string; results: { key: string; title: string }[]
  }>({ status: 'idle', message: '', results: [] })
  // settings.toml's own PRODUCT.organizations (see api.organizations
  // and WizardPage's own organizationOptions, which reads the same list for
  // its Publisher/Rights holder dropdowns) — offered here as a quick-fill
  // for "Publishing organization UUID" below, restricted to whichever
  // organizations actually have a key configured for the CURRENT
  // environment (see gbifOrgOptions below).
  const [organizationOptions, setOrganizationOptions] = useState<Organization[]>([])
  // settings.toml's own GBIF.installations — same idea as
  // organizationOptions above, for "Installation UUID" instead of
  // "Publishing organization UUID" (see installationKeyForEnv/
  // gbifInstallationOptions below).
  const [installationOptions, setInstallationOptions] = useState<GBIFInstallation[]>([])
  // Prefill from settings.toml — the same file 'gbif config' reads/writes on
  // the CLI. The credentials themselves are never sent to the frontend;
  // leaving them blank later reuses whatever is already saved. Form fields
  // are left alone when initialConfig is given (going Back) — those values
  // are already known-good, no need to re-fetch them. hasSavedCredentials
  // is fetched regardless, though: it isn't a form field the user could
  // have typed over, and going Back with an initialConfig whose own
  // username/password were left blank (relying on the saved ones) would
  // otherwise leave canContinue permanently false — the Continue button
  // stuck disabled with no way to re-enable it short of retyping
  // credentials that were never needed in the first place.
  useEffect(() => {
    api.gbifGetConfig()
      .then((config) => {
        setSavedCredentials(config.has_credentials_by_environment)
        setSavedKeys(config.keys_by_environment)
        if (initialConfig) return
        const environment = found?.environment ?? config.environment
        setForm((f) => ({ ...f, outputDir: config.output_dir, environment }))
        setRegistryLanguage(config.registry_language ?? 'eng')
      })
      .catch(() => {})
  }, [initialConfig])

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

  useEffect(() => {
    api.organizations().then(setOrganizationOptions).catch(() => { /* quick-fill just stays unavailable */ })
  }, [])

  useEffect(() => {
    api.gbifInstallations().then(setInstallationOptions).catch(() => { /* quick-fill just stays unavailable */ })
  }, [])

  const organizationKey = savedKeys[form.environment]?.publishing_organization_key ?? ''
  const installationKey = savedKeys[form.environment]?.installation_key ?? ''
  const organizationName = organizationOptions.find((o) => gbifKeyForEnv(o, form.environment) === organizationKey)?.title ?? organizationKey
  const installationName = installationOptions.find((i) => installationKeyForEnv(i, form.environment) === installationKey)?.title ?? installationKey

  function setField(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
    if (key === 'archiveUrl') setArchiveCheck({ status: 'idle', message: '' })
    // A stale result list would no longer reflect the environment it was searched under.
    if (key === 'environment') setDatasetSearch({ status: 'idle', message: '', results: [] })
  }

  async function handleSearchDatasets() {
    setDatasetSearch({ status: 'testing', message: '', results: [] })
    try {
      const results = await api.gbifOrganizationDatasets(organizationKey, form.environment)
      setDatasetSearch({
        status: 'ok',
        message: results.length === 0 ? 'No datasets found for this organization yet.' : '',
        results,
      })
    } catch (e) {
      setDatasetSearch({
        status: 'error', results: [],
        message: e instanceof Error ? e.message : 'Could not search for existing datasets.',
      })
    }
  }

  const canContinue = (dryRun
    ? true
    : form.archiveUrl !== '' && organizationKey !== '' && installationKey !== '' && hasSavedCredentials)
    // A new version updates the previous version's own GBIF dataset.
    && !(found && form.datasetKey.trim() === '')

  async function handleValidateArchive() {
    setArchiveCheck({ status: 'testing', message: '' })
    try {
      await api.gbifValidateArchive(form.archiveUrl)
      setArchiveCheck({ status: 'ok', message: 'Valid Camtrap DP zip archive.' })
    } catch (e) {
      setArchiveCheck({
        status: 'error',
        message: e instanceof Error ? e.message : 'Could not validate the archive.',
      })
    }
  }

  function handleContinue() {
    onConfigured({
      archiveUrl: form.archiveUrl, environment: form.environment,
      publishingOrganizationKey: organizationKey, installationKey,
      registryLanguage, username: '', password: '',
      outputDir: form.outputDir, datasetKey: form.datasetKey,
    })
  }

  return (
    <div>
      <p className={hintClass + ' mb-4'}>
        GBIF never hosts a copy of the package — it only registers, in its Registry, a dataset
        whose endpoint points at a URL where the Camtrap DP is already publicly hosted (e.g. a
        Hugging Face Hub repository published earlier in this run).
      </p>

      <Section title="Where to publish">
        <InstancePicker
          name="gbif-environment" repository="GBIF" credential="account"
          value={form.environment} onChange={(env) => setField('environment', env)}
          hasToken={savedCredentials} communities={{}} dryRun={dryRun}
          subject={organizationKey && installationKey ? (
            <>
              Registered under <strong className="text-zinc-800 dark:text-zinc-200">{organizationName}</strong>, installation{' '}
              <strong className="text-zinc-800 dark:text-zinc-200">{installationName}</strong>
            </>
          ) : (
            <span className="text-amber-600 dark:text-amber-400">
              No publishing organization and installation are saved for {form.environment === 'sandbox' ? 'Sandbox' : 'Production'} yet
            </span>
          )}
        />
      {(publication?.kind === 'version' || (!publication && form.datasetKey.trim() !== '')) && (
        <div className="mt-6">
          <label className={labelClass} htmlFor="gbif-dataset-key">
            {found ? "Previous version's GBIF dataset UUID" : 'Dataset UUID (leave blank to create a new dataset)'}
          </label>
          <div className="flex gap-2">
            <input
              id="gbif-dataset-key"
              className={inputClass}
              placeholder="UUID — leave blank to create a new dataset"
              value={form.datasetKey}
              onChange={(e) => setField('datasetKey', e.target.value)}
            />
            <button
              type="button" className={btnOutline}
              disabled={!organizationKey || datasetSearch.status === 'testing'}
              onClick={handleSearchDatasets}
            >
              {datasetSearch.status === 'testing' && <SmallSpinner />}
              {datasetSearch.status === 'testing' ? 'Searching…' : 'Search existing datasets'}
            </button>
          </div>
          <p className={hintClass}>
            Publishing this run updates that exact dataset instead of creating a new one — takes priority
            over whatever this app already remembers locally. Search looks up datasets already published
            by the organization above, on the selected environment.
          </p>
          {datasetSearch.status === 'error' && (
            <p className="text-sm text-red-600 dark:text-red-400 mt-1">{datasetSearch.message}</p>
          )}
          {datasetSearch.status === 'ok' && datasetSearch.message && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">{datasetSearch.message}</p>
          )}
          {datasetSearch.status === 'ok' && datasetSearch.results.length > 0 && (
            <ul className="mt-2 border border-zinc-300 dark:border-zinc-700 rounded divide-y divide-zinc-200 dark:divide-zinc-700 max-h-48 overflow-y-auto">
              {datasetSearch.results.map((d) => (
                <li key={d.key}>
                  <button
                    type="button"
                    onClick={() => {
                      setField('datasetKey', d.key)
                      setDatasetSearch({ status: 'idle', message: '', results: [] })
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 dark:hover:bg-blue-950/30"
                  >
                    <div className="text-zinc-900 dark:text-zinc-100">{d.title}</div>
                    <div className="text-xs text-zinc-500 dark:text-zinc-400 font-mono">{d.key}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        {found && (
          <p className={hintClass}>
            Pre-filled from the previous version: this run updates that same GBIF dataset (GBIF datasets have no
            versions of their own).
          </p>
        )}
        {publication?.kind === 'version' && !found && (
          <p className={hintClass}>
            No GBIF dataset was found for the previous version — leave this blank to register the dataset's first one.
          </p>
        )}
        {found && form.environment !== found.environment && (
          <p className="text-sm text-amber-600 dark:text-amber-400 mt-1">
            ⚠ The previous version is on GBIF's {found.environment} environment, not {form.environment}.
          </p>
        )}
        </div>
      )}

      </Section>

      <Section title="What gets registered">
      <div>
        <label className={labelClass} htmlFor="gbif-archive-url">Archive URL</label>
        <input
          id="gbif-archive-url"
          className={inputClass + (archiveUrlLocked ? ' opacity-75 cursor-not-allowed' : '')}
          placeholder="https://huggingface.co/datasets/.../resolve/main/camtrapdp-remote.zip"
          value={form.archiveUrl}
          onChange={(e) => setField('archiveUrl', e.target.value)}
          readOnly={archiveUrlLocked}
        />
        {archiveUrlLocked ? (
          <p className={hintClass}>
            Fixed to Hugging Face Hub's own camtrapdp-remote.zip, since it's publishing first in this
            same run — there's no other valid value once both are selected together.
          </p>
        ) : (
          <p className={hintClass}>
            Public URL where the Camtrap DP is already hosted — GBIF will crawl it from there. Must be
            a zip archive (e.g. camtrapdp-remote.zip — not camtrapdp-local.zip, whose media.csv uses
            relative paths meaningless once extracted in isolation, nor a bare datapackage.json).
          </p>
        )}
        {standaloneRegistration && (
          <p className={hintClass}>
            This isn't derived automatically here — not from the local copy you just fetched in
            "Where is it located?" (only used to read its title/description/license), and not from
            Hugging Face Hub either if it's not publishing a self-contained archive in this run (Link
            mode never creates one). This URL must point to a completely separate, already-public copy
            of the same Camtrap DP (e.g. hosted outside this tool, or from an earlier publish).
          </p>
        )}
        {pendingFromOtherRepo && (
          <p className={hintClass}>
            Zenodo/B2SHARE will also publish a Camtrap DP archive in this same run, but their own
            record isn't assigned until they actually upload — its URL isn't known yet, unlike Hugging
            Face Hub's predictable one. Either leave GBIF's own registration for a separate run
            afterward (once you have that URL, register it standalone — see "Where is it located?" →
            Public URL), or, if you already know it from an earlier publish, enter it here by hand.
          </p>
        )}
        {archiveNotPublishedYet && (
          <p className={hintClass + ' text-amber-600 dark:text-amber-400'}>
            ⚠ Hugging Face Hub hasn't published yet in this run — this file won't exist until
            publishing actually finishes, so validating it now will fail even though everything is
            configured correctly. Only validate here if this URL already points to something already
            published (e.g. from an earlier run).
          </p>
        )}
        <div className="flex justify-end mt-2">
          <button
            type="button" className={btnOutline}
            disabled={form.archiveUrl === '' || archiveCheck.status === 'testing'}
            onClick={handleValidateArchive}
          >
            {archiveCheck.status === 'testing' && <SmallSpinner />}
            {archiveCheck.status === 'testing' ? 'Validating…' : 'Validate archive'}
          </button>
        </div>
        {archiveCheck.status === 'ok' && (
          <p className="text-sm text-emerald-600 dark:text-emerald-400 text-right mt-2">{archiveCheck.message}</p>
        )}
        {archiveCheck.status === 'error' && (
          <p className="text-sm text-red-600 dark:text-red-400 text-right mt-2">{archiveCheck.message}</p>
        )}
      </div>

      </Section>

      <div className="flex justify-between items-start">
        {onBack && (
          <button type="button" className={btnOutline} onClick={onBack}>
            {backLabel ?? '← Back'}
          </button>
        )}
        <button type="button" className={`${btnOutline} ml-auto`} disabled={!canContinue} onClick={handleContinue}>
          {continueLabel}<span aria-hidden="true"> →</span>
        </button>
      </div>
    </div>
  )
}

type SyncStatus = 'idle' | 'running' | 'done' | 'error'

/** Rendered by the wizard's final "All done!" screen, but only if this run's
 * GBIF registration actually came back with a DOI (see WizardPage — most
 * organizations don't get one automatically, only those with their own
 * DataCite arrangement configured with GBIF; see gbif.register_gbif_dataset).
 * Reflects that DOI into an already-published HFH export's CITATION.cff.
 * Self-contained: only needs the GBIF output directory, everything else
 * (HFH export dir/username/token) is read from settings.toml or typed in
 * here — same shape as ZenodoPublishForm's own SyncDoiSection. */
export function GBIFSyncDoiSection({
  gbifOutputDir, alreadySyncedRepoUrl,
}: { gbifOutputDir: string; alreadySyncedRepoUrl?: string | null }) {
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
      const result = await api.gbifSyncDoi({ gbifOutputDir, hfhOutputDir, hfhRepoId, hfhToken: token })
      setSync({ status: 'done', repoUrl: result.repo_url, error: null })
    } catch (e) {
      setSync({ status: 'error', repoUrl: null, error: e instanceof Error ? e.message : 'Could not sync the DOI.' })
    }
  }

  if (sync.status === 'done' || alreadySyncedRepoUrl) {
    const repoUrl = sync.repoUrl ?? alreadySyncedRepoUrl ?? ''
    return (
      <div className={successPanel + ' mt-6'}>
        <CheckIcon />
        <span>
          {alreadySyncedRepoUrl && sync.status !== 'done'
            ? 'GBIF’s DOI was automatically synced to '
            : 'DOI synced to '}
          <a href={repoUrl} target="_blank" rel="noreferrer" className="underline font-mono">
            {repoUrl}
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
        GBIF assigned this dataset a DOI — reflects it in the CITATION.cff of an already-published
        Hugging Face Hub dataset.
      </p>

      <div className="mb-4">
        <span className={labelClass}>Hugging Face Hub export directory</span>
        <p className="text-sm font-mono text-zinc-600 dark:text-zinc-400 break-all">{hfhOutputDir}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className={labelClass} htmlFor="gbif-sync-hfh-user">User or organization</label>
          <input
            id="gbif-sync-hfh-user"
            className={inputClass}
            placeholder="user_or_org"
            value={hfUser}
            onChange={(e) => setHfUser(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="gbif-sync-hfh-repo-name">Repository name</label>
          <input
            id="gbif-sync-hfh-repo-name"
            className={inputClass}
            placeholder="dataset"
            value={repoName}
            onChange={(e) => setRepoName(e.target.value)}
          />
        </div>
      </div>

      <div className="mb-4">
        <label className={labelClass} htmlFor="gbif-sync-hfh-token">HuggingFace Hub token</label>
        <input
          id="gbif-sync-hfh-token"
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
