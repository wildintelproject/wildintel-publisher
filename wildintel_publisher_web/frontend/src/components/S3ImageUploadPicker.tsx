import { useEffect, useState } from 'react'
import { api } from '../api'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const btnOutline = 'px-3 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-400 border-t-transparent rounded-full animate-spin" />
}

/** The connection details this picker collects — kept in the wizard's own
 * state (see WizardPage) so going Back and returning doesn't lose them. */
export interface S3Config {
  endpointUrl: string
  region: string
  bucket: string
  prefix: string
  publicBaseUrl: string
  accessKey: string
  secretKey: string
  /** Download/hash/rewrite for real, but upload nothing — just list each file's object key. */
  dryRun: boolean
  /** Validate the endpoint's TLS certificate — off only for a trusted self-signed one. */
  verifySsl: boolean
}

export const EMPTY_S3_CONFIG: S3Config = {
  endpointUrl: '', region: '', bucket: '', prefix: '', publicBaseUrl: '', accessKey: '', secretKey: '', dryRun: false, verifySsl: true,
}

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
 * chosen to publish metadata to. Only collects/validates the bucket
 * connection here ("Test connection"); the actual download+upload of every
 * public image (see the backend's services.s3_service.run_s3_image_upload)
 * runs from the metadata step's own "Continue" button, right after the
 * datapackage.json edits have been applied (see WizardPage's
 * handleContinueToPreprocessing) — not from a button in this picker. So
 * media.csv's own filePath is guaranteed to already point at the bucket's
 * public URLs by the time the user chooses where to publish, and any
 * repository downstream (HuggingFace Hub/Zenodo/B2SHARE, mirror or link
 * mode) reads it that way. */
export default function S3ImageUploadPicker({ wanted, onWantedChange, config, onConfigChange }: Props) {
  const [test, setTest] = useState<{ status: 'idle' | 'loading' | 'ok' | 'error'; message: string }>(
    { status: 'idle', message: '' },
  )

  // Pre-fills every field from whatever's already saved in settings.toml —
  // same "defaults from settings, secrets never round-tripped" pattern as
  // PublicationKindPicker's own Zenodo/B2SHARE/GBIF config effect.
  useEffect(() => {
    if (wanted !== true) return
    api.s3GetConfig().then((c) => {
      onConfigChange({
        endpointUrl: config.endpointUrl || c.endpoint_url || '',
        region: config.region || c.region || '',
        bucket: config.bucket || c.bucket || '',
        prefix: config.prefix || c.prefix || '',
        publicBaseUrl: config.publicBaseUrl || c.public_base_url || '',
        accessKey: config.accessKey,
        secretKey: config.secretKey,
        dryRun: config.dryRun,
        verifySsl: c.verify_ssl ?? config.verifySsl,
      })
    }).catch(() => { /* keep whatever's already in `config` */ })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-runs when `wanted` flips to true
  }, [wanted])

  function set<K extends keyof S3Config>(key: K, value: S3Config[K]) {
    onConfigChange({ ...config, [key]: value })
    setTest({ status: 'idle', message: '' })
  }

  async function handleTestConnection() {
    setTest({ status: 'loading', message: '' })
    try {
      await api.s3TestConnection({
        endpointUrl: config.endpointUrl, region: config.region, bucket: config.bucket,
        accessKey: config.accessKey || undefined, secretKey: config.secretKey || undefined,
        verifySsl: config.verifySsl,
      })
      setTest({ status: 'ok', message: 'Connection successful — the bucket is reachable.' })
    } catch (e) {
      setTest({ status: 'error', message: e instanceof Error ? e.message : 'Could not connect to the bucket.' })
    }
  }

  const canTest = config.bucket.trim() !== '' && test.status !== 'loading'

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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass} htmlFor="s3-bucket">Bucket</label>
              <input id="s3-bucket" className={inputClass} value={config.bucket} onChange={(e) => set('bucket', e.target.value)} placeholder="my-bucket" />
            </div>
            <div>
              <label className={labelClass} htmlFor="s3-region">Region (optional)</label>
              <input id="s3-region" className={inputClass} value={config.region} onChange={(e) => set('region', e.target.value)} placeholder="eu-west-1" />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass} htmlFor="s3-endpoint">Endpoint URL (optional — leave empty for AWS S3 itself)</label>
              <input id="s3-endpoint" className={inputClass} value={config.endpointUrl} onChange={(e) => set('endpointUrl', e.target.value)} placeholder="https://minio.example.org" />
            </div>
            <div>
              <label className={labelClass} htmlFor="s3-prefix">Key prefix (optional)</label>
              <input id="s3-prefix" className={inputClass} value={config.prefix} onChange={(e) => set('prefix', e.target.value)} placeholder="wildintel/images" />
            </div>
            <div>
              <label className={labelClass} htmlFor="s3-public-base-url">Public base URL (optional — a CDN/custom domain)</label>
              <input id="s3-public-base-url" className={inputClass} value={config.publicBaseUrl} onChange={(e) => set('publicBaseUrl', e.target.value)} placeholder="https://images.example.org" />
            </div>
            <div>
              <label className={labelClass} htmlFor="s3-access-key">Access key</label>
              <input id="s3-access-key" className={inputClass} value={config.accessKey} onChange={(e) => set('accessKey', e.target.value)} placeholder="Leave empty to use what's already saved" />
            </div>
            <div>
              <label className={labelClass} htmlFor="s3-secret-key">Secret key</label>
              <input id="s3-secret-key" type="password" className={inputClass} value={config.secretKey} onChange={(e) => set('secretKey', e.target.value)} placeholder="Leave empty to use what's already saved" />
            </div>
          </div>

          <label className="flex items-start gap-2 mt-3 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            <input
              type="checkbox" className="mt-0.5" checked={!config.verifySsl}
              onChange={(e) => set('verifySsl', !e.target.checked)}
            />
            <span>
              <strong>Don't validate the SSL certificate</strong> — only for a trusted endpoint with a self-signed
              certificate; it disables protection against man-in-the-middle attacks.
            </span>
          </label>

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
        </div>
      )}
    </div>
  )
}
