import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { AppSettings, AppSettingsUpdate, ConfigInfo, VersionCheck, GBIFInstallation, LogLevel, Organization, ProductAuthor, S3Remote } from '../types'

// Same look as wildintel-zooniverse's settings page: filled, rounded boxes with the
// label inside, base-size text and stroke icons.
const inputClass = 'block w-full bg-transparent text-base text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500 outline-none py-0.5'
const labelClass = 'block text-base text-zinc-800 dark:text-zinc-200'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnPrimary = 'px-6 py-2.5 text-sm bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
const btnOutline = 'inline-flex items-center justify-center px-4 py-2 text-sm rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50'
// A destructive action: the same red as wildintel-zooniverse's Clear log. Not btnOutline plus
// a red text class — btnOutline's own text colour would compete with it.
const btnDanger = 'inline-flex items-center justify-center px-4 py-2 text-sm rounded-xl bg-zinc-100 dark:bg-zinc-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors disabled:opacity-50'

// ── Icons (24×24, stroke — lucide's shapes) ─────────────────────────────

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}

const SlidersIcon = () => (
  <Icon>
    <path d="M4 21v-7" /><path d="M4 10V3" /><path d="M12 21v-9" /><path d="M12 8V3" />
    <path d="M20 21v-5" /><path d="M20 12V3" /><path d="M2 14h4" /><path d="M10 8h4" /><path d="M18 16h4" />
  </Icon>
)
const CameraIcon = () => (
  <Icon>
    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
    <circle cx="12" cy="13" r="3" />
  </Icon>
)
const PackageIcon = () => (
  <Icon>
    <path d="m7.5 4.27 9 5.15" />
    <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
    <path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />
  </Icon>
)
const LayersIcon = () => (
  <Icon>
    <path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z" />
    <path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65" />
    <path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" />
  </Icon>
)
const CloudIcon = () => (
  <Icon>
    <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
  </Icon>
)
const BuildingIcon = () => (
  <Icon>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M9 22v-4h6v4" />
    <path d="M8 6h.01" /><path d="M16 6h.01" /><path d="M12 6h.01" />
    <path d="M12 10h.01" /><path d="M12 14h.01" /><path d="M16 10h.01" /><path d="M16 14h.01" /><path d="M8 10h.01" /><path d="M8 14h.01" />
  </Icon>
)
const UserIcon = () => (
  <Icon>
    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </Icon>
)
const FileIcon = () => (
  <Icon>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <path d="M16 13H8" /><path d="M16 17H8" />
  </Icon>
)
const GlobeIcon = () => (
  <Icon>
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </Icon>
)
const BookIcon = () => (
  <Icon>
    <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
  </Icon>
)
const DatabaseIcon = () => (
  <Icon>
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5v14a9 3 0 0 0 18 0V5" />
    <path d="M3 12a9 3 0 0 0 18 0" />
  </Icon>
)
const BoxesIcon = () => (
  <Icon>
    <path d="M12 3 3 8l9 5 9-5-9-5z" />
    <path d="M3 8v8l9 5 9-5V8" />
    <path d="M12 13v8" />
  </Icon>
)
const GearIcon = () => (
  <Icon>
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
)
const FolderIcon = () => (
  <Icon>
    <path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />
  </Icon>
)
const DownloadIcon = () => (
  <Icon>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <path d="m7 10 5 5 5-5" /><path d="M12 15V3" />
  </Icon>
)
const BackIcon = () => (
  <Icon>
    <path d="M19 12H5" />
    <path d="m12 19-7-7 7-7" />
  </Icon>
)

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
 * (GBIF.installations, PRODUCT.organizations, PRODUCT.authors) are kept as their own
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
  trapperDownloadWorkers: string
  trapperRetryAttempts: string
  trapperRetryWaitSeconds: string

  hfhMessage: string
  hfhRepositoryCode: string
  hfhRepoId: string
  hfhUsername: string
  hfhToken: string

  zenodoEnvironment: Environment
  zenodoSandboxCommunities: string
  zenodoProductionCommunities: string
  zenodoSandboxToken: string
  zenodoProductionToken: string

  b2shareEnvironment: Environment
  b2shareSandboxCommunityId: string
  b2shareProductionCommunityId: string
  b2shareSandboxToken: string
  b2shareProductionToken: string

  gbifEnvironment: Environment
  gbifSandboxPublishingOrganizationKey: string
  gbifProductionPublishingOrganizationKey: string
  gbifSandboxInstallationKey: string
  gbifProductionInstallationKey: string
  gbifRegistryLanguage: string
  gbifSandboxUsername: string
  gbifSandboxPassword: string
  gbifProductionUsername: string
  gbifProductionPassword: string
  gbifInstallations: GBIFInstallation[]

  s3Remotes: S3RemoteDraft[]
  s3RetryAttempts: string
  s3RetryWaitSeconds: string

  organizations: Organization[]
  authors: ProductAuthor[]
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
    trapperDownloadWorkers: String(s.TRAPPER.download_workers),
    trapperRetryAttempts: String(s.TRAPPER.retry_attempts),
    trapperRetryWaitSeconds: String(s.TRAPPER.retry_wait_seconds),

    hfhMessage: s.HFH.message ?? '',
    hfhRepositoryCode: s.HFH.repository_code ?? '',
    hfhRepoId: s.HFH.repo_id ?? '',
    hfhUsername: s.HFH.username ?? '',
    hfhToken: '',

    zenodoEnvironment: s.ZENODO.environment ?? 'sandbox',
    zenodoSandboxCommunities: s.ZENODO.sandbox_communities ?? '',
    zenodoProductionCommunities: s.ZENODO.production_communities ?? '',
    zenodoSandboxToken: '',
    zenodoProductionToken: '',

    b2shareEnvironment: s.B2SHARE.environment ?? 'sandbox',
    b2shareSandboxCommunityId: s.B2SHARE.sandbox_community_id ?? '',
    b2shareProductionCommunityId: s.B2SHARE.production_community_id ?? '',
    b2shareSandboxToken: '',
    b2shareProductionToken: '',

    gbifEnvironment: s.GBIF.environment ?? 'sandbox',
    gbifSandboxPublishingOrganizationKey: s.GBIF.sandbox_publishing_organization_key ?? '',
    gbifProductionPublishingOrganizationKey: s.GBIF.production_publishing_organization_key ?? '',
    gbifSandboxInstallationKey: s.GBIF.sandbox_installation_key ?? '',
    gbifProductionInstallationKey: s.GBIF.production_installation_key ?? '',
    gbifRegistryLanguage: s.GBIF.registry_language ?? '',
    gbifSandboxUsername: '',
    gbifSandboxPassword: '',
    gbifProductionUsername: '',
    gbifProductionPassword: '',
    gbifInstallations: s.GBIF.installations,

    s3Remotes: s.S3.remotes.map(toRemoteDraft),
    s3RetryAttempts: String(s.S3.retry_attempts),
    s3RetryWaitSeconds: String(s.S3.retry_wait_seconds),

    organizations: s.PRODUCT.organizations,
    authors: s.PRODUCT.authors,
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

// TrapperSettings.download_workers' own bounds.
const MAX_DOWNLOAD_WORKERS = 32
function downloadWorkersValid(v: string): boolean {
  return /^\d+$/.test(v.trim()) && Number(v) >= 1 && Number(v) <= MAX_DOWNLOAD_WORKERS
}

function toUpdate(d: Draft): AppSettingsUpdate | null {
  if (!projectIdValid(d.trapperProjectId)) return null
  if (!downloadWorkersValid(d.trapperDownloadWorkers)) return null
  if (!retryAttemptsValid(d.trapperRetryAttempts) || !retryWaitValid(d.trapperRetryWaitSeconds)) return null
  if (!retryAttemptsValid(d.s3RetryAttempts) || !retryWaitValid(d.s3RetryWaitSeconds)) return null
  if (d.s3Remotes.some((r) => r.name.trim() === '')) return null
  return {
    TRAPPER: {
      base_url: orNull(d.trapperUrl),
      user_name: d.trapperUserName || null,
      user_password: d.trapperUserPassword || null,
      project_id: d.trapperProjectId.trim() ? Number(d.trapperProjectId) : null,
      download_workers: Number(d.trapperDownloadWorkers),
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
      sandbox_communities: orNull(d.zenodoSandboxCommunities),
      production_communities: orNull(d.zenodoProductionCommunities),
      sandbox_token: d.zenodoSandboxToken || null,
      production_token: d.zenodoProductionToken || null,
    },
    B2SHARE: {
      environment: d.b2shareEnvironment,
      sandbox_community_id: orNull(d.b2shareSandboxCommunityId),
      production_community_id: orNull(d.b2shareProductionCommunityId),
      sandbox_token: d.b2shareSandboxToken || null,
      production_token: d.b2shareProductionToken || null,
    },
    GBIF: {
      environment: d.gbifEnvironment,
      sandbox_publishing_organization_key: orNull(d.gbifSandboxPublishingOrganizationKey),
      production_publishing_organization_key: orNull(d.gbifProductionPublishingOrganizationKey),
      sandbox_installation_key: orNull(d.gbifSandboxInstallationKey),
      production_installation_key: orNull(d.gbifProductionInstallationKey),
      registry_language: orNull(d.gbifRegistryLanguage),
      sandbox_username: d.gbifSandboxUsername || null,
      sandbox_password: d.gbifSandboxPassword || null,
      production_username: d.gbifProductionUsername || null,
      production_password: d.gbifProductionPassword || null,
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
    PRODUCT: { organizations: d.organizations, authors: d.authors },
  }
}

// ── Layout pieces ───────────────────────────────────────────────────────

const LOG_LEVELS: { value: LogLevel; label: string; hint: string }[] = [
  { value: 'ERROR', label: 'Error', hint: 'Only what went wrong.' },
  { value: 'WARNING', label: 'Warning', hint: 'Also what may be wrong: retries, failed images…' },
  { value: 'INFO', label: 'Info', hint: 'Also what the app does: each download, upload, publication… started and finished.' },
  { value: 'DEBUG', label: 'Debug', hint: 'Everything: each image uploaded to the bucket, full tracebacks. Big logs — for tracking a problem down.' },
]

type SectionId = 'config' | 'general' | 'trapper' | 'products' | 'repositories' | 's3' | 'product' | 'authors'
type RepoId = 'hfh' | 'zenodo' | 'b2share' | 'gbif'

const SECTIONS: { id: SectionId; label: string; icon: () => ReactNode }[] = [
  { id: 'general', label: 'General', icon: SlidersIcon },
  { id: 'trapper', label: 'Trapper', icon: CameraIcon },
  { id: 'products', label: 'Products', icon: PackageIcon },
  { id: 'repositories', label: 'Repositories', icon: LayersIcon },
  { id: 's3', label: 'S3 image hosting', icon: CloudIcon },
  { id: 'product', label: 'Organizations', icon: BuildingIcon },
  { id: 'authors', label: 'Authors', icon: UserIcon },
  { id: 'config', label: 'Config', icon: FileIcon },
]

const REPOS: { id: RepoId; label: string; icon: () => ReactNode }[] = [
  { id: 'hfh', label: 'HuggingFace Hub', icon: BoxesIcon },
  { id: 'zenodo', label: 'Zenodo', icon: BookIcon },
  { id: 'b2share', label: 'B2SHARE', icon: DatabaseIcon },
  { id: 'gbif', label: 'GBIF', icon: GlobeIcon },
]

function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: React.ReactNode }) {
  return (
    <div>
      <label className={[
        'block rounded-xl px-4 py-2 bg-zinc-100 dark:bg-zinc-800 border transition-colors focus-within:border-blue-500',
        error ? 'border-red-500' : 'border-transparent',
      ].join(' ')}>
        <span className="block text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
        {children}
      </label>
      {error ? <p className="text-xs text-red-600 dark:text-red-400 mt-1 px-1">{error}</p> : hint ? <p className={`${hintClass} px-1`}>{hint}</p> : null}
    </div>
  )
}

/** One setting: its name and what it does on the left, its controls on the
 * right — stacked on narrow screens. */
function Row({ label, description, children }: { label: string; description?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[13rem_1fr] gap-x-10 gap-y-3 py-5">
      <div className="md:text-right">
        <div className="text-base text-zinc-800 dark:text-zinc-200">{label}</div>
        {description && <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 leading-relaxed">{description}</p>}
      </div>
      <div className="space-y-3 min-w-0">{children}</div>
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

/** The two tenacity knobs shared by TRAPPER and S3 (see common.retrying): filled
 * boxes stacked, each with its unit beside the value — like wildintel-zooniverse's. */
function RetryFields({ attempts, wait, onAttemptsChange, onWaitChange, attemptsLabel = 'Retry attempts' }: {
  attempts: string; wait: string; onAttemptsChange: (v: string) => void; onWaitChange: (v: string) => void; attemptsLabel?: string
}) {
  return (
    <>
      <Field label={attemptsLabel} error={retryAttemptsValid(attempts) ? null : 'A whole number, 1 or more.'}>
        <span className="flex items-baseline gap-2">
          <input
            className={inputClass} inputMode="numeric" value={attempts} aria-label={attemptsLabel}
            aria-invalid={!retryAttemptsValid(attempts)} onChange={(e) => onAttemptsChange(e.target.value)}
          />
          <span className="text-xs text-zinc-500 dark:text-zinc-400 shrink-0">including the first</span>
        </span>
      </Field>
      <Field label="Seconds between retries" error={retryWaitValid(wait) ? null : 'A number of seconds, 0 or more.'}>
        <span className="flex items-baseline gap-2">
          <input
            className={inputClass} inputMode="decimal" value={wait} aria-label="Seconds between retries"
            aria-invalid={!retryWaitValid(wait)} onChange={(e) => onWaitChange(e.target.value)}
          />
          <span className="text-xs text-zinc-500 dark:text-zinc-400 shrink-0">before the first retry</span>
        </span>
      </Field>
    </>
  )
}

// ── S3 remotes: a list of cards, each edited in a dialog ──────────────────

const iconBtn = 'w-10 h-10 shrink-0 flex items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors'

/** The modal every card's gear opens. */
function DialogShell({ label, title, onClose, children }: { label: string; title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        role="dialog" aria-modal="true" aria-label={label}
        className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h5 className="text-lg font-semibold">{title}</h5>
        {children}
      </div>
    </div>
  )
}

/** One entry of a card list: icon tile, name + subtitle, an optional badge, and the gear that edits it. */
function ItemCard({ icon, title, subtitle, badge, badgeOk, editLabel, onEdit }: {
  icon: ReactNode; title: string; subtitle: string; badge?: string; badgeOk?: boolean; editLabel: string; onEdit: () => void
}) {
  return (
    <div className="flex items-center gap-4 px-4 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800">
      <span className="w-10 h-10 shrink-0 flex items-center justify-center rounded-full bg-zinc-200 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-300" aria-hidden="true">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-base truncate">{title}</p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate">{subtitle}</p>
      </div>
      {badge && (
        <span className={`text-xs px-2 py-0.5 rounded-full ${badgeOk ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'}`}>
          {badge}
        </span>
      )}
      <button type="button" className={iconBtn} aria-label={editLabel} title="Edit" onClick={onEdit}><GearIcon /></button>
    </div>
  )
}

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
    <DialogShell label="S3 remote" title={remote.name.trim() || 'New remote'} onClose={onClose}>
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
          <button type="button" className={btnDanger} onClick={onRemove}>Remove remote</button>
          <button type="button" className={btnPrimary} disabled={!remote.name.trim()} onClick={onClose}>Done</button>
        </div>
    </DialogShell>
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
      <div className="space-y-3">
        {items.length === 0 && <p className={hintClass}>No remote yet — the wizard can&rsquo;t upload images until you add one.</p>}
        {items.map((r) => (
          <ItemCard
            key={r.id} icon={<CloudIcon />} title={r.name} subtitle={remoteSubtitle(r)} editLabel={`Edit ${r.name}`}
            badge={(r.hasAccessKey || r.accessKey) && (r.hasSecretKey || r.secretKey) ? 'Credentials saved' : 'No credentials'}
            badgeOk={!!((r.hasAccessKey || r.accessKey) && (r.hasSecretKey || r.secretKey))}
            onEdit={() => setEditingId(r.id)}
          />
        ))}
        <button type="button" className={btnOutline} aria-label="Add remote" onClick={add}>+ Add remote</button>
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

function OrganizationDialog({ item, onChange, onRemove, onClose }: {
  item: Organization; onChange: (patch: Partial<Organization>) => void; onRemove: () => void; onClose: () => void
}) {
  return (
    <DialogShell label="Organization" title={item.title.trim() || 'New organization'} onClose={onClose}>
      <Field label="Title" error={item.title.trim() ? null : 'A title is required.'}>
        <input className={inputClass} value={item.title} aria-label="Title" onChange={(e) => onChange({ title: e.target.value })} />
      </Field>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <TextField label="Website" value={item.path ?? ''} onChange={(v) => onChange({ path: v || null })} />
        <TextField label="Contact email (publisher role only)" value={item.email ?? ''} onChange={(v) => onChange({ email: v || null })} />
        <TextField
          label="GBIF sandbox organization UUID" mono
          value={item.gbif_sandbox_organization_key ?? ''} onChange={(v) => onChange({ gbif_sandbox_organization_key: v || null })}
        />
        <TextField
          label="GBIF production organization UUID" mono
          value={item.gbif_production_organization_key ?? ''} onChange={(v) => onChange({ gbif_production_organization_key: v || null })}
        />
      </div>
      <div className="flex items-center justify-between pt-3 border-t border-zinc-200 dark:border-zinc-800">
        <button type="button" className={btnDanger} onClick={onRemove}>Remove organization</button>
        <button type="button" className={btnPrimary} disabled={!item.title.trim()} onClick={onClose}>Done</button>
      </div>
    </DialogShell>
  )
}

function OrganizationsEditor({ items, onChange }: { items: Organization[]; onChange: (v: Organization[]) => void }) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const editing = editingIndex !== null ? items[editingIndex] ?? null : null

  function add() {
    onChange([...items, { title: 'New organization', path: null, email: null, gbif_sandbox_organization_key: null, gbif_production_organization_key: null }])
    setEditingIndex(items.length)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <label className={`${labelClass} mb-0`}>Organizations</label>
        <button type="button" className={iconBtn} aria-label="Add organization" title="Add organization" onClick={add}>+</button>
      </div>
      <div className="space-y-3">
        {items.length === 0 && <p className={hintClass}>No organization yet — the wizard&rsquo;s metadata step needs at least one.</p>}
        {items.map((o, i) => {
          const linked = !!(o.gbif_sandbox_organization_key || o.gbif_production_organization_key)
          return (
            <ItemCard
              key={i} icon={<BuildingIcon />} title={o.title} subtitle={o.path || 'No website'} editLabel={`Edit ${o.title}`}
              badge={linked ? 'GBIF linked' : undefined} badgeOk onEdit={() => setEditingIndex(i)}
            />
          )
        })}
      </div>
      {editing && editingIndex !== null && (
        <OrganizationDialog
          item={editing}
          onChange={(patch) => onChange(items.map((o, i) => (i === editingIndex ? { ...o, ...patch } : o)))}
          onRemove={() => { onChange(items.filter((_, i) => i !== editingIndex)); setEditingIndex(null) }}
          onClose={() => setEditingIndex(null)}
        />
      )}
    </div>
  )
}

function AuthorDialog({ item, onChange, onRemove, onClose }: {
  item: ProductAuthor; onChange: (patch: Partial<ProductAuthor>) => void; onRemove: () => void; onClose: () => void
}) {
  const name = (item.name ?? '').trim()
  return (
    <DialogShell label="Author" title={name || 'New author'} onClose={onClose}>
      <Field label="Name" error={name ? null : 'A name is required.'}>
        <input className={inputClass} value={item.name ?? ''} aria-label="Name" onChange={(e) => onChange({ name: e.target.value })} />
      </Field>
      <TextField
        label="Affiliation" hint="Free text — separate several affiliations with “; ”."
        value={item.affiliation ?? ''} onChange={(v) => onChange({ affiliation: v || null })}
      />
      <div className="flex items-center justify-between pt-3 border-t border-zinc-200 dark:border-zinc-800">
        <button type="button" className={btnDanger} onClick={onRemove}>Remove author</button>
        <button type="button" className={btnPrimary} disabled={!name} onClick={onClose}>Done</button>
      </div>
    </DialogShell>
  )
}

function AuthorsEditor({ items, onChange }: { items: ProductAuthor[]; onChange: (v: ProductAuthor[]) => void }) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const editing = editingIndex !== null ? items[editingIndex] ?? null : null

  function add() {
    onChange([...items, { name: 'New author', affiliation: null }])
    setEditingIndex(items.length)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <label className={`${labelClass} mb-0`}>Authors</label>
        <button type="button" className={iconBtn} aria-label="Add author" title="Add author" onClick={add}>+</button>
      </div>
      <div className="space-y-3">
        {items.length === 0 && <p className={hintClass}>No author yet — the wizard&rsquo;s metadata step will have none to quick-add.</p>}
        {items.map((a, i) => (
          <ItemCard
            key={i} icon={<UserIcon />} title={a.name ?? ''} subtitle={a.affiliation || 'No affiliation'} editLabel={`Edit ${a.name}`}
            onEdit={() => setEditingIndex(i)}
          />
        ))}
      </div>
      {editing && editingIndex !== null && (
        <AuthorDialog
          item={editing}
          onChange={(patch) => onChange(items.map((a, i) => (i === editingIndex ? { ...a, ...patch } : a)))}
          onRemove={() => { onChange(items.filter((_, i) => i !== editingIndex)); setEditingIndex(null) }}
          onClose={() => setEditingIndex(null)}
        />
      )}
    </div>
  )
}

type UpdateState =
  | { kind: 'idle' } | { kind: 'checking' } | { kind: 'error'; message: string } | { kind: 'result'; check: VersionCheck }

/** One button that walks through the update check: "Check updates" → (if a newer
 * release exists) "Tap to download vX" → or "Tap to retry" when it couldn't tell. */
function UpdateCheck() {
  const [state, setState] = useState<UpdateState>({ kind: 'idle' })

  async function check() {
    setState({ kind: 'checking' })
    try {
      const result = await api.checkVersion()
      setState(result.error ? { kind: 'error', message: result.error } : { kind: 'result', check: result })
    } catch (e) {
      setState({ kind: 'error', message: e instanceof Error ? e.message : 'Could not check for updates.' })
    }
  }

  const buttonClass = `${btnOutline} w-full`
  const check_ = state.kind === 'result' ? state.check : null
  return (
    <>
      <div className="space-y-1.5">
        {check_?.update_available ? (
          <a href={check_.download_url ?? check_.release_url ?? '#'} target="_blank" rel="noreferrer" className={`${buttonClass} no-underline`}>
            Tap to download {check_.latest}
          </a>
        ) : (
          <button type="button" className={buttonClass} disabled={state.kind === 'checking'} onClick={check}>
            {state.kind === 'checking' ? 'Checking…' : state.kind === 'error' ? 'Tap to retry' : 'Check updates'}
          </button>
        )}
        {state.kind === 'error' && <p className="text-xs text-red-600 dark:text-red-400">{state.message}</p>}
        {check_ && !check_.update_available && (
          <p className="text-xs text-emerald-700 dark:text-emerald-400" role="status">
            {check_.current === 'dev' ? 'This is a development build — updates aren’t checked.' : `You’re up to date (version ${check_.current}).`}
          </p>
        )}
        {check_?.update_available && (
          <p className={hintClass} role="status">Version {check_.latest} is available — you have {check_.current}.</p>
        )}
      </div>
    </>
  )
}

function ConfigsEditor({ onSwitched, onError }: { onSwitched: () => void; onError: (message: string) => void }) {
  const [configs, setConfigs] = useState<ConfigInfo[] | null>(null)
  const [adding, setAdding] = useState<{ name: string; error?: string } | null>(null)
  const fail = (e: unknown, fallback: string) => onError(e instanceof Error ? e.message : fallback)

  useEffect(() => {
    api.configs().then(setConfigs).catch((e) => fail(e, 'Could not load the configs.'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function create() {
    if (!adding?.name.trim()) return
    try {
      setConfigs(await api.addConfig(adding.name))
      setAdding(null)
    } catch (e) {
      setAdding({ ...adding, error: e instanceof Error ? e.message : 'Could not create the config.' })
    }
  }

  async function activate(id: string) {
    try {
      setConfigs(await api.activateConfig(id))
      onSwitched()
    } catch (e) {
      fail(e, 'Could not switch config.')
    }
  }

  return (
    <div>
      <p className={`${hintClass} mb-4`}>
        Each config is a settings file; the active one is what the app reads and saves. A new one starts from the
        default values. Keep in mind these files hold your tokens and passwords as plain text.
      </p>
      <div className="flex items-center justify-between mb-3">
        <label className={`${labelClass} mb-0`}>Config</label>
        <button type="button" className={iconBtn} aria-label="Add config" title="Add a config with the default values" onClick={() => setAdding({ name: '' })}>+</button>
      </div>
      <div className="space-y-3">
        {configs?.map((c, i) => (
          <div
            key={c.id}
            className={`flex items-center gap-4 px-4 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 border ${c.active ? 'border-blue-500' : 'border-transparent'}`}
          >
            <span className="w-10 h-10 flex items-center justify-center rounded-full bg-zinc-200 dark:bg-zinc-700 text-sm font-semibold shrink-0" aria-hidden="true">#{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-base truncate">{c.name}</p>
                {c.active && <span className="text-xs px-2 py-0.5 rounded-full bg-blue-600 text-white">ACTIVE</span>}
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 font-mono break-all" aria-label={`${c.name} file location`}>{c.path}</p>
            </div>
            {!c.active && <button type="button" className={btnOutline} aria-label={`Activate ${c.name}`} onClick={() => activate(c.id)}>Activate</button>}
            <button
              type="button" className={iconBtn} aria-label={`Open ${c.name} folder`} title="Open the folder containing the config file"
              onClick={() => api.openConfigFolder(c.id).catch((e) => fail(e, 'Could not open the folder.'))}
            >
              <FolderIcon />
            </button>
            <a
              href={`/api/settings/configs/${encodeURIComponent(c.id)}/download`} download
              aria-label={`Download ${c.name}`} title="Download the config file" className={iconBtn}
            >
              <DownloadIcon />
            </a>
          </div>
        ))}
      </div>
      {adding && (
        <DialogShell label="New config" title="New config" onClose={() => setAdding(null)}>
          <Field label="Name" error={adding.error ?? null} hint="It names the file, so keep it short.">
            <input
              className={inputClass} aria-label="Config name" autoFocus value={adding.name}
              onChange={(e) => setAdding({ name: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') create() }}
            />
          </Field>
          <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-200 dark:border-zinc-800">
            <button type="button" className={btnOutline} onClick={() => setAdding(null)}>Cancel</button>
            <button type="button" className={btnPrimary} disabled={!adding.name.trim()} onClick={create}>Create</button>
          </div>
        </DialogShell>
      )}
    </div>
  )
}

/** Badge of a repository with one credential per environment. */
function tokensBadge(sandbox: boolean, production: boolean): { badge: string; ok: boolean } {
  if (sandbox && production) return { badge: 'Sandbox + production saved', ok: true }
  if (sandbox) return { badge: 'Sandbox saved', ok: true }
  if (production) return { badge: 'Production saved', ok: true }
  return { badge: 'No credentials', ok: false }
}

/** One column of a per-environment dialog (sandbox | production). */
function EnvironmentColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="space-y-4 rounded-lg border border-border p-4">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      {children}
    </fieldset>
  )
}

/** What a repository's card shows: where it points, and whether its credentials are saved. */
function repoSummary(id: RepoId, d: Draft, saved: AppSettings): { subtitle: string; badge: string; ok: boolean } {
  const env = (e: Environment) => (e === 'production' ? 'Production' : 'Sandbox')
  switch (id) {
    case 'hfh': {
      const ok = saved.HFH.has_token || !!d.hfhToken
      return { subtitle: d.hfhRepoId || d.hfhUsername || 'No default repo', badge: ok ? 'Token saved' : 'No token', ok }
    }
    case 'zenodo': {
      const ok = tokensBadge(saved.ZENODO.has_sandbox_token || !!d.zenodoSandboxToken, saved.ZENODO.has_production_token || !!d.zenodoProductionToken)
      return { subtitle: `Default: ${env(d.zenodoEnvironment)}`, ...ok }
    }
    case 'b2share': {
      const ok = tokensBadge(saved.B2SHARE.has_sandbox_token || !!d.b2shareSandboxToken, saved.B2SHARE.has_production_token || !!d.b2shareProductionToken)
      return { subtitle: `Default: ${env(d.b2shareEnvironment)}`, ...ok }
    }
    case 'gbif': {
      const ok = tokensBadge(
        (saved.GBIF.has_sandbox_username || !!d.gbifSandboxUsername) && (saved.GBIF.has_sandbox_password || !!d.gbifSandboxPassword),
        (saved.GBIF.has_production_username || !!d.gbifProductionUsername) && (saved.GBIF.has_production_password || !!d.gbifProductionPassword),
      )
      return { subtitle: `Default: ${env(d.gbifEnvironment)}`, ...ok }
    }
  }
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
  const [repoDialog, setRepoDialog] = useState<RepoId | null>(null)
  const [productDialog, setProductDialog] = useState<'camtrapdp' | null>(null)
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

  // Also called after switching config, which discards whatever wasn't saved.
  function reloadSettings() {
    api.getSettings()
      .then((s) => { setSaved(s); setDraft(toDraft(s)); setStatus({ kind: 'idle' }) })
      .catch((e) => setStatus({ kind: 'error', message: e instanceof Error ? e.message : 'Could not load the settings.' }))
  }

  useEffect(reloadSettings, [])

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
          <BackIcon />Back
        </button>
        <ul className="flex md:flex-col gap-2 overflow-x-auto">
          {SECTIONS.map(({ id, label, icon: SectionIcon }) => {
            const active = id === section
            return (
              <li key={id} className="shrink-0">
                <button
                  type="button" onClick={() => setSection(id)} aria-current={active ? 'page' : undefined}
                  className={[
                    'w-full flex items-center gap-3 px-4 py-3 rounded-xl text-base transition-colors',
                    active ? 'bg-blue-600 text-white' : 'text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800',
                  ].join(' ')}
                >
                  <SectionIcon />
                  <span>{label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* Section */}
      <div className="flex-1 min-w-0">
        <h4 className="text-2xl font-semibold mb-2">{current.label}</h4>

        {!draft && status.kind !== 'error' && <p className="text-sm text-zinc-500 dark:text-zinc-400 py-5">Loading…</p>}

        {draft && saved && section === 'trapper' && (
          <div className="divide-y divide-zinc-200/60 dark:divide-zinc-800/60">
            <Row label="Server" description="The Trapper instance the datasets are fetched from.">
              <TextField label="URL" value={draft.trapperUrl} onChange={(v) => set('trapperUrl', v)} mono />
            </Row>
            <Row
              label="Account"
              description={`${passwordHint(saved.TRAPPER.has_user_name, 'username')} ${passwordHint(saved.TRAPPER.has_user_password, 'password')} Leave a field blank to keep it.`}
            >
              <TextField label="Username" value={draft.trapperUserName} onChange={(v) => set('trapperUserName', v)} />
              <TextField label="Password" type="password" value={draft.trapperUserPassword} onChange={(v) => set('trapperUserPassword', v)} />
            </Row>
            <Row label="Classification project" description="The project a Camtrap DP is fetched from when none is given.">
              <Field label="Default classification project id" error={projectIdValid(draft.trapperProjectId) ? null : 'A whole number, or blank.'}>
                <input
                  className={inputClass} inputMode="numeric" value={draft.trapperProjectId} aria-label="Default classification project id"
                  onChange={(e) => set('trapperProjectId', e.target.value)}
                />
              </Field>
            </Row>
            <Row label="Downloads" description="How images are downloaded from Trapper, and how a call to it is retried. Each retry waits twice as long as the one before.">
              <Field
                label="Parallel downloads"
                error={downloadWorkersValid(draft.trapperDownloadWorkers) ? null : `A whole number from 1 to ${MAX_DOWNLOAD_WORKERS}.`}
              >
                <span className="flex items-baseline gap-2">
                  <input
                    className={inputClass} inputMode="numeric" value={draft.trapperDownloadWorkers} aria-label="Parallel downloads"
                    aria-invalid={!downloadWorkersValid(draft.trapperDownloadWorkers)}
                    onChange={(e) => set('trapperDownloadWorkers', e.target.value)}
                  />
                  <span className="text-xs text-zinc-500 dark:text-zinc-400 shrink-0">at once</span>
                </span>
              </Field>
              <RetryFields
                attempts={draft.trapperRetryAttempts} wait={draft.trapperRetryWaitSeconds} attemptsLabel="Attempts per call"
                onAttemptsChange={(v) => set('trapperRetryAttempts', v)} onWaitChange={(v) => set('trapperRetryWaitSeconds', v)}
              />
            </Row>
          </div>
        )}

        {draft && saved && section === 'products' && (
          <div className="space-y-3">
            <p className={hintClass}>Defaults for each kind of product the wizard publishes.</p>
            <ItemCard
              icon={<CameraIcon />} title="Camtrap DP" editLabel="Edit Camtrap DP"
              subtitle={[draft.camtrapdpDatasetName, draft.camtrapdpLicenseId].filter(Boolean).join(' · ') || 'No defaults set'}
              onEdit={() => setProductDialog('camtrapdp')}
            />
            {productDialog === 'camtrapdp' && (
              <DialogShell label="Camtrap DP" title="Camtrap DP" onClose={() => setProductDialog(null)}>
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
                <div className="flex justify-end pt-3 border-t border-zinc-200 dark:border-zinc-800">
                  <button type="button" className={btnPrimary} onClick={() => setProductDialog(null)}>Done</button>
                </div>
              </DialogShell>
            )}
          </div>
        )}

        {draft && saved && section === 'general' && (
          <div className="divide-y divide-zinc-200/60 dark:divide-zinc-800/60">
            <Row label="Update" description="Looks for a newer version of the app.">
              <UpdateCheck />
            </Row>
            <Row
              label="Log level"
              description="How much the app writes to its log — raise it to Debug to track a problem down, then lower it again. Applied as soon as it's saved."
            >
              <Field label="Level">
                <select className={inputClass} value={draft.logLevel} aria-label="Log level" onChange={(e) => set('logLevel', e.target.value as LogLevel)}>
                  {LOG_LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
              </Field>
              <p className={`${hintClass} px-1`}>{LOG_LEVELS.find((l) => l.value === draft.logLevel)?.hint}</p>
              {saved.GENERAL.log_level_override && (
                <p className="text-xs text-amber-700 dark:text-amber-400 px-1">
                  The environment variable <span className="font-mono">WILDINTEL_PUBLISHER_LOG_LEVEL</span> sets it
                  to <strong>{saved.GENERAL.log_level_override}</strong> for now — it wins over this setting.
                </p>
              )}
            </Row>
            <Row label="Log file" description="Rotated at 5 MB, keeping the last 5. Attach it to a bug report.">
              <Field label="Location">
                <span className="block font-mono text-sm text-zinc-900 dark:text-zinc-100 break-all py-0.5" aria-label="Log file location">{saved.GENERAL.log_file}</span>
              </Field>
              <div className="flex flex-wrap gap-2">
                <a href="/api/settings/log" download className={btnOutline}>Download log</a>
                {clearLog.kind !== 'confirming' && (
                  <button
                    type="button" className={btnDanger} disabled={clearLog.kind === 'clearing'}
                    onClick={() => setClearLog({ kind: 'confirming' })}
                  >
                    {clearLog.kind === 'clearing' ? 'Clearing…' : 'Clear log'}
                  </button>
                )}
              </div>
              {clearLog.kind === 'confirming' && (
                <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-3 text-sm text-zinc-700 dark:text-zinc-300">
                  <p>Delete the log file and its older copies? This can&rsquo;t be undone — download it first if you need it.</p>
                  <div className="flex gap-2 mt-2">
                    <button type="button" onClick={handleClearLog} className="px-4 py-1.5 text-sm rounded-xl bg-red-600 text-white hover:bg-red-700 transition-colors">Yes, clear it</button>
                    <button type="button" className={btnOutline} onClick={() => setClearLog({ kind: 'idle' })}>Cancel</button>
                  </div>
                </div>
              )}
              {clearLog.kind === 'cleared' && <p className="text-xs text-emerald-700 dark:text-emerald-400 px-1">Log cleared — a new one starts now.</p>}
              {clearLog.kind === 'error' && <p className="text-xs text-red-600 dark:text-red-400 px-1">{clearLog.message}</p>}
            </Row>
          </div>
        )}

        {draft && saved && section === 'repositories' && (
          <div className="space-y-3">
            <p className={hintClass}>Credentials and defaults of the repositories the wizard publishes to.</p>
            {REPOS.map(({ id, label, icon: RepoIcon }) => {
              const summary = repoSummary(id, draft, saved)
              return (
                <ItemCard
                  key={id} icon={<RepoIcon />} title={label} subtitle={summary.subtitle} editLabel={`Edit ${label}`}
                  badge={summary.badge} badgeOk={summary.ok} onEdit={() => setRepoDialog(id)}
                />
              )
            })}
            {repoDialog && (
              <DialogShell label={REPOS.find((r) => r.id === repoDialog)!.label} title={REPOS.find((r) => r.id === repoDialog)!.label} onClose={() => setRepoDialog(null)}>
                {repoDialog === 'hfh' && (
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
                {repoDialog === 'zenodo' && (
          <div className="space-y-4">
            <EnvironmentField label="Default environment" value={draft.zenodoEnvironment} onChange={(v) => set('zenodoEnvironment', v)} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <EnvironmentColumn title="Sandbox">
                <TextField label="Sandbox access token" type="password" value={draft.zenodoSandboxToken} onChange={(v) => set('zenodoSandboxToken', v)} hint={passwordHint(saved.ZENODO.has_sandbox_token, 'token')} />
                <TextField label="Sandbox communities" value={draft.zenodoSandboxCommunities} onChange={(v) => set('zenodoSandboxCommunities', v)} hint="Comma-separated." />
              </EnvironmentColumn>
              <EnvironmentColumn title="Production">
                <TextField label="Production access token" type="password" value={draft.zenodoProductionToken} onChange={(v) => set('zenodoProductionToken', v)} hint={passwordHint(saved.ZENODO.has_production_token, 'token')} />
                <TextField label="Production communities" value={draft.zenodoProductionCommunities} onChange={(v) => set('zenodoProductionCommunities', v)} hint="Comma-separated, e.g. wildintelproject." />
              </EnvironmentColumn>
            </div>
          </div>
        )}
                {repoDialog === 'b2share' && (
          <div className="space-y-4">
            <EnvironmentField label="Default environment" value={draft.b2shareEnvironment} onChange={(v) => set('b2shareEnvironment', v)} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <EnvironmentColumn title="Sandbox">
                <TextField label="Sandbox access token" type="password" value={draft.b2shareSandboxToken} onChange={(v) => set('b2shareSandboxToken', v)} hint={passwordHint(saved.B2SHARE.has_sandbox_token, 'token')} />
                <TextField label="Sandbox community UUID" value={draft.b2shareSandboxCommunityId} onChange={(v) => set('b2shareSandboxCommunityId', v)} mono />
              </EnvironmentColumn>
              <EnvironmentColumn title="Production">
                <TextField label="Production access token" type="password" value={draft.b2shareProductionToken} onChange={(v) => set('b2shareProductionToken', v)} hint={passwordHint(saved.B2SHARE.has_production_token, 'token')} />
                <TextField label="Production community UUID" value={draft.b2shareProductionCommunityId} onChange={(v) => set('b2shareProductionCommunityId', v)} mono />
              </EnvironmentColumn>
            </div>
          </div>
        )}
                {repoDialog === 'gbif' && (
          <div className="space-y-4">
            <EnvironmentField label="Default environment" value={draft.gbifEnvironment} onChange={(v) => set('gbifEnvironment', v)} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <EnvironmentColumn title="Sandbox (gbif-test.org)">
                <TextField label="Sandbox username" value={draft.gbifSandboxUsername} onChange={(v) => set('gbifSandboxUsername', v)} hint={passwordHint(saved.GBIF.has_sandbox_username, 'username')} />
                <TextField label="Sandbox password" type="password" value={draft.gbifSandboxPassword} onChange={(v) => set('gbifSandboxPassword', v)} hint={passwordHint(saved.GBIF.has_sandbox_password, 'password')} />
                <TextField label="Sandbox publishing organization UUID" value={draft.gbifSandboxPublishingOrganizationKey} onChange={(v) => set('gbifSandboxPublishingOrganizationKey', v)} mono />
                <TextField label="Sandbox installation UUID" value={draft.gbifSandboxInstallationKey} onChange={(v) => set('gbifSandboxInstallationKey', v)} mono />
              </EnvironmentColumn>
              <EnvironmentColumn title="Production (gbif.org)">
                <TextField label="Production username" value={draft.gbifProductionUsername} onChange={(v) => set('gbifProductionUsername', v)} hint={passwordHint(saved.GBIF.has_production_username, 'username')} />
                <TextField label="Production password" type="password" value={draft.gbifProductionPassword} onChange={(v) => set('gbifProductionPassword', v)} hint={passwordHint(saved.GBIF.has_production_password, 'password')} />
                <TextField label="Production publishing organization UUID" value={draft.gbifProductionPublishingOrganizationKey} onChange={(v) => set('gbifProductionPublishingOrganizationKey', v)} mono />
                <TextField label="Production installation UUID" value={draft.gbifProductionInstallationKey} onChange={(v) => set('gbifProductionInstallationKey', v)} mono />
              </EnvironmentColumn>
            </div>
            <TextField label="Registry language (ISO 639-2/T)" value={draft.gbifRegistryLanguage} onChange={(v) => set('gbifRegistryLanguage', v)} />
            <div>
              <label className={labelClass}>Selectable installations</label>
              <p className={`${hintClass} mb-2`}>Offered as GBIFPublishForm&rsquo;s own &ldquo;Installation UUID&rdquo; quick-fill dropdown.</p>
              <InstallationsEditor items={draft.gbifInstallations} onChange={(v) => set('gbifInstallations', v)} />
            </div>
          </div>
        )}
                <div className="flex justify-end pt-3 border-t border-zinc-200 dark:border-zinc-800">
                  <button type="button" className={btnPrimary} onClick={() => setRepoDialog(null)}>Done</button>
                </div>
              </DialogShell>
            )}
          </div>
        )}

        {draft && saved && section === 's3' && (
          <div className="divide-y divide-zinc-200/60 dark:divide-zinc-800/60">
            <Row
              label="Remotes"
              description={<>
                S3-compatible buckets (AWS S3, MinIO, or any other provider speaking the same API) the wizard offers to
                upload a Camtrap DP&rsquo;s own images to, right after its metadata step and before you choose where
                to publish — once done, media.csv&rsquo;s own filePath points at these public URLs instead of local files.
                Pick which remote to use in the wizard.
              </>}
            >
              <S3RemotesEditor items={draft.s3Remotes} onChange={(v) => set('s3Remotes', v)} />
            </Row>
            <Row label="Transfers" description="How each image is fetched from its source and uploaded to the bucket. Each retry waits twice as long as the one before.">
              <RetryFields
                attempts={draft.s3RetryAttempts} wait={draft.s3RetryWaitSeconds} attemptsLabel="Attempts per transfer"
                onAttemptsChange={(v) => set('s3RetryAttempts', v)} onWaitChange={(v) => set('s3RetryWaitSeconds', v)}
              />
            </Row>
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

        {section === 'config' && (
          <ConfigsEditor onSwitched={reloadSettings} onError={(message) => setStatus({ kind: 'error', message })} />
        )}

        {draft && saved && section === 'authors' && (
          <div className="space-y-4">
            <p className={hintClass}>
              Authors the wizard&rsquo;s metadata step can add to a dataset with one click (they stay editable there).
            </p>
            <AuthorsEditor items={draft.authors} onChange={(v) => set('authors', v)} />
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
