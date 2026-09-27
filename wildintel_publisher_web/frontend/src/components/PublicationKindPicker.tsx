import { useEffect, useState } from 'react'
import { api } from '../api'
import type { FoundRecord, PreviousVersion, Publication, PublicationKind } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const selectClass = 'px-2 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnOutline = 'px-3 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap'

export type LookupRepo = 'hfh' | 'zenodo' | 'b2share' | 'gbif'

const LOOKUP_LABELS: Record<LookupRepo, { label: string; placeholder: string }> = {
  hfh: { label: 'Hugging Face Hub dataset', placeholder: 'owner/name, or its URL' },
  zenodo: { label: 'Zenodo record', placeholder: 'Record id, URL or DOI' },
  b2share: { label: 'B2SHARE record', placeholder: 'Record id, URL or DOI' },
  gbif: { label: 'GBIF dataset', placeholder: 'Dataset key (UUID), URL or DOI' },
}

type Environment = 'sandbox' | 'production'

interface Published {
  id: string
  title: string
  /** The highest version published (none for GBIF, whose datasets have no
   * versions of their own). */
  version?: string | null
  /** When its latest version was published (YYYY-MM-DD). */
  published?: string | null
}

type SortOrder = 'published' | 'title'

/** Newest first for 'published' (undated ones last); A–Z for 'title'. */
function sortPublished(items: Published[], order: SortOrder): Published[] {
  return [...items].sort((a, b) => (order === 'title'
    ? a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
    : (b.published ?? '').localeCompare(a.published ?? '')))
}

/** The identifier the lookup gets for an item picked from a list: its URL,
 * so the environment it lives on is never guessed. */
function identifierFor(repo: LookupRepo, environment: Environment, id: string): string {
  const sandbox = environment === 'sandbox'
  switch (repo) {
    case 'hfh': return id
    case 'zenodo': return `https://${sandbox ? 'sandbox.zenodo.org' : 'zenodo.org'}/records/${id}`
    case 'b2share': return `https://${sandbox ? 'trng-b2share.eudat.eu' : 'b2share.eudat.eu'}/records/${id}`
    case 'gbif': return sandbox ? `https://registry.gbif-test.org/dataset/${id}` : `https://www.gbif.org/dataset/${id}`
  }
}

/** Where to see a published item on the repository's own website. */
function pageUrlFor(repo: LookupRepo, environment: Environment, id: string): string {
  return repo === 'hfh' ? `https://huggingface.co/datasets/${id}` : identifierFor(repo, environment, id)
}

/** Everything already published to `repo` with the saved credentials —
 * the same searches each repository's own form offers (Zenodo/B2SHARE: the
 * token's own; GBIF: the configured publishing organization's; HFH: the
 * token's user and organizations). */
async function listPublished(repo: LookupRepo, environment: Environment, gbifOrganizationKey: string | null): Promise<Published[]> {
  switch (repo) {
    case 'hfh': return api.hfhDatasets()
    case 'zenodo': return api.zenodoDepositions(environment, '')
    case 'b2share': return api.b2shareRecords(environment, '')
    case 'gbif': {
      if (!gbifOrganizationKey) {
        throw new Error('No GBIF publishing organization is configured yet — type the dataset\'s key or URL instead.')
      }
      const datasets = await api.gbifOrganizationDatasets(gbifOrganizationKey, environment)
      return datasets.map((d) => ({ id: d.key, title: d.title, published: d.published }))
    }
  }
}

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-400 border-t-transparent rounded-full animate-spin" />
}

interface Props {
  value: Publication | null
  onChange: (value: Publication | null) => void
  /** The repositories this product type can publish to that can be looked
   * up (see REPOS_BY_PRODUCT_TYPE) — the first one is the default. */
  repos: LookupRepo[]
}

function RecordRow({ label, record }: { label: string; record: FoundRecord }) {
  return (
    <>
      <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="text-zinc-800 dark:text-zinc-200">
        <a href={record.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline font-mono">
          {record.record_id}
        </a>
        {record.environment === 'sandbox' && <span className="text-zinc-500"> (sandbox)</span>}
        {record.version && <span className="text-zinc-500"> · version {record.version}</span>}
      </dd>
    </>
  )
}

/** Asked at the very start of the metadata step: is this a brand new
 * dataset, or a new version of one already published? For a new version,
 * one identifier from any repository is enough to find the rest (see
 * services.previous_version_service) — what's found then pre-fills every
 * repository's form, and the version number to publish. */
export default function PublicationKindPicker({ value, onChange, repos }: Props) {
  const [repo, setRepo] = useState<LookupRepo>(repos[0] ?? 'zenodo')
  const [identifier, setIdentifier] = useState('')
  const [lookup, setLookup] = useState<{ status: 'idle' | 'loading' | 'error'; message: string }>({ status: 'idle', message: '' })
  // Zenodo/B2SHARE/GBIF's own environment to list from — defaults to each
  // one's saved configuration (see the effect below).
  const [environment, setEnvironment] = useState<Environment>('sandbox')
  const [gbifOrganizationKey, setGbifOrganizationKey] = useState<string | null>(null)
  // Narrows the "List what I published here" results as the user types.
  const [filter, setFilter] = useState('')
  const [sortOrder, setSortOrder] = useState<SortOrder>('published')
  const [published, setPublished] = useState<{ status: 'idle' | 'loading' | 'ok' | 'error'; message: string; items: Published[] }>(
    { status: 'idle', message: '', items: [] },
  )

  useEffect(() => {
    setPublished({ status: 'idle', message: '', items: [] })
    const config = repo === 'zenodo' ? api.zenodoGetConfig()
      : repo === 'b2share' ? api.b2shareGetConfig()
        : repo === 'gbif' ? api.gbifGetConfig()
          : null
    config?.then((c) => {
      if (c.environment === 'sandbox' || c.environment === 'production') setEnvironment(c.environment)
      if ('publishing_organization_key' in c) setGbifOrganizationKey(c.publishing_organization_key ?? null)
    }).catch(() => { /* keep the defaults */ })
  }, [repo])

  async function handleListPublished() {
    setFilter('')
    setPublished({ status: 'loading', message: '', items: [] })
    try {
      const items = await listPublished(repo, environment, gbifOrganizationKey)
      setPublished({ status: 'ok', message: items.length === 0 ? 'Nothing published here yet.' : '', items })
    } catch (e) {
      setPublished({ status: 'error', message: e instanceof Error ? e.message : 'Could not list what you published.', items: [] })
    }
  }

  const needle = filter.trim().toLowerCase()
  const shownItems = sortPublished(
    needle
      ? published.items.filter((item) => [item.title, item.id, item.version ?? ''].some((v) => v.toLowerCase().includes(needle)))
      : published.items,
    sortOrder,
  )

  function handlePick(item: Published) {
    const picked = identifierFor(repo, environment, item.id)
    setIdentifier(picked)
    setPublished({ status: 'idle', message: '', items: [] })
    void handleFind(picked)
  }
  const previous: PreviousVersion | null = value?.previous ?? null

  function choose(kind: PublicationKind) {
    onChange(kind === 'new' ? { kind, previous: null } : { kind, previous: value?.kind === 'version' ? value.previous : null })
  }

  async function handleFind(value: string = identifier) {
    setLookup({ status: 'loading', message: '' })
    onChange({ kind: 'version', previous: null })
    try {
      const found = await api.previousVersion(repo, value.trim())
      onChange({ kind: 'version', previous: found })
      setLookup({ status: 'idle', message: '' })
    } catch (e) {
      setLookup({ status: 'error', message: e instanceof Error ? e.message : 'Could not find that dataset.' })
    }
  }

  return (
    <div className="mb-8">
      <h5 className="text-base font-semibold mb-2 text-zinc-800 dark:text-zinc-200">1. What are you publishing?</h5>
      <div className="flex flex-col gap-2">
        <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
          <input type="radio" name="publication-kind" className="mt-0.5" checked={value?.kind === 'new'} onChange={() => choose('new')} />
          <span><strong>A new dataset</strong> — never published before; every repository gets a brand new record.</span>
        </label>
        <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
          <input type="radio" name="publication-kind" className="mt-0.5" checked={value?.kind === 'version'} onChange={() => choose('version')} />
          <span>
            <strong>A new version of an already published dataset</strong> — every repository gets a new version,
            linked to the previous ones.
          </span>
        </label>
      </div>

      {value?.kind === 'version' && (
        <div className="mt-4 ml-6 p-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-3">
            Where is it published? Pick it from what you already published there, or type its identifier — one
            repository is enough, the others are found from it.
          </p>
          <div className="flex gap-2 flex-wrap sm:flex-nowrap">
            <select
              aria-label="Previous version repository" className={selectClass} value={repo}
              onChange={(e) => { setRepo(e.target.value as LookupRepo); onChange({ kind: 'version', previous: null }) }}
            >
              {repos.map((r) => <option key={r} value={r}>{LOOKUP_LABELS[r].label}</option>)}
            </select>
            <input
              aria-label="Previous version identifier" className={inputClass} placeholder={LOOKUP_LABELS[repo].placeholder}
              value={identifier}
              onChange={(e) => { setIdentifier(e.target.value); if (previous) onChange({ kind: 'version', previous: null }) }}
            />
            <button type="button" className={btnOutline} disabled={!identifier.trim() || lookup.status === 'loading'} onClick={() => handleFind()}>
              {lookup.status === 'loading' && <SmallSpinner />}
              {lookup.status === 'loading' ? 'Finding…' : 'Find'}
            </button>
          </div>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {repo !== 'hfh' && (
              <select
                aria-label="Previous version environment" className={selectClass} value={environment}
                onChange={(e) => { setEnvironment(e.target.value as Environment); setPublished({ status: 'idle', message: '', items: [] }) }}
              >
                <option value="sandbox">Sandbox</option>
                <option value="production">Production</option>
              </select>
            )}
            <button type="button" className={btnOutline} disabled={published.status === 'loading'} onClick={handleListPublished}>
              {published.status === 'loading' && <SmallSpinner />}
              {published.status === 'loading' ? 'Listing…' : 'List what I published here'}
            </button>
          </div>
          {published.status === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mt-1">{published.message}</p>}
          {published.status === 'ok' && published.message && <p className={hintClass}>{published.message}</p>}
          {published.status === 'ok' && published.items.length > 0 && (
            <div className="mt-2 flex items-center gap-2">
              <input
                aria-label="Filter published datasets" className={inputClass} placeholder="Filter by title, id or version"
                value={filter} onChange={(e) => setFilter(e.target.value)}
              />
              <select
                aria-label="Sort published datasets" className={selectClass} value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value as SortOrder)}
              >
                <option value="published">Newest first</option>
                <option value="title">Title (A–Z)</option>
              </select>
              <span className="text-xs text-zinc-500 dark:text-zinc-400 whitespace-nowrap">
                {shownItems.length === published.items.length ? `${published.items.length} found` : `${shownItems.length} of ${published.items.length}`}
              </span>
            </div>
          )}
          {published.status === 'ok' && published.items.length > 0 && shownItems.length === 0 && (
            <p className={hintClass}>Nothing matches “{filter}”.</p>
          )}
          {published.status === 'ok' && shownItems.length > 0 && (
            <ul className="mt-2 border border-zinc-300 dark:border-zinc-700 rounded divide-y divide-zinc-200 dark:divide-zinc-700 max-h-56 overflow-y-auto">
              {shownItems.map((item) => (
                <li key={item.id} className="flex items-stretch">
                  <button
                    type="button" onClick={() => handlePick(item)}
                    className="flex-1 min-w-0 text-left px-3 py-2 text-sm hover:bg-blue-50 dark:hover:bg-blue-950/30"
                  >
                    <div className="text-zinc-900 dark:text-zinc-100 truncate">{item.title}</div>
                    <div className="text-xs text-zinc-500 dark:text-zinc-400">
                      <span className="font-mono">{item.id}</span>
                      {item.version && <> · version <span className="font-mono">{item.version}</span></>}
                      {item.published && <> · published {item.published}</>}
                    </div>
                  </button>
                  <a
                    href={pageUrlFor(repo, environment, item.id)} target="_blank" rel="noreferrer"
                    aria-label={`Open ${item.title} in a new tab`} title="Open it on the repository's website"
                    className="flex items-center px-3 text-sm text-blue-600 dark:text-blue-400 hover:bg-zinc-100 dark:hover:bg-zinc-700 border-l border-zinc-200 dark:border-zinc-700 whitespace-nowrap"
                  >
                    Open ↗
                  </a>
                </li>
              ))}
            </ul>
          )}
          {lookup.status === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mt-2">{lookup.message}</p>}

          {previous && (
            <div className="mt-4">
              <p className="text-sm text-zinc-800 dark:text-zinc-200">
                <strong>{previous.title ?? 'Untitled dataset'}</strong>
                {previous.version && <> — last published version: <span className="font-mono">{previous.version}</span></>}
              </p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm mt-2">
                {previous.hfh && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">Hugging Face Hub</dt>
                    <dd>
                      <a href={previous.hfh.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline font-mono">
                        {previous.hfh.repo_id}
                      </a>
                      {previous.hfh.version && <span className="text-zinc-500"> · version {previous.hfh.version}</span>}
                    </dd>
                  </>
                )}
                {previous.zenodo && <RecordRow label="Zenodo" record={previous.zenodo} />}
                {previous.b2share && <RecordRow label="B2SHARE" record={previous.b2share} />}
                {previous.gbif && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">GBIF</dt>
                    <dd>
                      <a href={previous.gbif.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline font-mono">
                        {previous.gbif.dataset_key}
                      </a>
                      {previous.gbif.environment === 'sandbox' && <span className="text-zinc-500"> (sandbox)</span>}
                    </dd>
                  </>
                )}
              </dl>
              {previous.warnings.map((w, i) => (
                <p key={i} className="text-sm text-amber-600 dark:text-amber-400 mt-1">⚠ {w}</p>
              ))}
              <p className={hintClass}>
                Each repository's form will be pre-filled with these. A repository not listed here gets its first
                record for this dataset.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
