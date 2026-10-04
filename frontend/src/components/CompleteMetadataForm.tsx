import { useState } from 'react'
import { api } from '../api'
import { missingRequiredFields } from '../types'
import type { DatapackageSummary, ProductAuthor } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const readOnlyClass = 'text-sm text-zinc-800 dark:text-zinc-200 px-3 py-2 rounded bg-zinc-100 dark:bg-zinc-800/50'
const btnOutline = 'px-3 py-1.5 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors'
const btnPrimary = 'px-6 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-white/60 border-t-white rounded-full animate-spin" />
}

interface Props {
  /** The directory generateProductMetadata was just called on — where
   * metadata.json (with the gaps this form fills) already lives. */
  inputDir: string
  /** The just-generated summary — whatever the extractor could determine
   * on its own; used to decide which fields are locked vs editable. */
  summary: DatapackageSummary
  /** Called once /api/camtrapdp/complete-metadata succeeds, with the
   * merged, now-complete summary. */
  onComplete: (summary: DatapackageSummary) => void
}

export default function CompleteMetadataForm({ inputDir, summary, onComplete }: Props) {
  const missing = missingRequiredFields(summary)
  const needsTitle = missing.includes('title')
  const needsDescription = missing.includes('description')
  const needsVersion = missing.includes('version')
  const needsLicense = missing.includes('license')
  const needsAuthors = missing.includes('authors')

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [version, setVersion] = useState('')
  const [licenseId, setLicenseId] = useState('')
  const [licenseName, setLicenseName] = useState('')
  const [licenseUrl, setLicenseUrl] = useState('')
  const [authors, setAuthors] = useState<ProductAuthor[]>([{ name: '', affiliation: '' }])
  const [homepage, setHomepage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function updateAuthor(index: number, field: keyof ProductAuthor, value: string) {
    setAuthors((prev) => prev.map((a, i) => (i === index ? { ...a, [field]: value } : a)))
  }

  const filledAuthors = authors.filter((a) => (a.name ?? '').trim() !== '')
  const canSubmit = !submitting
    && (!needsTitle || title.trim() !== '')
    && (!needsDescription || description.trim() !== '')
    && (!needsVersion || version.trim() !== '')
    && (!needsLicense || (licenseId.trim() !== '' && licenseName.trim() !== ''))
    && (!needsAuthors || filledAuthors.length > 0)

  async function handleSubmit() {
    setSubmitting(true)
    setError(null)
    try {
      const updates: Partial<Omit<DatapackageSummary, 'product_type' | 'hfh_repo_id'>> = {}
      if (needsTitle) updates.title = title.trim()
      if (needsDescription) updates.description = description.trim()
      if (needsVersion) updates.version = version.trim()
      if (needsLicense) updates.license = { id: licenseId.trim(), name: licenseName.trim(), url: licenseUrl.trim() }
      if (needsAuthors) {
        updates.authors = filledAuthors.map((a) => ({ name: (a.name ?? '').trim(), affiliation: (a.affiliation ?? '').trim() }))
      }
      if (homepage.trim() !== '') updates.homepage = homepage.trim()

      const updated = await api.completeProductMetadata(inputDir, updates)
      onComplete(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the metadata.')
      setSubmitting(false)
    }
  }

  return (
    <div className="mt-6 p-4 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/20">
      <h5 className="font-semibold text-zinc-900 dark:text-zinc-100 mb-1">Some details are missing</h5>
      <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-4">
        Could not read everything from the product itself — please fill in the rest below.
      </p>

      <div className="flex flex-col gap-4">
        <div>
          <label className={labelClass} htmlFor="meta-title">Title</label>
          {needsTitle ? (
            <input id="meta-title" className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
          ) : (
            <p className={readOnlyClass}>{summary.title}</p>
          )}
        </div>

        <div>
          <label className={labelClass} htmlFor="meta-description">Description</label>
          {needsDescription ? (
            <textarea id="meta-description" className={inputClass} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          ) : (
            <p className={readOnlyClass}>{summary.description}</p>
          )}
        </div>

        <div>
          <label className={labelClass} htmlFor="meta-version">Version</label>
          {needsVersion ? (
            <input id="meta-version" className={inputClass} value={version} onChange={(e) => setVersion(e.target.value)} />
          ) : (
            <p className={readOnlyClass}>{summary.version}</p>
          )}
        </div>

        <div>
          <span className={labelClass}>License</span>
          {needsLicense ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <input aria-label="License ID" className={inputClass} placeholder="ID (e.g. CC-BY-4.0)" value={licenseId} onChange={(e) => setLicenseId(e.target.value)} />
              <input aria-label="License name" className={inputClass} placeholder="Name" value={licenseName} onChange={(e) => setLicenseName(e.target.value)} />
              <input aria-label="License URL" className={inputClass} placeholder="URL (optional)" value={licenseUrl} onChange={(e) => setLicenseUrl(e.target.value)} />
            </div>
          ) : (
            <p className={readOnlyClass}>{summary.license?.name ?? summary.license?.id}</p>
          )}
        </div>

        <div>
          <span className={labelClass}>Authors</span>
          {needsAuthors ? (
            <div className="flex flex-col gap-2">
              {authors.map((author, i) => (
                <div key={i} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2">
                  <input aria-label={`Author ${i + 1} name`} className={inputClass} placeholder="Name" value={author.name ?? ''} onChange={(e) => updateAuthor(i, 'name', e.target.value)} />
                  <input aria-label={`Author ${i + 1} affiliation`} className={inputClass} placeholder="Affiliation (optional)" value={author.affiliation ?? ''} onChange={(e) => updateAuthor(i, 'affiliation', e.target.value)} />
                  <button
                    type="button"
                    className={btnOutline}
                    disabled={authors.length === 1}
                    onClick={() => setAuthors((prev) => prev.filter((_, idx) => idx !== i))}
                    aria-label={`Remove author ${i + 1}`}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <div>
                <button type="button" className={btnOutline} onClick={() => setAuthors((prev) => [...prev, { name: '', affiliation: '' }])}>
                  + Add author
                </button>
              </div>
            </div>
          ) : (
            <p className={readOnlyClass}>{summary.authors.map((a) => a.name).filter(Boolean).join(', ')}</p>
          )}
        </div>

        <div>
          <label className={labelClass} htmlFor="meta-homepage">Homepage (optional)</label>
          {summary.homepage ? (
            <p className={readOnlyClass}>{summary.homepage}</p>
          ) : (
            <input id="meta-homepage" className={inputClass} placeholder="https://…" value={homepage} onChange={(e) => setHomepage(e.target.value)} />
          )}
        </div>
      </div>

      <div className="flex justify-end mt-5">
        <button type="button" className={btnPrimary} disabled={!canSubmit} onClick={handleSubmit}>
          {submitting && <SmallSpinner />}
          {submitting ? 'Saving…' : 'Continue'}
        </button>
      </div>
      {error && <p className="text-sm text-red-600 dark:text-red-400 text-right mt-2">{error}</p>}
    </div>
  )
}
