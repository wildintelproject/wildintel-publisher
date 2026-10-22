import { titlesUnrelated } from '../titles'
import Notice from './Notice'
import { useEffect, useState } from 'react'
import { api } from '../api'
import ChoiceCards from './ChoiceCards'
import type { PreviousVersion, Publication, PublicationKind } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const selectClass = 'px-2 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnOutline = 'px-3 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap'

export type LookupRepo = 'hfh' | 'zenodo' | 'b2share' | 'gbif'

const LOOKUP_LABELS: Record<LookupRepo, { name: string; placeholder: string; hint: string }> = {
  hfh: { name: 'Hugging Face Hub', placeholder: 'owner/name, or its URL', hint: 'Enter the dataset repository ID, e.g. organization/dataset-name.' },
  zenodo: { name: 'Zenodo', placeholder: 'Record id, URL or DOI', hint: 'Enter the record id, its URL or its DOI.' },
  b2share: { name: 'B2SHARE', placeholder: 'Record id, URL or DOI', hint: 'Enter the record id, its URL or its DOI.' },
  gbif: { name: 'GBIF', placeholder: 'Dataset key (UUID), URL or DOI', hint: 'Enter the dataset key (a UUID), its URL or its DOI.' },
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

/** Finds the publication a new version is a version of: one identifier from any repository is enough to find the rest
 * (see services.previous_version_service) — what is found pre-fills every repository's form, and the version number to publish. */
export function PreviousPublicationFinder({ value, onChange, repos, currentTitle }: Omit<Props, 'showHeading'> & {
  /** The title of the dataset being published, when it is already known — a warning is shown if it looks nothing like the previous one's. */
  currentTitle?: string | null
}) {
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

  const found: { label: string; id: string; url: string; version?: string | null; sandbox?: boolean }[] = []
  if (previous?.hfh) found.push({ label: 'Hugging Face Hub', id: previous.hfh.repo_id, url: previous.hfh.url, version: previous.hfh.version })
  if (previous?.zenodo) found.push({ label: 'Zenodo', id: `Record ${previous.zenodo.record_id}`, url: previous.zenodo.url, version: previous.zenodo.version, sandbox: previous.zenodo.environment === 'sandbox' })
  if (previous?.b2share) found.push({ label: 'B2SHARE', id: `Record ${previous.b2share.record_id}`, url: previous.b2share.url, version: previous.b2share.version, sandbox: previous.b2share.environment === 'sandbox' })
  if (previous?.gbif) found.push({ label: 'GBIF', id: `Dataset ${previous.gbif.dataset_key}`, url: previous.gbif.url, sandbox: previous.gbif.environment === 'sandbox' })

  return (
    <div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-5">
        Select a repository and provide the identifier of the previously published dataset. We will use it to identify
        the dataset and retrieve the associated records from other repositories.
      </p>

      <fieldset className="mb-5">
        <legend className="block text-sm font-semibold mb-2 text-zinc-700 dark:text-zinc-300">Repository</legend>
        <div role="radiogroup" aria-label="Previous version repository" className="flex flex-col gap-1">
          {repos.map((r) => (
            <label key={r} className="flex items-center gap-3 py-1.5 cursor-pointer text-base text-zinc-800 dark:text-zinc-200 focus-within:ring-2 focus-within:ring-blue-500/50 rounded">
              <input
                type="radio" name="previous-repository" className="sr-only" checked={repo === r}
                onChange={() => { setRepo(r); onChange({ kind: 'version', previous: null }) }}
              />
              <span aria-hidden="true" className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${repo === r ? 'border-blue-500 bg-blue-600' : 'border-zinc-400 dark:border-zinc-600'}`}>
                {repo === r && <span className="h-2 w-2 rounded-full bg-white" />}
              </span>
              {LOOKUP_LABELS[r].name}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mb-4">
        <label htmlFor="previous-identifier" className="block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300">Previous publication ID</label>
        <input
          id="previous-identifier" aria-label="Previous version identifier" className={`${inputClass} rounded-full px-4 py-2.5`}
          placeholder={LOOKUP_LABELS[repo].placeholder} value={identifier}
          onChange={(e) => { setIdentifier(e.target.value); if (previous) onChange({ kind: 'version', previous: null }) }}
        />
        <p className={hintClass}>{LOOKUP_LABELS[repo].hint}</p>
      </div>

      <div className="flex items-center gap-2 mb-3 flex-wrap">
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
      {published.status === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mb-2">{published.message}</p>}
      {published.status === 'ok' && published.message && <p className={hintClass}>{published.message}</p>}
      {published.status === 'ok' && published.items.length > 0 && (
        <div className="mb-2 flex items-center gap-2">
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
        <ul className="mb-3 border border-zinc-300 dark:border-zinc-700 rounded divide-y divide-zinc-200 dark:divide-zinc-700 max-h-56 overflow-y-auto">
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

      <button
        type="button" disabled={!identifier.trim() || lookup.status === 'loading'} onClick={() => handleFind()}
        className="w-full flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium bg-zinc-100 dark:bg-zinc-200 text-zinc-900 hover:bg-zinc-200 dark:hover:bg-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {lookup.status === 'loading' && <SmallSpinner />}
        {lookup.status === 'loading' ? 'Finding…' : 'Find previous publication'}
      </button>
      {lookup.status === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mt-3" role="alert">{lookup.message}</p>}

      {previous && (
        <section aria-label="Previous publication found" className="mt-6">
          <h5 className="flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6 shrink-0 fill-none stroke-emerald-500" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9.5" /><path d="M8 12.5l3 3 5-6" />
            </svg>
            Previous publication found
          </h5>
          <p className="mt-3 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{previous.title ?? 'Untitled dataset'}</p>
          {previous.version && <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">Last published version: <span className="font-mono">{previous.version}</span></p>}
          {previous.title && titlesUnrelated(currentTitle, previous.title) && (
            <Notice kind="warning" role="status" className="mt-3">
              This title looks nothing like the previous publication's («{previous.title}»). Check that this
              really is a new version of it.
            </Notice>
          )}
          <ul className="mt-3 rounded-xl border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-200 dark:divide-zinc-700">
            {found.map((f) => (
              <li key={f.label} className="flex items-start gap-3 px-4 py-3">
                <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 mt-0.5 shrink-0 fill-none stroke-current text-zinc-500 dark:text-zinc-400" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
                </svg>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-zinc-900 dark:text-zinc-100">{f.label}{f.sandbox && <span className="font-normal text-zinc-500"> (sandbox)</span>}</p>
                  <a href={f.url} target="_blank" rel="noreferrer" className="block text-sm text-blue-600 dark:text-blue-400 hover:underline font-mono break-all">{f.id}</a>
                  {f.version && <p className="text-sm text-zinc-600 dark:text-zinc-400">Version {f.version}</p>}
                </div>
                <span className="rounded-full px-2.5 py-0.5 text-xs font-medium bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400">Found</span>
              </li>
            ))}
          </ul>
          {previous.warnings.map((w, i) => (
            <p key={i} className="text-sm text-amber-600 dark:text-amber-400 mt-2">⚠ {w}</p>
          ))}
        </section>
      )}
    </div>
  )
}

/** Asked at the start of the metadata step: is this a brand new dataset, or a new version of one already published?
 * For a new version, the next step finds the previous publication (see PreviousPublicationFinder). */
export default function PublicationKindPicker({ value, onChange }: Pick<Props, 'value' | 'onChange'>) {
  return (
    <ChoiceCards
      name="publication-kind" label="What are you publishing?" value={value?.kind ?? null}
      onChoose={(kind: PublicationKind) => onChange(kind === 'new' ? { kind, previous: null } : { kind, previous: value?.kind === 'version' ? value.previous : null })}
      options={[
        { value: 'new', title: 'New dataset', description: 'This dataset has never been published. A new record will be created in each repository.' },
        { value: 'version', title: 'New version of an existing dataset', description: 'An update to a previously published dataset. Existing repository records will be linked to their new versions.' },
      ]}
    />
  )
}
