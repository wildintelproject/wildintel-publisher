import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AppSettings, AppSettingsUpdate, GBIFInstallation, Organization } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnPrimary = 'px-6 py-2.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
const btnOutline = 'px-3 py-1.5 text-sm border border-zinc-300 dark:border-zinc-600 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors'

// ── The form's own state ────────────────────────────────────────────────

type Environment = 'sandbox' | 'production'

/** Every scalar field as typed text/select; the two list fields
 * (GBIF.installations, PRODUCT.organizations) are kept as their own
 * structured arrays instead. */
interface Draft {
  trapperUrl: string
  trapperUserName: string
  trapperUserPassword: string
  trapperProjectId: string
  trapperLicenseId: string
  trapperLicenseName: string
  trapperLicenseUrl: string
  trapperDatasetSlug: string
  trapperDatasetName: string
  trapperDescription: string

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

  organizations: Organization[]
}

function toDraft(s: AppSettings): Draft {
  return {
    trapperUrl: s.TRAPPER.base_url ?? '',
    trapperUserName: '',
    trapperUserPassword: '',
    trapperProjectId: s.TRAPPER.project_id != null ? String(s.TRAPPER.project_id) : '',
    trapperLicenseId: s.TRAPPER.license_id ?? '',
    trapperLicenseName: s.TRAPPER.license_name ?? '',
    trapperLicenseUrl: s.TRAPPER.license_url ?? '',
    trapperDatasetSlug: s.TRAPPER.dataset_slug ?? '',
    trapperDatasetName: s.TRAPPER.dataset_name ?? '',
    trapperDescription: s.TRAPPER.description ?? '',

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

    organizations: s.PRODUCT.organizations,
  }
}

function orNull(v: string): string | null {
  return v.trim() ? v.trim() : null
}

function projectIdValid(v: string): boolean {
  return v.trim() === '' || /^\d+$/.test(v.trim())
}

function toUpdate(d: Draft): AppSettingsUpdate | null {
  if (!projectIdValid(d.trapperProjectId)) return null
  return {
    TRAPPER: {
      base_url: orNull(d.trapperUrl),
      user_name: d.trapperUserName || null,
      user_password: d.trapperUserPassword || null,
      project_id: d.trapperProjectId.trim() ? Number(d.trapperProjectId) : null,
      license_id: orNull(d.trapperLicenseId),
      license_name: orNull(d.trapperLicenseName),
      license_url: orNull(d.trapperLicenseUrl),
      dataset_slug: orNull(d.trapperDatasetSlug),
      dataset_name: orNull(d.trapperDatasetName),
      description: orNull(d.trapperDescription),
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
    PRODUCT: { organizations: d.organizations },
  }
}

// ── Layout pieces ───────────────────────────────────────────────────────

type SectionId = 'trapper' | 'hfh' | 'zenodo' | 'b2share' | 'gbif' | 'product'

const SECTIONS: { id: SectionId; label: string; icon: string }[] = [
  { id: 'trapper', label: 'Trapper', icon: '📷' },
  { id: 'hfh', label: 'HuggingFace Hub', icon: '🤗' },
  { id: 'zenodo', label: 'Zenodo', icon: '📚' },
  { id: 'b2share', label: 'B2SHARE', icon: '🗄️' },
  { id: 'gbif', label: 'GBIF', icon: '🌍' },
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
  const [section, setSection] = useState<SectionId>('trapper')
  const [saved, setSaved] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'saved' | 'error'; message?: string }>({ kind: 'idle' })

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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label="Dataset slug" value={draft.trapperDatasetSlug} onChange={(v) => set('trapperDatasetSlug', v)} hint="Short internal identifier — used to derive the dataset name below if left blank." />
              <TextField label="Dataset name" value={draft.trapperDatasetName} onChange={(v) => set('trapperDatasetName', v)} />
            </div>
            <TextField label="Description" value={draft.trapperDescription} onChange={(v) => set('trapperDescription', v)} />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <TextField label="License id" value={draft.trapperLicenseId} onChange={(v) => set('trapperLicenseId', v)} />
              <TextField label="License name" value={draft.trapperLicenseName} onChange={(v) => set('trapperLicenseName', v)} />
              <TextField label="License URL" value={draft.trapperLicenseUrl} onChange={(v) => set('trapperLicenseUrl', v)} mono />
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
