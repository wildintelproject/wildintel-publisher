import type { Organization, ProductAuthor, ProductLicense, YoloDataYamlFields, YoloDataYamlMetadata } from '../types'
import { COMMON_LICENSES, findCommonLicense } from '../licenses'
import { isNewerVersion } from '../versions'
import { authorIsInvalid, licenseIsInvalid, organizationPublisher } from '../yoloMetadata'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const invalidInputClass = 'w-full px-3 py-2 text-sm rounded border border-red-500 dark:border-red-500 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const OTHER_LICENSE = '__other__'
const selectClass = 'px-2 py-1.5 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const btnOutline = 'px-3 py-1.5 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors'

interface Props {
  /** Read-only facts about the dataset (classes, images per split) and its
   * validation warnings, as returned by api.yoloDataYamlFields. */
  dataset: YoloDataYamlFields
  value: YoloDataYamlMetadata
  onChange: (value: YoloDataYamlMetadata) => void
  /** settings.toml's PRODUCT.organizations — the options for both the
   * publisher and the rights holder (see api.organizations). */
  organizations: Organization[]
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
export default function YoloMetadataEditor({ dataset, value, onChange, organizations, organizationWarnings, previousVersion }: Props) {
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

  return (
    <div className="space-y-4">
      <div className="p-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
        <h5 className="text-sm font-semibold mb-2 text-zinc-700 dark:text-zinc-300">Dataset</h5>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-zinc-500 dark:text-zinc-400">Classes ({dataset.class_names.length})</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">{dataset.class_names.join(', ')}</dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Images</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">
            {Object.entries(dataset.split_image_counts).map(([split, count]) => `${split}: ${count}`).join(' · ')}
          </dd>
        </dl>
        <p className={hintClass}>
          These come from data.yaml's own YOLO keys and the images/ folder — not editable here.
        </p>
        {dataset.warnings.length > 0 && (
          <div className="mt-3 space-y-1">
            {dataset.warnings.map((warning, i) => (
              <p key={i} className="text-sm text-amber-600 dark:text-amber-400">⚠ {warning}</p>
            ))}
          </div>
        )}
      </div>

      <div>
        <label htmlFor="yolo-title" className={labelClass}>Title</label>
        <input
          id="yolo-title" type="text" className={inputClass}
          value={value.title ?? ''} onChange={(e) => set('title', e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="yolo-description" className={labelClass}>Description</label>
        <textarea
          id="yolo-description" rows={3} className={inputClass}
          value={value.description ?? ''} onChange={(e) => set('description', e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="yolo-version" className={labelClass}>Version</label>
        <input
          id="yolo-version" type="text" className={`${inputClass} sm:w-48 font-mono`}
          value={value.version ?? ''} onChange={(e) => set('version', e.target.value)}
        />
        {previousVersion && (
          <p className={isNewerVersion(value.version, previousVersion) ? hintClass : 'text-xs text-red-600 dark:text-red-400 mt-1'}>
            The last published version is {previousVersion} — this one must be newer.
          </p>
        )}
      </div>
      <div>
        <label htmlFor="yolo-homepage" className={labelClass}>Homepage</label>
        <input
          id="yolo-homepage" type="text" className={`${inputClass} font-mono`}
          value={value.homepage ?? ''} onChange={(e) => set('homepage', e.target.value)}
        />
        <p className={hintClass}>Optional — a URL related to this dataset.</p>
      </div>

      <div>
        <label htmlFor="yolo-license" className={labelClass}>License</label>
        <select
          id="yolo-license" className={selectClass}
          value={commonLicense?.id ?? OTHER_LICENSE}
          onChange={(e) => {
            const picked = findCommonLicense(e.target.value)
            set('license', picked ? { ...picked } : { id: '', name: '', url: '' })
          }}
        >
          {COMMON_LICENSES.map((l) => <option key={l.id} value={l.id}>{l.id} — {l.name}</option>)}
          <option value={OTHER_LICENSE}>Other…</option>
        </select>
        {commonLicense ? (
          <p className={hintClass}>
            <a href={commonLicense.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">
              {commonLicense.url}
            </a>
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
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
          <p className="text-xs text-red-600 dark:text-red-400 mt-1">A license needs at least an ID or a name.</p>
        )}
      </div>

      <div>
        <span className={labelClass}>Authors</span>
        <div className="space-y-2">
          {value.authors.map((author, i) => (
            <div key={i} className="flex gap-2 items-start">
              <input
                aria-label={`Author ${i + 1} name`} placeholder="Name"
                className={authorIsInvalid(author) ? invalidInputClass : inputClass}
                value={author.name ?? ''} onChange={(e) => setAuthor(i, 'name', e.target.value)}
              />
              <input
                aria-label={`Author ${i + 1} affiliation`} placeholder="Affiliation (optional)" className={inputClass}
                value={author.affiliation ?? ''} onChange={(e) => setAuthor(i, 'affiliation', e.target.value)}
              />
              <button
                type="button" className={btnOutline} aria-label={`Remove author ${i + 1}`}
                onClick={() => set('authors', value.authors.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        {value.authors.some(authorIsInvalid) && (
          <p className="text-xs text-red-600 dark:text-red-400 mt-1">Every author needs a name.</p>
        )}
        <button
          type="button" className={`${btnOutline} mt-2`}
          onClick={() => set('authors', [...value.authors, { name: '', affiliation: '' }])}
        >
          + Add author
        </button>
      </div>

      <div>
        <span className={labelClass}>Publisher and rights holder</span>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
          Always present, chosen from the organizations configured for this app (settings.toml's
          PRODUCT.organizations). They're credited in CITATION.cff and the README's citation.
        </p>
        {organizationWarnings.length > 0 && (
          <div className="mb-3 space-y-1">
            {organizationWarnings.map((warning, i) => (
              <p key={i} className="text-sm text-amber-600 dark:text-amber-400">⚠ {warning}</p>
            ))}
          </div>
        )}
        <div className="space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex-1 min-w-[10rem] text-sm text-zinc-500 dark:text-zinc-400">Publisher</div>
            <select
              aria-label="Publisher" className={selectClass}
              value={value.publisher?.name ?? ''}
              onChange={(e) => {
                const org = organizations.find((o) => o.title === e.target.value)
                if (org) set('publisher', organizationPublisher(org))
              }}
            >
              {organizations.map((org) => <option key={org.title} value={org.title}>{org.title}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex-1 min-w-[10rem] text-sm text-zinc-500 dark:text-zinc-400">Rights holder</div>
            <select
              aria-label="Rights holder" className={selectClass}
              value={value.copyright_holders[0] ?? ''}
              onChange={(e) => set('copyright_holders', [e.target.value])}
            >
              {organizations.map((org) => <option key={org.title} value={org.title}>{org.title}</option>)}
            </select>
          </div>
        </div>
      </div>

      <p className={hintClass}>
        Saved to a copy of data.yaml inside this session — your own dataset directory is never modified.
        Title, description, version, license and at least one author are required to publish; anything
        still missing is asked for again on the next step.
      </p>
    </div>
  )
}
