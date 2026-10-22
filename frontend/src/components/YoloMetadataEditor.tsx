import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Organization, ProductAuthor, ProductLicense, YoloDataYamlFields, YoloDataYamlMetadata } from '../types'
import { COMMON_LICENSES, findCommonLicense } from '../licenses'
import { isNewerVersion } from '../versions'
import Notice, { StatusIcon } from './Notice'
import SuggestInput from './SuggestInput'
import { authorIsBlank, authorIsInvalid, licenseIsInvalid, organizationPublisher } from '../yoloMetadata'

const inputClass = 'w-full px-3 py-2.5 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const invalidInputClass = 'w-full px-3 py-2.5 text-sm rounded-lg border border-red-500 dark:border-red-500 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1.5'
const OTHER_LICENSE = '__other__'
const btnOutline = 'px-3 py-2 text-sm border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
const iconBtn = 'w-9 h-9 flex items-center justify-center text-sm border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'

/** What a license lets others do, in a sentence — for the ones offered by the dropdown. */
const LICENSE_SUMMARIES: Record<string, string> = {
  'CC-BY-4.0': 'Others may share and adapt the data, as long as they credit you.',
  'CC-BY-NC-4.0': 'Others may share and adapt the data for non-commercial purposes, as long as they credit you.',
  'CC-BY-SA-4.0': 'Others may share and adapt the data, as long as they credit you and share their changes under the same license.',
  'CC-BY-NC-SA-4.0': 'Others may share and adapt the data for non-commercial purposes, as long as they credit you and share their changes under the same license.',
  'CC-BY-ND-4.0': 'Others may share the data, as long as they credit you and do not change it.',
  'CC-BY-NC-ND-4.0': 'Others may share the data for non-commercial purposes, as long as they credit you and do not change it.',
  'CC0-1.0': 'You give up your rights: others may use the data for anything, without crediting you.',
  'ODbL-1.0': 'Others may share and adapt the database, as long as they credit you and keep it open under the same license.',
  MIT: 'Others may use, change and share it for any purpose, as long as the license notice is kept.',
  'Apache-2.0': 'Others may use, change and share it for any purpose, as long as the license notice is kept.',
}

/** The line under an organization in the suggestions: its website, or else its email. */
const orgDetail = (o: Organization) => o.path || o.email || undefined

const SPLIT_LABELS: Record<string, string> = { train: 'Training images', val: 'Validation images', test: 'Test images' }

/** A titled block of the form; a green tick says it is complete. */
function Card({ title, description, done, action, children }: {
  title: ReactNode; description?: ReactNode; done?: boolean; action?: ReactNode; children?: ReactNode
}) {
  return (
    <section className="p-6 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/60 dark:bg-zinc-800/40">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <h5 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{title}</h5>
          {description && <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">{description}</p>}
        </div>
        {done && <span role="img" aria-label="Complete" className="text-emerald-500"><StatusIcon kind="success" className="h-7 w-7" /></span>}
        {action}
      </div>
      {children && <div className="mt-5 space-y-5">{children}</div>}
    </section>
  )
}

/** A field's label, with whether it is needed to publish. */
function FieldLabel({ htmlFor, label, required }: { htmlFor?: string; label: string; required?: boolean }) {
  return (
    <div className="flex items-baseline gap-2 mb-1.5">
      <label htmlFor={htmlFor} className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{label}</label>
      {required !== undefined && <span className="text-xs text-zinc-500 dark:text-zinc-400">{required ? 'Required' : 'Optional'}</span>}
    </div>
  )
}

interface Props {
  /** Read-only facts about the dataset (classes, images per split) and its
   * validation warnings, as returned by api.yoloDataYamlFields. */
  dataset: YoloDataYamlFields
  value: YoloDataYamlMetadata
  onChange: (value: YoloDataYamlMetadata) => void
  /** settings.toml's PRODUCT.organizations — the options for both the
   * publisher and the rights holder (see api.organizations). */
  organizations: Organization[]
  /** settings.toml's PRODUCT.authors — quick-add options for the authors list. */
  authorOptions?: ProductAuthor[]
  /** Why a publisher/rights holder from data.yaml was replaced (see
   * withOrganizationDefaults). */
  organizationWarnings: string[]
  /** For a new version of an already-published dataset — the one being
   * published must be newer (see WizardPage's own Continue gating). */
  previousVersion?: string | null
}

/** The wizard's metadata step for a YOLO dataset: edits the keys this tool
 * adds to data.yaml (not part of the YOLO spec itself) on the session's
 * working copy — the user's own data.yaml is never modified. */
export default function YoloMetadataEditor({ dataset, value, onChange, organizations, authorOptions = [], organizationWarnings, previousVersion }: Props) {
  const set = <K extends keyof YoloDataYamlMetadata>(key: K, fieldValue: YoloDataYamlMetadata[K]) =>
    onChange({ ...value, [key]: fieldValue })
  const license = value.license ?? {}
  // Recognized by id, so typing a known id under "Other…" switches the
  // dropdown over to it — its name/URL then come from COMMON_LICENSES.
  const commonLicense = findCommonLicense(license.id)
  const setLicense = (key: keyof ProductLicense, fieldValue: string) =>
    set('license', { ...license, [key]: fieldValue })
  const setAuthor = (index: number, key: keyof ProductAuthor, fieldValue: string) =>
    set('authors', value.authors.map((a, i) => (i === index ? { ...a, [key]: fieldValue } : a)))
  const moveAuthor = (from: number, to: number) => {
    if (from === to || to < 0 || to >= value.authors.length) return
    const authors = [...value.authors]
    authors.splice(to, 0, authors.splice(from, 1)[0])
    set('authors', authors)
  }
  const [dragging, setDragging] = useState<number | null>(null)
  const [extrasOpen, setExtrasOpen] = useState(true)

  // Saved authors not already in the list (matched by name).
  const listed = new Set(value.authors.map((a) => (a.name ?? '').trim().toLowerCase()))
  const availableAuthors = authorOptions.filter((a) => a.name && !listed.has(a.name.trim().toLowerCase()))

  const filled = (text: string | null | undefined) => !!(text ?? '').trim()
  const aboutDone = filled(value.title) && filled(value.description) && filled(value.version)
    && isNewerVersion(value.version, previousVersion)
  const licenseDone = !licenseIsInvalid(value.license)
  const authorsDone = value.authors.some((a) => !authorIsBlank(a)) && !value.authors.some(authorIsInvalid)
  const organizationsDone = filled(value.publisher?.name) && filled(value.copyright_holders[0])
  const hasExtras = filled(value.funding) || filled(value.acknowledgements)

  return (
    <div className="space-y-5">
      <Notice kind="info">Your changes are saved to a working copy. The original dataset folder is never changed.</Notice>

      <Card title="What we found in your dataset" description="Read from your files. You can’t change these here.">
        <div>
          <p className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 mb-2">Classes · {dataset.class_names.length}</p>
          <ul className="flex flex-wrap gap-2">
            {dataset.class_names.map((name) => (
              <li key={name} className="px-3.5 py-1.5 text-sm rounded-full border border-zinc-300 dark:border-zinc-600 bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200">{name}</li>
            ))}
          </ul>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {Object.entries(dataset.split_image_counts).map(([split, count]) => (
            <div key={split} className="px-5 py-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/40">
              <p className="text-3xl font-semibold text-zinc-900 dark:text-zinc-100">{count}</p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">{SPLIT_LABELS[split] ?? `${split} images`}</p>
            </div>
          ))}
        </div>
        {dataset.warnings.map((warning, i) => <Notice key={i} kind="warning">{warning}</Notice>)}
      </Card>

      <Card title="About the dataset" description="What people will see first." done={aboutDone}>
        <div>
          <FieldLabel htmlFor="yolo-title" label="Title" required />
          <input
            id="yolo-title" type="text" className={inputClass}
            value={value.title ?? ''} onChange={(e) => set('title', e.target.value)}
          />
        </div>
        <div>
          <FieldLabel htmlFor="yolo-description" label="Description" required />
          <textarea
            id="yolo-description" rows={4} className={inputClass}
            value={value.description ?? ''} onChange={(e) => set('description', e.target.value)}
          />
          <p className={hintClass}>A few sentences on what the dataset contains and how it was made.</p>
        </div>
        <div>
          <FieldLabel htmlFor="yolo-version" label="Version" required />
          <div className="flex items-center gap-4 flex-wrap">
            <input
              id="yolo-version" type="text" className={`${inputClass} sm:w-48 font-mono`}
              value={value.version ?? ''} onChange={(e) => set('version', e.target.value)}
            />
            <p className="text-xs text-zinc-500 dark:text-zinc-400 flex-1 min-w-[12rem]">
              Raise it each time you publish a new release, for example 1.1 or 2.0.
            </p>
          </div>
          {previousVersion && (
            <p className={isNewerVersion(value.version, previousVersion) ? hintClass : 'text-xs text-red-600 dark:text-red-400 mt-1.5'}>
              The last published version is {previousVersion} — this one must be newer.
            </p>
          )}
        </div>
        <div>
          <FieldLabel htmlFor="yolo-homepage" label="Homepage" required={false} />
          <input
            id="yolo-homepage" type="text" className={`${inputClass} font-mono`}
            value={value.homepage ?? ''} onChange={(e) => set('homepage', e.target.value)}
          />
          <p className={hintClass}>A web page about this dataset, such as the project site or its code.</p>
        </div>
      </Card>

      <Card title="License" description="What others are allowed to do with the data." done={licenseDone}>
        <div>
          <FieldLabel htmlFor="yolo-license" label="License" required />
          <select
            id="yolo-license" className={inputClass}
            value={commonLicense?.id ?? OTHER_LICENSE}
            onChange={(e) => {
              const picked = findCommonLicense(e.target.value)
              set('license', picked ? { ...picked } : { id: '', name: '', url: '' })
            }}
          >
            {COMMON_LICENSES.map((l) => <option key={l.id} value={l.id}>{l.id} — {l.name}</option>)}
            <option value={OTHER_LICENSE}>Other…</option>
          </select>
        </div>
        {commonLicense ? (
          <div className="p-5 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/40">
            <p className="text-sm text-zinc-800 dark:text-zinc-200">{LICENSE_SUMMARIES[commonLicense.id] ?? commonLicense.name}</p>
            <a href={commonLicense.url} target="_blank" rel="noreferrer" className="inline-block mt-3 text-sm font-semibold text-blue-600 dark:text-blue-400 hover:underline">
              Read the full license terms
            </a>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input
              aria-label="License ID" placeholder="ID (e.g. CC-BY-4.0)"
              className={licenseIsInvalid(value.license) ? invalidInputClass : inputClass}
              value={license.id ?? ''} onChange={(e) => setLicense('id', e.target.value)}
            />
            <input
              aria-label="License name" placeholder="Name" className={inputClass}
              value={license.name ?? ''} onChange={(e) => setLicense('name', e.target.value)}
            />
            <input
              aria-label="License URL" placeholder="URL (optional)" className={inputClass}
              value={license.url ?? ''} onChange={(e) => setLicense('url', e.target.value)}
            />
          </div>
        )}
        {licenseIsInvalid(value.license) && (
          <p className="text-xs text-red-600 dark:text-red-400 -mt-3">A license needs at least an ID or a name.</p>
        )}
      </Card>

      <Card
        title="Authors" done={authorsDone}
        description="Listed in this order in the citation. Drag to reorder, or use the arrows. At least one is required."
      >
        <div className="space-y-3">
          {value.authors.map((author, i) => (
            <div
              key={i} onDragOver={(e) => { if (dragging !== null) e.preventDefault() }}
              onDrop={() => { if (dragging !== null) moveAuthor(dragging, i); setDragging(null) }}
              className={`p-4 rounded-xl border bg-white dark:bg-zinc-900/40 ${dragging === i ? 'opacity-50 border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}
            >
              <div className="flex items-center gap-3 mb-3">
                <span
                  draggable aria-hidden="true" title="Drag to reorder"
                  onDragStart={() => setDragging(i)} onDragEnd={() => setDragging(null)}
                  className="cursor-grab select-none text-zinc-400 text-lg leading-none px-1"
                >⠿</span>
                <p className="flex-1 text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  Author {i + 1}{i === 0 ? ' · cited first' : ''}
                </p>
                <button type="button" className={iconBtn} aria-label={`Move author ${i + 1} up`} disabled={i === 0} onClick={() => moveAuthor(i, i - 1)}>↑</button>
                <button type="button" className={iconBtn} aria-label={`Move author ${i + 1} down`} disabled={i === value.authors.length - 1} onClick={() => moveAuthor(i, i + 1)}>↓</button>
                <button
                  type="button" className={iconBtn} aria-label={`Remove author ${i + 1}`}
                  onClick={() => set('authors', value.authors.filter((_, j) => j !== i))}
                >✕</button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <FieldLabel label="Name" required />
                  <SuggestInput
                    ariaLabel={`Author ${i + 1} name`}
                    className={authorIsInvalid(author) ? invalidInputClass : inputClass}
                    value={author.name ?? ''} onChange={(text) => setAuthor(i, 'name', text)}
                    options={availableAuthors.map((a) => ({ value: a.name ?? '', detail: a.affiliation ?? undefined, affiliation: a.affiliation ?? '' }))}
                    onPick={(picked) => set('authors', value.authors.map((a, j) => (j === i ? { ...a, name: picked.value, affiliation: picked.affiliation } : a)))}
                  />
                </div>
                <div>
                  <FieldLabel label="Organization" required={false} />
                  <input
                    aria-label={`Author ${i + 1} affiliation`} className={inputClass}
                    value={author.affiliation ?? ''} onChange={(e) => setAuthor(i, 'affiliation', e.target.value)}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
        {value.authors.some(authorIsInvalid) && (
          <p className="text-xs text-red-600 dark:text-red-400 -mt-3">Every author needs a name.</p>
        )}
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button" className={`${btnOutline} font-semibold`}
            onClick={() => set('authors', [...value.authors, { name: '', affiliation: '' }])}
          >
            + Add author
          </button>
        </div>
      </Card>

      <Card title="Publisher and rights holder" description="Always included. Both are credited in the citation and in the README." done={organizationsDone}>
        {organizationWarnings.map((warning, i) => <Notice key={i} kind="warning">{warning}</Notice>)}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <FieldLabel htmlFor="yolo-publisher" label="Publisher" />
            <SuggestInput
              id="yolo-publisher" ariaLabel="Publisher" className={inputClass}
              value={value.publisher?.name ?? ''}
              onChange={(text) => {
                // Writing the exact name of a known organization is the same as picking it.
                const known = organizations.find((o) => o.title === text)
                set('publisher', known ? organizationPublisher(known) : { name: text })
              }}
              options={organizations.map((o) => ({ value: o.title, detail: orgDetail(o), org: o }))}
              onPick={(picked) => set('publisher', organizationPublisher(picked.org))}
            />
          </div>
          <div>
            <FieldLabel htmlFor="yolo-rights-holder" label="Rights holder" />
            <SuggestInput
              id="yolo-rights-holder" ariaLabel="Rights holder" className={inputClass}
              value={value.copyright_holders[0] ?? ''}
              onChange={(text) => set('copyright_holders', [text])}
              options={organizations.map((o) => ({ value: o.title, detail: orgDetail(o) }))}
              onPick={(picked) => set('copyright_holders', [picked.value])}
            />
          </div>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 -mt-2">Pick one of the organizations configured for this app, or write any other name.</p>
      </Card>

      <Card
        title={<>Funding and acknowledgements <span className="ml-2 text-sm font-normal text-zinc-500 dark:text-zinc-400">Optional</span></>}
        description={hasExtras
          ? 'Your text is added after the standard WildINTEL text.'
          : 'Nothing added. The standard WildINTEL text is used.'}
        action={(
          <button
            type="button" className={iconBtn} aria-expanded={extrasOpen}
            aria-label={extrasOpen ? 'Hide funding and acknowledgements' : 'Show funding and acknowledgements'}
            onClick={() => setExtrasOpen(!extrasOpen)}
          >
            {extrasOpen ? '⌃' : '⌄'}
          </button>
        )}
      >
        {extrasOpen && (
          <>
            <div>
              <FieldLabel htmlFor="yolo-funding" label="Funding" />
              <textarea
                id="yolo-funding" rows={4} className={inputClass} value={value.funding ?? ''}
                onChange={(e) => set('funding', e.target.value)}
              />
              <p className={hintClass}>Added to the README’s Funding section, after the standard WildINTEL text. You can use Markdown.</p>
            </div>
            <div>
              <FieldLabel htmlFor="yolo-acknowledgements" label="Acknowledgements" />
              <textarea
                id="yolo-acknowledgements" rows={4} className={inputClass} value={value.acknowledgements ?? ''}
                onChange={(e) => set('acknowledgements', e.target.value)}
              />
              <p className={hintClass}>Added to the README’s Acknowledgements section, after the standard text. You can use Markdown.</p>
            </div>
          </>
        )}
      </Card>
    </div>
  )
}
