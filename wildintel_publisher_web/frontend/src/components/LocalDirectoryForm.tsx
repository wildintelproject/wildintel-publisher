import { useEffect, useState } from 'react'
import { api } from '../api'
import type { DatapackageSummary } from '../types'
import DirectoryPicker from './DirectoryPicker'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const browseBtn = 'px-3 py-2 text-sm border border-l-0 border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 rounded-r hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors flex-shrink-0'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

type CheckStatus = 'idle' | 'checking' | 'valid' | 'invalid'

interface CheckState {
  status: CheckStatus
  summary: DatapackageSummary | null
  error: string | null
}

interface Props {
  /** Which ProductAdapter to validate/extract metadata with (see
   * services.product.get_adapter in the backend) — "camtrapdp" or "yolo". */
  productType: string
  /** Called with the confirmed directory path once its metadata.json has
   * been generated successfully, or `null` while it hasn't (or is no
   * longer) valid. */
  onSelectionChange: (path: string | null) => void
}

export default function LocalDirectoryForm({ productType, onSelectionChange }: Props) {
  const [path, setPath] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [check, setCheck] = useState<CheckState>({ status: 'idle', summary: null, error: null })

  // Debounced: validate `path` (and write its metadata.json — see
  // generate_metadata_json) shortly after it stops changing, so typing
  // doesn't trigger a request per keystroke.
  useEffect(() => {
    if (!path.trim()) {
      setCheck({ status: 'idle', summary: null, error: null })
      return
    }
    let cancelled = false
    setCheck({ status: 'checking', summary: null, error: null })
    const handle = setTimeout(() => {
      api.generateProductMetadata(path, productType)
        .then((summary) => { if (!cancelled) setCheck({ status: 'valid', summary, error: null }) })
        .catch((e) => {
          if (!cancelled) {
            setCheck({
              status: 'invalid', summary: null,
              error: e instanceof Error ? e.message : 'Could not read this directory.',
            })
          }
        })
    }, 400)
    return () => { cancelled = true; clearTimeout(handle) }
  }, [path, productType])

  useEffect(() => {
    onSelectionChange(check.status === 'valid' ? path : null)
  }, [check.status, path, onSelectionChange])

  return (
    <div>
      <label className={labelClass} htmlFor="local-product-dir">Directory</label>
      <div className="flex">
        <input
          id="local-product-dir"
          className={inputClass + ' rounded-r-none'}
          placeholder="/path/to/dataset"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <button type="button" className={browseBtn} onClick={() => setPickerOpen(true)}>
          📁 Browse
        </button>
      </div>

      {check.status === 'checking' && (
        <div className="flex items-center gap-1.5 mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          <SmallSpinner /> Reading metadata…
        </div>
      )}
      {check.status === 'valid' && (
        <div className="flex items-center gap-1.5 mt-2 text-sm text-emerald-600 dark:text-emerald-400">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          {check.summary?.title ?? 'Valid package'}
        </div>
      )}
      {check.status === 'invalid' && (
        <p className="text-sm text-red-600 dark:text-red-400 mt-2">{check.error}</p>
      )}

      {pickerOpen && (
        <DirectoryPicker
          initialPath={path || undefined}
          title="Select the directory"
          onSelect={setPath}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  )
}
