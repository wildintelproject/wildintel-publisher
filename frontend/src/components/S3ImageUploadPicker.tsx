import { useEffect, useState } from 'react'
import { api } from '../api'
import type { S3Remote } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const btnOutline = 'px-3 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-400 border-t-transparent rounded-full animate-spin" />
}

/** What this picker collects — kept in the wizard's own state (see
 * WizardPage) so going Back and returning doesn't lose it. The connection
 * itself (bucket, credentials...) is a remote saved on the settings page. */
export interface S3Config {
  /** Id of the saved remote to upload to ('' until one is chosen). */
  remoteId: string
  /** Download/hash/rewrite for real, but upload nothing — just list each file's object key. */
  dryRun: boolean
}

export const EMPTY_S3_CONFIG: S3Config = { remoteId: '', dryRun: false }

interface Props {
  /** Whether the user wants to upload this package's own public images to
   * a S3-compatible bucket before publishing metadata anywhere — null
   * means "not asked yet" (neither radio button checked). */
  wanted: boolean | null
  onWantedChange: (wanted: boolean) => void
  config: S3Config
  onConfigChange: (config: S3Config) => void
}

/** Asked at the very start of the metadata step, before
 * PublicationKindPicker — independent of which repositories are later
 * chosen to publish metadata to. Only picks which saved remote to use
 * (they're managed under Settings → S3 image hosting) and lets the user
 * test it; the actual download+upload of every public image (see the
 * backend's services.s3_service.run_s3_image_upload) runs from the metadata
 * step's own "Continue" button, right after the datapackage.json edits have
 * been applied (see WizardPage's handleContinueToPreprocessing) — not from a
 * button in this picker. So media.csv's own filePath is guaranteed to
 * already point at the bucket's public URLs by the time the user chooses
 * where to publish, and any repository downstream (HuggingFace
 * Hub/Zenodo/B2SHARE, mirror or link mode) reads it that way. */
export default function S3ImageUploadPicker({ wanted, onWantedChange, config, onConfigChange }: Props) {
  const [remotes, setRemotes] = useState<S3Remote[] | null>(null)
  const [test, setTest] = useState<{ status: 'idle' | 'loading' | 'ok' | 'error'; message: string }>(
    { status: 'idle', message: '' },
  )

  // Loads the saved remotes once the user says yes, pre-selecting the
  // previous choice, or the only one there is.
  useEffect(() => {
    if (wanted !== true) return
    api.s3GetConfig().then(({ remotes: saved }) => {
      setRemotes(saved)
      if (!saved.some((r) => r.id === config.remoteId)) {
        onConfigChange({ ...config, remoteId: saved.length === 1 ? saved[0].id : '' })
      }
    }).catch(() => setRemotes([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-runs when `wanted` flips to true
  }, [wanted])

  const selected = remotes?.find((r) => r.id === config.remoteId) ?? null

  function set<K extends keyof S3Config>(key: K, value: S3Config[K]) {
    onConfigChange({ ...config, [key]: value })
    setTest({ status: 'idle', message: '' })
  }

  async function handleTestConnection() {
    setTest({ status: 'loading', message: '' })
    try {
      await api.s3TestConnection({ remoteId: config.remoteId })
      setTest({ status: 'ok', message: 'Connection successful — the bucket is reachable.' })
    } catch (e) {
      setTest({ status: 'error', message: e instanceof Error ? e.message : 'Could not connect to the bucket.' })
    }
  }

  const canTest = selected !== null && test.status !== 'loading'

  return (
    <div className="mb-8">
      <h5 className="text-base font-semibold mb-2 text-zinc-800 dark:text-zinc-200">Upload images to a public repository?</h5>
      <div className="flex flex-col gap-2">
        <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
          <input
            type="radio" name="s3-upload-wanted" className="mt-0.5" checked={wanted === false}
            onChange={() => onWantedChange(false)}
          />
          <span><strong>No</strong> — media.csv's filePath is left as-is.</span>
        </label>
        <label className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
          <input
            type="radio" name="s3-upload-wanted" className="mt-0.5" checked={wanted === true}
            onChange={() => onWantedChange(true)}
          />
          <span>
            <strong>Yes</strong> — download every public image and upload it to a S3-compatible bucket (AWS S3,
            MinIO, ...) first, so every repository published afterwards links to it instead of re-hosting the
            images itself. This happens when you press Continue, right after your metadata edits are applied.
          </span>
        </label>
      </div>

      {wanted === true && (
        <div className="mt-4 ml-6 p-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
          {remotes === null && <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading remotes…</p>}
          {remotes !== null && remotes.length === 0 && (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              There is no S3 remote saved yet — add one under Settings → S3 image hosting, then come back.
            </p>
          )}
          {remotes !== null && remotes.length > 0 && (
            <>
              <label className={labelClass} htmlFor="s3-remote">Remote</label>
              <select id="s3-remote" className={inputClass} value={config.remoteId} onChange={(e) => set('remoteId', e.target.value)}>
                <option value="">Choose a remote…</option>
                {remotes.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}{r.bucket ? ` — ${r.bucket}` : ''}</option>
                ))}
              </select>
              {selected && (
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {[selected.endpoint_url ?? 'AWS S3', selected.bucket && `bucket ${selected.bucket}`, selected.prefix && `prefix ${selected.prefix}`]
                    .filter(Boolean).join(' · ')}
                </p>
              )}

              <label className="flex items-start gap-2 mt-3 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
                <input
                  type="checkbox" className="mt-0.5" checked={config.dryRun}
                  onChange={(e) => onConfigChange({ ...config, dryRun: e.target.checked })}
                />
                <span>
                  <strong>Dry run</strong> — go through every image and show the name each one would get in the
                  bucket, without uploading anything. media.csv is still rewritten to those URLs, and the wizard stays
                  on this step so you can uncheck this and run it for real.
                </span>
              </label>

              <div className="flex items-center gap-2 mt-3">
                <button type="button" className={btnOutline} disabled={!canTest} onClick={handleTestConnection}>
                  {test.status === 'loading' && <SmallSpinner />}
                  {test.status === 'loading' ? 'Testing…' : 'Test connection'}
                </button>
              </div>
              {test.status === 'ok' && <p className="text-sm text-emerald-600 dark:text-emerald-400 mt-2">{test.message}</p>}
              {test.status === 'error' && <p className="text-sm text-red-600 dark:text-red-400 mt-2">{test.message}</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
