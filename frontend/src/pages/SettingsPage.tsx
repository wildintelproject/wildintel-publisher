import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AppSettings, AppSettingsUpdate, GBIFInstallation, LogLevel, Organization, S3Remote } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnPrimary = 'px-6 py-2.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
const btnOutline = 'px-3 py-1.5 text-sm border border-zinc-300 dark:border-zinc-600 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors'

// ── The form's own state ────────────────────────────────────────────────

/** A saved S3 remote as typed text; the two secrets only ever hold what's
 * being typed now (blank keeps the saved ones — see hasAccessKey/hasSecretKey). */
interface S3RemoteDraft {
  id: string
  name: string
  endpointUrl: string
  region: string
  bucket: string
  prefix: string
  publicBaseUrl: string
  verifySsl: boolean
  accessKey: string
  secretKey: string
  hasAccessKey: boolean
  hasSecretKey: boolean
}

function toRemoteDraft(r: S3Remote): S3RemoteDraft {
  return {
    id: r.id, name: r.name, endpointUrl: r.endpoint_url ?? '', region: r.region ?? '', bucket: r.bucket ?? '',
    prefix: r.prefix ?? '', publicBaseUrl: r.public_base_url ?? '', verifySsl: r.verify_ssl,
    accessKey: '', secretKey: '', hasAccessKey: r.has_access_key, hasSecretKey: r.has_secret_key,
  }
}

function newRemoteId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2)).replace(/-/g, '').slice(0, 8)
}

type Environment = 'sandbox' | 'production'

/** Every scalar field as typed text/select; the two list fields
 * (GBIF.installations, PRODUCT.organizations) are kept as their own
 * structured arrays instead. */
interface Draft {
  trapperUrl: string
  trapperUserName: string
  trapperUserPassword: string
  trapperProjectId: string
  logLevel: LogLevel
  camtrapdpLicenseId: string
  camtrapdpLicenseName: string
  camtrapdpLicenseUrl: string
  camtrapdpDatasetSlug: string
  camtrapdpDatasetName: string
  camtrapdpDescription: string
  trapperRetryAttempts: string
  trapperRetryWaitSeconds: string

  hfhMessage: string
  hfhRepositoryCode: string
  hfhRepoId: string
  hfhUsername: string
  hfhToken: string

  zenodoEnvironment: Environment
  zenodoCommunities: string
  zenodoToken: string

  b2shareEnvironment: Environment
  b2shareCommunityId: string
  b2shareToken: string

  gbifEnvironment: Environment
  gbifPublishingOrganizationKey: string
  gbifInstallationKey: string
  gbifRegistryLanguage: string
  gbifUsername: string
  gbifPassword: string
  gbifInstallations: GBIFInstallation[]

  s3Remotes: S3RemoteDraft[]
  s3RetryAttempts: string
  s3RetryWaitSeconds: string

  organizations: Organization[]
}

function toDraft(s: AppSettings): Draft {
  return {
    trapperUrl: s.TRAPPER.base_url ?? '',
    trapperUserName: '',
    trapperUserPassword: '',
    trapperProjectId: s.TRAPPER.project_id != null ? String(s.TRAPPER.project_id) : '',
    logLevel: s.GENERAL.log_level,
    camtrapdpLicenseId: s.CAMTRAPDP.license_id ?? '',
    camtrapdpLicenseName: s.CAMTRAPDP.license_name ?? '',
    camtrapdpLicenseUrl: s.CAMTRAPDP.license_url ?? '',
    camtrapdpDatasetSlug: s.CAMTRAPDP.dataset_slug ?? '',
    camtrapdpDatasetName: s.CAMTRAPDP.dataset_name ?? '',
    camtrapdpDescription: s.CAMTRAPDP.description ?? '',
    trapperRetryAttempts: String(s.TRAPPER.retry_attempts),
    trapperRetryWaitSeconds: String(s.TRAPPER.retry_wait_seconds),

    hfhMessage: s.HFH.message ?? '',
    hfhRepositoryCode: s.HFH.repository_code ?? '',
    hfhRepoId: s.HFH.repo_id ?? '',
    hfhUsername: s.HFH.username ?? '',
    hfhToken: '',

    zenodoEnvironment: s.ZENODO.environment ?? 'sandbox',
    zenodoCommunities: s.ZENODO.communities ?? '',
    zenodoToken: '',

    b2shareEnvironment: s.B2SHARE.environment ?? 'sandbox',
    b2shareCommunityId: s.B2SHARE.community_id ?? '',
    b2shareToken: '',

    gbifEnvironment: s.GBIF.environment ?? 'sandbox',
    gbifPublishingOrganizationKey: s.GBIF.publishing_organization_key ?? '',
    gbifInstallationKey: s.GBIF.installation_key ?? '',
    gbifRegistryLanguage: s.GBIF.registry_language ?? '',
    gbifUsername: '',
    gbifPassword: '',
    gbifInstallations: s.GBIF.installations,

    s3Remotes: s.S3.remotes.map(toRemoteDraft),
    s3RetryAttempts: String(s.S3.retry_attempts),
    s3RetryWaitSeconds: String(s.S3.retry_wait_seconds),

    organizations: s.PRODUCT.organizations,
  }
}

function orNull(v: string): string | null {
  return v.trim() ? v.trim() : null
}

function projectIdValid(v: string): boolean {
  return v.trim() === '' || /^\d+$/.test(v.trim())
}

// tenacity's own knobs (see common.retrying): attempts is the TOTAL number of
// tries (1 = no retry), wait the base seconds between them (doubling each time).
function retryAttemptsValid(v: string): boolean {
  return /^\d+$/.test(v.trim()) && Number(v) >= 1
}

function retryWaitValid(v: string): boolean {
  return v.trim() !== '' && Number.isFinite(Number(v)) && Number(v) >= 0
}

function toUpdate(d: Draft): AppSettingsUpdate | null {
  if (!projectIdValid(d.trapperProjectId)) return null
  if (!retryAttemptsValid(d.trapperRetryAttempts) || !retryWaitValid(d.trapperRetryWaitSeconds)) return null
  if (!retryAttemptsValid(d.s3RetryAttempts) || !retryWaitValid(d.s3RetryWaitSeconds)) return null
  if (d.s3Remotes.some((r) => r.name.trim() === '')) return null
  return {
    TRAPPER: {
      base_url: orNull(d.trapperUrl),
      user_name: d.trapperUserName || null,
      user_password: d.trapperUserPassword || null,
      project_id: d.trapperProjectId.trim() ? Number(d.trapperProjectId) : null,
      retry_attempts: Number(d.trapperRetryAttempts),
      retry_wait_seconds: Number(d.trapperRetryWaitSeconds),
    },
    GENERAL: { log_level: d.logLevel },
    CAMTRAPDP: {
      license_id: orNull(d.camtrapdpLicenseId),
      license_name: orNull(d.camtrapdpLicenseName),
      license_url: orNull(d.camtrapdpLicenseUrl),
      dataset_slug: orNull(d.camtrapdpDatasetSlug),
      dataset_name: orNull(d.camtrapdpDatasetName),
      description: orNull(d.camtrapdpDescription),
    },
    HFH: {
      message: orNull(d.hfhMessage),
      repository_code: orNull(d.hfhRepositoryCode),
      repo_id: orNull(d.hfhRepoId),
      username: orNull(d.hfhUsername),
      token: d.hfhToken || null,
    },
    ZENODO: {
      environment: d.zenodoEnvironment,
      communities: orNull(d.zenodoCommunities),
      token: d.zenodoToken || null,
    },
    B2SHARE: {
      environment: d.b2shareEnvironment,
      community_id: orNull(d.b2shareCommunityId),
      token: d.b2shareToken || null,
    },
    GBIF: {
      environment: d.gbifEnvironment,
      publishing_organization_key: orNull(d.gbifPublishingOrganizationKey),
      installation_key: orNull(d.gbifInstallationKey),
      registry_language: orNull(d.gbifRegistryLanguage),
      username: d.gbifUsername || null,
      password: d.gbifPassword || null,
      installations: d.gbifInstallations,
    },
    S3: {
      remotes: d.s3Remotes.map((r) => ({
        id: r.id,
        name: r.name.trim(),
        endpoint_url: orNull(r.endpointUrl),
        region: orNull(r.region),
        bucket: orNull(r.bucket),
        prefix: orNull(r.prefix),
        public_base_url: orNull(r.publicBaseUrl),
        verify_ssl: r.verifySsl,
        access_key: r.accessKey || null,
        secret_key: r.secretKey || null,
      })),
      retry_attempts: Number(d.s3RetryAttempts),
      retry_wait_seconds: Number(d.s3RetryWaitSeconds),
    },
    PRODUCT: { organizations: d.organizations },
  }
}

// ── Layout pieces ───────────────────────────────────────────────────────

const LOG_LEVELS: { value: LogLevel; label: string; hint: string }[] = [
  { value: 'ERROR', label: 'Error', hint: 'Only what went wrong.' },
  { value: 'WARNING', label: 'Warning', hint: 'Also what may be wrong: retries, failed images…' },
  { value: 'INFO', label: 'Info', hint: 'Also what the app does: each download, upload, publication… started and finished.' },
  { value: 'DEBUG', label: 'Debug', hint: 'Everything: each image uploaded to the bucket, full tracebacks. Big logs — for tracking a problem down.' },
]

type SectionId = 'general' | 'trapper' | 'camtrapdp' | 'hfh' | 'zenodo' | 'b2share' | 'gbif' | 's3' | 'product'

const SECTIONS: { id: SectionId; label: string; icon: string }[] = [
  { id: 'general', label: 'General', icon: '⚙️' },
  { id: 'trapper', label: 'Trapper', icon: '📷' },
  { id: 'camtrapdp', label: 'Camtrap DP', icon: '🦌' },
  { id: 'hfh', label: 'HuggingFace Hub', icon: '🤗' },
  { id: 'zenodo', label: 'Zenodo', icon: '📚' },
  { id: 'b2share', label: 'B2SHARE', icon: '🗄️' },
  { id: 'gbif', label: 'GBIF', icon: '🌍' },
  { id: 's3', label: 'S3 image hosting', icon: '☁️' },
  { id: 'product', label: 'Organizations', icon: '🏢' },
]

function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: React.ReactNode }) {
  return (
    <div>
      <label className={labelClass}>{label}</label>
      {children}
      {error ? <p className="text-xs text-red-600 dark:text-red-400 mt-1">{error}</p> : hint ? <p className={hintClass}>{hint}</p> : null}
    </div>
  )
}

function TextField({ label, value, onChange, type = 'text', hint, mono }: {
  label: string; value: string; onChange: (v: string) => void; type?: 'text' | 'password'; hint?: string; mono?: boolean
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        type={type} className={`${inputClass} ${mono ? 'font-mono' : ''}`} value={value} aria-label={label}
        onChange={(e) => onChange(e.target.value)} autoComplete={type === 'password' ? 'new-password' : 'off'}
      />
    </Field>
  )
}

function EnvironmentField({ label, value, onChange }: { label: string; value: Environment; onChange: (v: Environment) => void }) {
  return (
    <Field label={label}>
      <select className={inputClass} value={value} aria-label={label} onChange={(e) => onChange(e.target.value as Environment)}>
        <option value="sandbox">Sandbox (testing)</option>
        <option value="production">Production</option>
      </select>
    </Field>
  )
}

const passwordHint = (has: boolean, what = 'value') => (has ? `A ${what} is saved — leave it blank to keep it.` : `No ${what} saved yet.`)

/** The two tenacity knobs shared by TRAPPER and S3 (see common.retrying). */
function RetryFields({ attempts, wait, onAttemptsChange, onWaitChange }: {
  attempts: string; wait: string; onAttemptsChange: (v: string) => void; onWaitChange: (v: string) => void
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <Field
        label="Retry attempts" hint="Total tries per network call before giving up — 1 means no retry."
        error={retryAttemptsValid(attempts) ? null : 'A whole number, 1 or more.'}
      >
        <input
          className={inputClass} inputMode="numeric" value={attempts} aria-label="Retry attempts"
          aria-invalid={!retryAttemptsValid(attempts)} onChange={(e) => onAttemptsChange(e.target.value)}
        />
      </Field>
      <Field
        label="Seconds between retries" hint="Wait before the first retry; it doubles on each further attempt."
        error={retryWaitValid(wait) ? null : 'A number of seconds, 0 or more.'}
      >
        <input
          className={inputClass} inputMode="decimal" value={wait} aria-label="Seconds between retries"
          aria-invalid={!retryWaitValid(wait)} onChange={(e) => onWaitChange(e.target.value)}
        />
      </Field>
    </div>
  )
}

// ── S3 remotes: a list of cards, each edited in a dialog ──────────────────

const iconBtn = 'w-10 h-10 flex items-center justify-center rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors'

function remoteSubtitle(r: S3RemoteDraft): string {
  return [r.bucket && `bucket ${r.bucket}`, r.endpointUrl || 'AWS S3'].filter(Boolean).join(' · ')
}

function S3RemoteDialog({ remote, onChange, onRemove, onClose }: {
  remote: S3RemoteDraft; onChange: (patch: Partial<S3RemoteDraft>) => void; onRemove: () => void; onClose: () => void
}) {
  const [test, setTest] = useState<{ status: 'idle' | 'loading' | 'ok' | 'error'; message: string }>({ status: 'idle', message: '' })
  const edit = (patch: Partial<S3RemoteDraft>) => { onChange(patch); setTest({ status: 'idle', message: '' }) }

  async function handleTest() {
    setTest({ status: 'loading', message: '' })
    try {
      await api.s3TestConnection({
        remoteId: remote.id, endpointUrl: remote.endpointUrl.trim(), region: remote.region.trim(), bucket: remote.bucket.trim(),
        accessKey: remote.accessKey || undefined, secretKey: remote.secretKey || undefined, verifySsl: remote.verifySsl,
      })
      setTest({ status: 'ok', message: 'Connection successful — the bucket is reachable.' })
    } catch (e) {
      setTest({ status: 'error', message: e instanceof Error ? e.message : 'Could not connect to the bucket.' })
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        role="dialog" aria-modal="true" aria-label="S3 remote"
        className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h5 className="text-lg font-semibold">{remote.name.trim() || 'New remote'}</h5>
        <Field label="Name" error={remote.name.trim() ? null : 'A name is required.'}>
          <input className={inputClass} value={remote.name} aria-label="Name" onChange={(e) => edit({ name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <TextField label="Bucket" value={remote.bucket} onChange={(v) => edit({ bucket: v })} mono />
          <TextField label="Region" value={remote.region} onChange={(v) => edit({ region: v })} hint="Defaults to us-east-1 if left blank." mono />
        </div>
        <TextField
          label="Endpoint URL" value={remote.endpointUrl} onChange={(v) => edit({ endpointUrl: v })} mono
          hint="Only needed for a self-hosted/non-AWS provider, e.g. MinIO — leave blank for AWS S3."
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <TextField label="Access key" type="password" value={remote.accessKey} onChange={(v) => edit({ accessKey: v })} hint={passwordHint(remote.hasAccessKey, 'access key')} />
          <TextField label="Secret key" type="password" value={remote.secretKey} onChange={(v) => edit({ secretKey: v })} hint={passwordHint(remote.hasSecretKey, 'secret key')} />
        </div>
        <TextField label="Key prefix" value={remote.prefix} onChange={(v) => edit({ prefix: v })} mono hint="Prepended to every uploaded object's key, e.g. camtrapdp/." />
        <TextField
          label="Public base URL" value={remote.publicBaseUrl} onChange={(v) => edit({ publicBaseUrl: v })} mono
          hint="Custom domain/CDN in front of the bucket, if any — otherwise built from the endpoint or AWS's own bucket URL."
        />
        <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
          <input type="checkbox" className="mt-0.5" checked={!remote.verifySsl} onChange={(e) => edit({ verifySsl: !e.target.checked })} />
          <span>
            <strong>Don't validate the SSL certificate</strong> — only for a trusted endpoint with a
            self-signed certificate; it disables protection against man-in-the-middle attacks.
          </span>
        </label>
        <div>
          <button type="button" className={btnOutline} disabled={!remote.bucket.trim() || test.status === 'loading'} onClick={handleTest}>
            {test.status === 'loading' ? 'Testing…' : 'Test connection'}
          </button>
          {test.status === 'ok' && <p className="text-sm text-emerald-600 dark:text-emerald-400 mt-2">{test.message}</p>}
          {test.status === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mt-2">{test.message}</p>}
        </div>
        <div className="flex items-center justify-between pt-3 border-t border-zinc-200 dark:border-zinc-800">
          <button type="button" className={`${btnOutline} text-red-600 dark:text-red-400`} onClick={onRemove}>Remove remote</button>
          <button type="button" className={btnPrimary} disabled={!remote.name.trim()} onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}

function S3RemotesEditor({ items, onChange }: { items: S3RemoteDraft[]; onChange: (v: S3RemoteDraft[]) => void }) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const editing = items.find((r) => r.id === editingId) ?? null

  function add() {
    const id = newRemoteId()
    onChange([...items, {
      id, name: 'New remote', endpointUrl: '', region: '', bucket: '', prefix: '', publicBaseUrl: '', verifySsl: true,
      accessKey: '', secretKey: '', hasAccessKey: false, hasSecretKey: false,
    }])
    setEditingId(id)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <label className={`${labelClass} mb-0`}>Remotes</label>
        <button type="button" className={iconBtn} aria-label="Add remote" title="Add remote" onClick={add}>+</button>
      </div>
      <div className="space-y-3">
        {items.length === 0 && <p className={hintClass}>No remote yet — the wizard can&rsquo;t upload images until you add one.</p>}
        {items.map((r) => {
          const hasKeys = (r.hasAccessKey || r.accessKey) && (r.hasSecretKey || r.secretKey)
          return (
            <div key={r.id} className="flex items-center gap-4 px-4 py-3 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/60">
              <span className="w-10 h-10 flex items-center justify-center rounded-lg bg-sky-100 dark:bg-sky-900/40 text-xl" aria-hidden="true">☁️</span>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{r.name}</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate">{remoteSubtitle(r)}</p>
              </div>
              <span className={`text-xs px-2 py-1 rounded ${hasKeys ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'}`}>
                {hasKeys ? 'Credentials saved' : 'No credentials'}
              </span>
              <button type="button" className={iconBtn} aria-label={`Edit ${r.name}`} title="Edit" onClick={() => setEditingId(r.id)}>⚙️</button>
            </div>
          )
        })}
      </div>
      {editing && (
        <S3RemoteDialog
          remote={editing}
          onChange={(patch) => onChange(items.map((r) => (r.id === editing.id ? { ...r, ...patch } : r)))}
          onRemove={() => { onChange(items.filter((r) => r.id !== editing.id)); setEditingId(null) }}
          onClose={() => setEditingId(null)}
        />
      )}
    </div>
  )
}

// ── List editors (GBIF.installations, PRODUCT.organizations) ─────────────

function InstallationsEditor({ items, onChange }: { items: GBIFInstallation[]; onChange: (v: GBIFInstallation[]) => void }) {
  const update = (i: number, patch: Partial<GBIFInstallation>) => onChange(items.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i))
  const add = () => onChange([...items, { title: '', sandbox_installation_key: null, production_installation_key: null }])
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <div key={i} className="p-3 border border-zinc-200 dark:border-zinc-700 rounded-lg space-y-2">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <TextField label="Title" value={it.title} onChange={(v) => update(i, { title: v })} />
            </div>
            <button type="button" className={btnOutline} onClick={() => remove(i)}>Remove</button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField
              label="Sandbox installation UUID" mono
              value={it.sandbox_installation_key ?? ''} onChange={(v) => update(i, { sandbox_installation_key: v || null })}
            />
            <TextField
              label="Production installation UUID" mono
              value={it.production_installation_key ?? ''} onChange={(v) => update(i, { production_installation_key: v || null })}
            />
          </div>
        </div>
      ))}
      <button type="button" className={btnOutline} onClick={add}>+ Add installation</button>
    </div>
  )
}

function OrganizationsEditor({ items, onChange }: { items: Organization[]; onChange: (v: Organization[]) => void }) {
  const update = (i: number, patch: Partial<Organization>) => onChange(items.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i))
  const add = () => onChange([...items, {
    title: '', path: null, email: null, gbif_sandbox_organization_key: null, gbif_production_organization_key: null,
  }])
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <div key={i} className="p-3 border border-zinc-200 dark:border-zinc-700 rounded-lg space-y-2">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <TextField label="Title" value={it.title} onChange={(v) => update(i, { title: v })} />
            </div>
            <button type="button" className={btnOutline} onClick={() => remove(i)}>Remove</button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField label="Website" value={it.path ?? ''} onChange={(v) => update(i, { path: v || null })} />
            <TextField label="Contact email (publisher role only)" value={it.email ?? ''} onChange={(v) => update(i, { email: v || null })} />
            <TextField
              label="GBIF sandbox organization UUID" mono
              value={it.gbif_sandbox_organization_key ?? ''} onChange={(v) => update(i, { gbif_sandbox_organization_key: v || null })}
            />
            <TextField
              label="GBIF production organization UUID" mono
              value={it.gbif_production_organization_key ?? ''} onChange={(v) => update(i, { gbif_production_organization_key: v || null })}
            />
          </div>
        </div>
      ))}
      <button type="button" className={btnOutline} onClick={add}>+ Add organization</button>
    </div>
  )
}

// ── The page ────────────────────────────────────────────────────────────

interface Props {
  onClose: () => void
}

/** Edits the app's own settings.toml, one section at a time — the
 * connection/publish defaults every wizard form otherwise reads and saves
 * piecemeal, plus GBIF.installations and PRODUCT.organizations (until now
 * only hand-editable in the file itself, see api.routers.product's own
 * comment). One Save saves every section. */
export default function SettingsPage({ onClose }: Props) {
  const [section, setSection] = useState<SectionId>('general')
  const [saved, setSaved] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'saved' | 'error'; message?: string }>({ kind: 'idle' })
  const [clearLog, setClearLog] = useState<{ kind: 'idle' | 'confirming' | 'clearing' | 'cleared' | 'error'; message?: string }>({ kind: 'idle' })

  async function handleClearLog() {
    setClearLog({ kind: 'clearing' })
    try {
      await api.clearLog()
      setClearLog({ kind: 'cleared' })
    } catch (e) {
      setClearLog({ kind: 'error', message: e instanceof Error ? e.message : 'Could not clear the log.' })
    }
  }

  useEffect(() => {
    api.getSettings()
      .then((s) => { setSaved(s); setDraft(toDraft(s)) })
      .catch((e) => setStatus({ kind: 'error', message: e instanceof Error ? e.message : 'Could not load the settings.' }))
  }, [])

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => (d && { ...d, [key]: value }))
    setStatus({ kind: 'idle' })
  }

  const update = draft && toUpdate(draft)

  async function handleSave() {
    if (!update) return
    setStatus({ kind: 'saving' })
    try {
      const result = await api.saveSettings(update)
      setSaved(result)
      setDraft(toDraft(result))
      setStatus({ kind: 'saved' })
    } catch (e) {
      setStatus({ kind: 'error', message: e instanceof Error ? e.message : 'Could not save the settings.' })
    }
  }

  const current = SECTIONS.find((s) => s.id === section)!

  return (
    <div className="mx-auto px-4 py-6 flex flex-col md:flex-row gap-6" style={{ maxWidth: 1000 }}>
      {/* Sidebar */}
      <nav className="md:w-56 shrink-0 md:border-r border-zinc-200 dark:border-zinc-800 md:pr-5" aria-label="Settings sections">
        <button
          type="button" onClick={onClose}
          className="flex items-center gap-2 px-3 py-2 mb-3 text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
        >
          ← Back
        </button>
        <ul className="flex md:flex-col gap-2 overflow-x-auto">
          {SECTIONS.map(({ id, label, icon }) => {
            const active = id === section
            return (
              <li key={id} className="shrink-0">
                <button
                  type="button" onClick={() => setSection(id)} aria-current={active ? 'page' : undefined}
                  className={[
                    'w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm transition-colors',
                    active ? 'bg-blue-600 text-white' : 'text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800',
                  ].join(' ')}
                >
                  <span aria-hidden="true">{icon}</span>
                  <span>{label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* Section */}
      <div className="flex-1 min-w-0">
        <h4 className="text-xl font-semibold mb-4">{current.label}</h4>

        {!draft && status.kind !== 'error' && <p className="text-sm text-zinc-500 dark:text-zinc-400 py-5">Loading…</p>}

        {draft && saved && section === 'trapper' && (
          <div className="space-y-4">
            <TextField label="Trapper URL" value={draft.trapperUrl} onChange={(v) => set('trapperUrl', v)} mono />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label="Username" value={draft.trapperUserName} onChange={(v) => set('trapperUserName', v)} hint={passwordHint(saved.TRAPPER.has_user_name, 'username')} />
              <TextField label="Password" type="password" value={draft.trapperUserPassword} onChange={(v) => set('trapperUserPassword', v)} hint={passwordHint(saved.TRAPPER.has_user_password, 'password')} />
            </div>
            <Field label="Default classification project id" error={projectIdValid(draft.trapperProjectId) ? null : 'A whole number, or blank.'}>
              <input
                className={inputClass} inputMode="numeric" value={draft.trapperProjectId} aria-label="Default classification project id"
                onChange={(e) => set('trapperProjectId', e.target.value)}
              />
            </Field>
            <RetryFields
              attempts={draft.trapperRetryAttempts} wait={draft.trapperRetryWaitSeconds}
              onAttemptsChange={(v) => set('trapperRetryAttempts', v)} onWaitChange={(v) => set('trapperRetryWaitSeconds', v)}
            />
          </div>
        )}

        {draft && saved && section === 'camtrapdp' && (
          <div className="space-y-4">
            <p className={hintClass}>
              Defaults for any Camtrap DP, whether it comes from Trapper, a local directory or a public URL.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label="Dataset slug" value={draft.camtrapdpDatasetSlug} onChange={(v) => set('camtrapdpDatasetSlug', v)} hint="Short internal identifier — used to derive the dataset name below if left blank." />
              <TextField label="Dataset name" value={draft.camtrapdpDatasetName} onChange={(v) => set('camtrapdpDatasetName', v)} hint="Title a Trapper download starts with; editable in the wizard's metadata step." />
            </div>
            <TextField label="Description" value={draft.camtrapdpDescription} onChange={(v) => set('camtrapdpDescription', v)} hint="Description a Trapper download starts with; editable in the wizard's metadata step." />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <TextField label="License id" value={draft.camtrapdpLicenseId} onChange={(v) => set('camtrapdpLicenseId', v)} />
              <TextField label="License name" value={draft.camtrapdpLicenseName} onChange={(v) => set('camtrapdpLicenseName', v)} />
              <TextField label="License URL" value={draft.camtrapdpLicenseUrl} onChange={(v) => set('camtrapdpLicenseUrl', v)} mono />
            </div>
            <p className={hintClass}>
              The license replaces the &ldquo;private&rdquo; placeholder Trapper leaves in datapackage.json; a real license already in the package is kept.
            </p>
          </div>
        )}

        {draft && saved && section === 'general' && (
          <div className="space-y-6">
            <div className="space-y-2">
              <Field label="Log level" hint={LOG_LEVELS.find((l) => l.value === draft.logLevel)?.hint}>
                <select className={inputClass} value={draft.logLevel} aria-label="Log level" onChange={(e) => set('logLevel', e.target.value as LogLevel)}>
                  {LOG_LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
              </Field>
              <p className={hintClass}>How much the app writes to its log — raise it to Debug to track a problem down, then lower it again. Applied as soon as it&rsquo;s saved.</p>
              {saved.GENERAL.log_level_override && (
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  The environment variable <span className="font-mono">WILDINTEL_PUBLISHER_LOG_LEVEL</span> sets it
                  to <strong>{saved.GENERAL.log_level_override}</strong> for now — it wins over this setting.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Field label="Log file" hint="Rotated at 5 MB, keeping the last 5. Attach it to a bug report.">
                <span className="block font-mono text-sm break-all py-0.5" aria-label="Log file location">{saved.GENERAL.log_file}</span>
              </Field>
              <div className="flex flex-wrap gap-2">
                <a href="/api/settings/log" download className={`${btnOutline} inline-block`}>Download log</a>
                {clearLog.kind !== 'confirming' && (
                  <button
                    type="button" className={`${btnOutline} text-red-600 dark:text-red-400`} disabled={clearLog.kind === 'clearing'}
                    onClick={() => setClearLog({ kind: 'confirming' })}
                  >
                    {clearLog.kind === 'clearing' ? 'Clearing…' : 'Clear log'}
                  </button>
                )}
              </div>
              {clearLog.kind === 'confirming' && (
                <div className="rounded border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-3 text-sm text-zinc-700 dark:text-zinc-300">
                  <p>Delete the log file and its older copies? This can&rsquo;t be undone — download it first if you need it.</p>
                  <div className="flex gap-2 mt-2">
                    <button type="button" onClick={handleClearLog} className="px-3 py-1.5 text-sm rounded bg-red-600 text-white hover:bg-red-700 transition-colors">Yes, clear it</button>
                    <button type="button" className={btnOutline} onClick={() => setClearLog({ kind: 'idle' })}>Cancel</button>
                  </div>
                </div>
              )}
              {clearLog.kind === 'cleared' && <p className="text-xs text-emerald-700 dark:text-emerald-400">Log cleared — a new one starts now.</p>}
              {clearLog.kind === 'error' && <p className="text-xs text-red-600 dark:text-red-400">{clearLog.message}</p>}
            </div>
          </div>
        )}

        {draft && saved && section === 'hfh' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label="Username / organization" value={draft.hfhUsername} onChange={(v) => set('hfhUsername', v)} />
              <TextField label="Access token" type="password" value={draft.hfhToken} onChange={(v) => set('hfhToken', v)} hint={passwordHint(saved.HFH.has_token, 'token')} />
            </div>
            <TextField label="Default repo id" value={draft.hfhRepoId} onChange={(v) => set('hfhRepoId', v)} hint="Format: user_or_org/dataset." />
            <TextField label="Citation message" value={draft.hfhMessage} onChange={(v) => set('hfhMessage', v)} />
            <TextField label="Repository code URL" value={draft.hfhRepositoryCode} onChange={(v) => set('hfhRepositoryCode', v)} mono />
          </div>
        )}

        {draft && saved && section === 'zenodo' && (
          <div className="space-y-4">
            <EnvironmentField label="Environment" value={draft.zenodoEnvironment} onChange={(v) => set('zenodoEnvironment', v)} />
            <TextField label="Access token" type="password" value={draft.zenodoToken} onChange={(v) => set('zenodoToken', v)} hint={passwordHint(saved.ZENODO.has_token, 'token')} />
            <TextField label="Communities" value={draft.zenodoCommunities} onChange={(v) => set('zenodoCommunities', v)} hint="Comma-separated, e.g. wildintelproject." />
          </div>
        )}

        {draft && saved && section === 'b2share' && (
          <div className="space-y-4">
            <EnvironmentField label="Environment" value={draft.b2shareEnvironment} onChange={(v) => set('b2shareEnvironment', v)} />
            <TextField label="Access token" type="password" value={draft.b2shareToken} onChange={(v) => set('b2shareToken', v)} hint={passwordHint(saved.B2SHARE.has_token, 'token')} />
            <TextField label="Community UUID" value={draft.b2shareCommunityId} onChange={(v) => set('b2shareCommunityId', v)} mono />
          </div>
        )}

        {draft && saved && section === 'gbif' && (
          <div className="space-y-4">
            <EnvironmentField label="Environment" value={draft.gbifEnvironment} onChange={(v) => set('gbifEnvironment', v)} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label="Username" value={draft.gbifUsername} onChange={(v) => set('gbifUsername', v)} hint={passwordHint(saved.GBIF.has_username, 'username')} />
              <TextField label="Password" type="password" value={draft.gbifPassword} onChange={(v) => set('gbifPassword', v)} hint={passwordHint(saved.GBIF.has_password, 'password')} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label="Publishing organization UUID" value={draft.gbifPublishingOrganizationKey} onChange={(v) => set('gbifPublishingOrganizationKey', v)} mono />
              <TextField label="Installation UUID" value={draft.gbifInstallationKey} onChange={(v) => set('gbifInstallationKey', v)} mono />
            </div>
            <TextField label="Registry language (ISO 639-2/T)" value={draft.gbifRegistryLanguage} onChange={(v) => set('gbifRegistryLanguage', v)} />
            <div>
              <label className={labelClass}>Selectable installations</label>
              <p className={`${hintClass} mb-2`}>Offered as GBIFPublishForm&rsquo;s own &ldquo;Installation UUID&rdquo; quick-fill dropdown.</p>
              <InstallationsEditor items={draft.gbifInstallations} onChange={(v) => set('gbifInstallations', v)} />
            </div>
          </div>
        )}

        {draft && saved && section === 's3' && (
          <div className="space-y-4">
            <p className={hintClass}>
              S3-compatible buckets (AWS S3, MinIO, or any other provider speaking the same API) the wizard offers to
              upload a Camtrap DP&rsquo;s own images to, right after its metadata step and before you choose where
              to publish — once done, media.csv&rsquo;s own filePath points at these public URLs instead of local files.
              Pick which remote to use in the wizard.
            </p>
            <S3RemotesEditor items={draft.s3Remotes} onChange={(v) => set('s3Remotes', v)} />
            <RetryFields
              attempts={draft.s3RetryAttempts} wait={draft.s3RetryWaitSeconds}
              onAttemptsChange={(v) => set('s3RetryAttempts', v)} onWaitChange={(v) => set('s3RetryWaitSeconds', v)}
            />
          </div>
        )}

        {draft && saved && section === 'product' && (
          <div className="space-y-4">
            <p className={hintClass}>
              Selectable publisher/rights holder organizations for the wizard&rsquo;s metadata-editing step — the same list
              also backs GBIF&rsquo;s own &ldquo;Publishing organization UUID&rdquo; quick-fill.
            </p>
            <OrganizationsEditor items={draft.organizations} onChange={(v) => set('organizations', v)} />
          </div>
        )}

        <div className="flex items-center justify-end gap-4 pt-5 mt-6 border-t border-zinc-200 dark:border-zinc-800">
          {status.kind === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mr-auto">{status.message}</p>}
          {status.kind === 'saved' && <p className="text-sm text-emerald-700 dark:text-emerald-400 mr-auto">Settings saved.</p>}
          {draft && !update && <p className="text-sm text-red-600 dark:text-red-400 mr-auto">Fix the values marked in red first.</p>}
          <button type="button" className={btnPrimary} disabled={!update || status.kind === 'saving'} onClick={handleSave}>
            {status.kind === 'saving' ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
