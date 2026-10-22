import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DatapackageSummary } from '../types'
import DirectoryPicker from './DirectoryPicker'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const btnOutline = 'px-4 py-2 text-sm border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

/** The tick (or the exclamation mark) inside a filled round badge, as in wildintel-uploader's folder step. */
function BadgeIcon({ kind }: { kind: 'tick' | 'alert' }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      {kind === 'tick' ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M12 5v9M12 19h.01" />}
    </svg>
  )
}

/** What the folder was found to be: a bordered card with a round badge, a bold line and a grey one under it. */
function ResultCard({ tone, title, detail }: { tone: 'ok' | 'error'; title: string; detail?: string }) {
  const box = tone === 'ok'
    ? 'border-emerald-300 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40'
    : 'border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40'
  return (
    <div className={`flex items-center gap-3 rounded border px-4 py-3 ${box}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div aria-hidden="true" className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-white font-bold ${tone === 'ok' ? 'bg-emerald-600' : 'bg-red-600'}`}>
        <BadgeIcon kind={tone === 'ok' ? 'tick' : 'alert'} />
      </div>
      <div className="flex-1 min-w-0 text-sm">
        <p className="font-semibold text-zinc-900 dark:text-zinc-100 break-words">{title}</p>
        {detail && <p className="text-zinc-600 dark:text-zinc-400 break-words">{detail}</p>}
      </div>
    </div>
  )
}

type CheckStatus = 'idle' | 'checking' | 'valid' | 'invalid'

interface CheckState {
  status: CheckStatus
  summary: DatapackageSummary | null
  error: string | null
  // The app-owned working copy (see api.resolveLocalSource/
  // api.yoloResolveLocalSource) that the rest of the wizard should actually
  // use as input_dir from here on, so it never mutates the user's own
  // directory: just the core files for Camtrap DP, just data.yaml (plus a
  // pointer back to `path` for images/labels) for YOLO.
  workingDir: string | null
}

export interface LocalSourceSelection {
  /** Working directory the rest of the wizard should use as input_dir. */
  path: string
  /** Original directory the user typed/picked — kept separately so
   * locally-referenced media (media.csv's filePath) can still be found at
   * publish time, without ever having been copied. */
  sourcePath: string
  /** The session this resolve started (see api.resolveLocalSource/
   * api.yoloResolveLocalSource) — same role as WizardPage's own
   * sessionTaskId for a Trapper/git/archive source, threaded the same way
   * into generateProductMetadata/publishAllStart from here on. */
  sessionTaskId?: string
}

interface Props {
  /** Which ProductAdapter to validate/extract metadata with (see
   * services.product.get_adapter in the backend) — "camtrapdp" or "yolo". */
  productType: string
  /** Called once the directory's metadata.json has been generated
   * successfully, or `null` while it hasn't (or is no longer) valid. */
  onSelectionChange: (selection: LocalSourceSelection | null) => void
  /** Pre-fills `path` — set when resuming a session whose local-directory
   * resolve itself failed (see WizardPage's own resumeSession prop): the
   * working copy never got created, so there's nothing to skip straight
   * past like the "fetched"/"preprocessed" phases do, but retyping the
   * exact same path shouldn't have to happen by memory. */
  initialPath?: string
  /** Pairs with `initialPath` — the same session that failed resolve
   * started (see resumeSession.task_id), reused instead of minting a new
   * one on the retry. */
  initialSessionTaskId?: string
}

const PICKER_TITLE = 'Select the directory'

export default function LocalDirectoryForm({ productType, onSelectionChange, initialPath, initialSessionTaskId }: Props) {
  const [path, setPath] = useState(initialPath ?? '')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [nativeOpen, setNativeOpen] = useState(false)
  // Browse opens the operating system's own folder dialog (the backend runs
  // on this same machine); the in-page DirectoryPicker is only the fallback
  // for a machine that can't open one.
  async function handleBrowse() {
    setNativeOpen(true)
    try {
      const { path: chosen } = await api.fsPickDirectory(path || undefined, PICKER_TITLE)
      if (chosen) setPath(chosen)
    } catch {
      setPickerOpen(true)
    } finally {
      setNativeOpen(false)
    }
  }

  const [check, setCheck] = useState<CheckState>({ status: 'idle', summary: null, error: null, workingDir: null })
  // The session minted by this form's own first successful (or failed)
  // resolveLocalSource call — reused for every later call, including
  // every re-run of the debounced effect below as the user keeps editing
  // `path`, so a session_dir is never left behind per keystroke. A ref
  // (not state) so the very next debounced call already sees it — waiting
  // on a state update/re-render here could race a fast retype into
  // minting a second, orphaned session.
  const sessionTaskIdRef = useRef<string | undefined>(initialSessionTaskId)

  // Debounced: validate `path` shortly after it stops changing, so typing
  // doesn't trigger a request per keystroke.
  useEffect(() => {
    if (!path.trim()) {
      setCheck({ status: 'idle', summary: null, error: null, workingDir: null })
      return
    }
    let cancelled = false
    setCheck({ status: 'checking', summary: null, error: null, workingDir: null })

    const generatePreview = (workingDir: string, sessionTaskId?: string) =>
      api.generateProductMetadata(workingDir, productType, undefined, undefined, undefined, undefined, sessionTaskId)
        .then((summary) => { if (!cancelled) setCheck({ status: 'valid', summary, error: null, workingDir }) })
        .catch((e) => {
          if (!cancelled) {
            setCheck({
              status: 'invalid', summary: null, workingDir: null,
              error: e instanceof Error ? e.message : 'Could not read this directory.',
            })
          }
        })

    const handle = setTimeout(() => {
      // Copy just the small files (Camtrap DP: datapackage.json + its 3
      // tables; YOLO: data.yaml) into an app-owned working directory first
      // (never mutate `path` itself — see services.camtrapdp_source.
      // resolve_local_camtrapdp_source/yolo_adapter.create_working_copy),
      // then preview/write metadata.json into THAT copy.
      const resolve = productType === 'yolo' ? api.yoloResolveLocalSource : api.resolveLocalSource
      resolve(path, sessionTaskIdRef.current)
        .then((res) => {
          sessionTaskIdRef.current = res.taskId
          if (cancelled) return
          if (res.status === 'valid' && res.workingDir) {
            return generatePreview(res.workingDir, res.taskId)
          }
          const fallback = productType === 'yolo' ? 'Not a valid YOLO dataset.' : 'Not a valid Camtrap DP package.'
          setCheck({ status: 'invalid', summary: null, workingDir: null, error: res.error ?? fallback })
        })
        .catch((e) => {
          if (!cancelled) {
            setCheck({
              status: 'invalid', summary: null, workingDir: null,
              error: e instanceof Error ? e.message : 'Could not read this directory.',
            })
          }
        })
    }, 400)
    return () => { cancelled = true; clearTimeout(handle) }
  }, [path, productType])

  useEffect(() => {
    onSelectionChange(
      check.status === 'valid' && check.workingDir
        ? { path: check.workingDir, sourcePath: path, sessionTaskId: sessionTaskIdRef.current }
        : null,
    )
  }, [check.status, check.workingDir, path, onSelectionChange])

  const kindLabel = productType === 'yolo' ? 'YOLO dataset' : 'Camtrap DP package'
  return (
    <div>
      <div className="mb-4">
        <label className={labelClass} htmlFor="local-product-dir">Directory</label>
        <div className="flex gap-2">
          <input
            id="local-product-dir"
            className={`${inputClass} flex-1`}
            placeholder="/path/to/dataset"
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <button type="button" className={`${btnOutline} flex items-center gap-2`} disabled={nativeOpen} onClick={handleBrowse}>
            {nativeOpen && <SmallSpinner />}
            {nativeOpen ? 'Browsing…' : 'Browse…'}
          </button>
        </div>
      </div>

      {check.status === 'checking' && (
        <div className="flex items-center gap-3 rounded border border-zinc-300 dark:border-zinc-700 px-4 py-3 text-sm text-zinc-600 dark:text-zinc-400">
          <SmallSpinner /> Reading the {kindLabel}…
        </div>
      )}
      {check.status === 'valid' && (
        <ResultCard
          tone="ok" title={check.summary?.title ?? `Valid ${kindLabel}`}
          detail={[kindLabel, check.summary?.version && `version ${check.summary.version}`].filter(Boolean).join(' · ')}
        />
      )}
      {check.status === 'invalid' && (
        <ResultCard tone="error" title={`Not a valid ${kindLabel}`} detail={check.error ?? undefined} />
      )}

      {pickerOpen && (
        <DirectoryPicker
          initialPath={path || undefined}
          title={PICKER_TITLE}
          onSelect={setPath}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  )
}
