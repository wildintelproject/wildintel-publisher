import { useEffect, useState } from 'react'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'

// Accepts https://, http://, git://, ssh:// and scp-like git@host:path forms
// — just enough to catch obviously-wrong input before a clone attempt fails
// server-side with a less friendly git error.
const GIT_URL_PATTERN = /^(https?|git|ssh):\/\/\S+|^[\w.-]+@[\w.-]+:\S+$/

interface Props {
  /** Called with the trimmed git URL once it looks valid, or `null` while
   * it doesn't (or is empty). */
  onSelectionChange: (url: string | null) => void
}

export default function GitCloneForm({ onSelectionChange }: Props) {
  const [url, setUrl] = useState('')

  const trimmed = url.trim()
  const isValid = trimmed.length > 0 && GIT_URL_PATTERN.test(trimmed)

  useEffect(() => {
    onSelectionChange(isValid ? trimmed : null)
  }, [isValid, trimmed, onSelectionChange])

  return (
    <div>
      <label className={labelClass} htmlFor="git-repo-url">Git repository URL</label>
      <input
        id="git-repo-url"
        className={inputClass}
        placeholder="https://github.com/user/repo.git"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <p className={hintClass}>
        The repository will be cloned to fetch its source code — nothing is published yet.
      </p>
      {trimmed.length > 0 && !isValid && (
        <p className="text-sm text-red-600 dark:text-red-400 mt-2">
          This doesn't look like a git repository URL (e.g. https://github.com/user/repo.git).
        </p>
      )}
    </div>
  )
}
