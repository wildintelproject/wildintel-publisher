import { useEffect, useState } from 'react'
import { api } from '../api'
import type { BrowseResult } from '../types'

interface Props {
  /** Called with the chosen absolute path when "Select" is clicked. */
  onSelect: (path: string) => void
  onClose: () => void
  initialPath?: string
  title?: string
}

const btnOutline = 'px-3 py-1 text-sm border border-zinc-400 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50'
const btnPrimary = 'px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-50'

export default function DirectoryPicker({ onSelect, onClose, initialPath, title }: Props) {
  const [data, setData] = useState<BrowseResult | null>(null)
  const [manualPath, setManualPath] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { browse(initialPath) }, [])

  async function browse(path?: string) {
    setLoading(true)
    setError(null)
    try {
      const result = await api.fsBrowse(path)
      setData(result)
      setManualPath(result.current)
    } catch (e) {
      if (path !== undefined) {
        await browse(undefined) // retry from the fallback (home) directory
        return
      }
      setError(e instanceof Error ? e.message : 'Could not read the directory.')
    } finally {
      setLoading(false)
    }
  }

  const segments = data ? data.current.split('/').filter(Boolean) : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg max-h-[80vh] flex flex-col rounded-lg bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700">
          <h5 className="font-semibold text-zinc-900 dark:text-zinc-100">{title ?? 'Select a directory'}</h5>
        </div>

        <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); browse(manualPath) }}>
            <input
              className="flex-1 px-3 py-1.5 text-sm rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
            />
            <button type="submit" className={btnOutline}>Go</button>
          </form>

          {data && (
            <div className="flex flex-wrap items-center gap-1 mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              <button type="button" className="hover:text-blue-600 dark:hover:text-blue-400" onClick={() => browse('/')}>/</button>
              {segments.map((seg, i) => (
                <span key={i} className="flex items-center gap-1">
                  <span>/</span>
                  <button
                    type="button"
                    className="hover:text-blue-600 dark:hover:text-blue-400"
                    onClick={() => browse('/' + segments.slice(0, i + 1).join('/'))}
                  >
                    {seg}
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          {loading && <p className="text-sm text-zinc-500 dark:text-zinc-400 px-2 py-1">Loading…</p>}
          {error && <p className="text-sm text-red-600 dark:text-red-400 px-2 py-1">{error}</p>}
          {!loading && data && (
            <ul>
              {data.parent && (
                <li>
                  <button
                    type="button"
                    className="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-400"
                    onClick={() => browse(data.parent as string)}
                  >
                    .. (up)
                  </button>
                </li>
              )}
              {data.dirs.length === 0 && (
                <li className="text-sm text-zinc-500 dark:text-zinc-400 px-2 py-1">No subdirectories</li>
              )}
              {data.dirs.map((d) => (
                <li key={d.path}>
                  <button
                    type="button"
                    className="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-800 dark:text-zinc-200"
                    onClick={() => setManualPath(d.path)}
                    onDoubleClick={() => browse(d.path)}
                  >
                    📁 {d.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-zinc-200 dark:border-zinc-700">
          <span className="text-xs font-mono text-zinc-500 dark:text-zinc-400 truncate">{manualPath}</span>
          <div className="flex gap-2 flex-shrink-0">
            <button type="button" className={btnOutline} onClick={onClose}>Cancel</button>
            <button
              type="button"
              className={btnPrimary}
              disabled={!manualPath}
              onClick={() => { onSelect(manualPath); onClose() }}
            >
              Select
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
