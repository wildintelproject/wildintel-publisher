import { useEffect, useState } from 'react'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'

interface Props {
  /** Called with the trimmed URL once it looks like an http(s) URL, or
   * `null` while it doesn't (or is empty). */
  onSelectionChange: (url: string | null) => void
}

export default function CamtrapDPArchiveForm({ onSelectionChange }: Props) {
  const [url, setUrl] = useState('')

  const trimmed = url.trim()
  const isValid = /^https?:\/\/\S+$/.test(trimmed)

  useEffect(() => {
    onSelectionChange(isValid ? trimmed : null)
  }, [isValid, trimmed, onSelectionChange])

  return (
    <div>
      <label className={labelClass} htmlFor="camtrapdp-archive-url">Camtrap DP archive URL</label>
      <input
        id="camtrapdp-archive-url"
        className={inputClass}
        placeholder="https://huggingface.co/datasets/user/dataset/resolve/main/camtrapdp-remote.zip"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <p className={hintClass}>
        Must be a zip archive containing the whole Camtrap DP package (datapackage.json plus its
        tables) — it gets downloaded and validated against the official schema before continuing.
        This same URL can then be reused directly if you register it with GBIF later, since it's
        already confirmed public.
      </p>
      {trimmed.length > 0 && !isValid && (
        <p className="text-sm text-red-600 dark:text-red-400 mt-2">
          This doesn't look like a public http(s) URL.
        </p>
      )}
    </div>
  )
}
