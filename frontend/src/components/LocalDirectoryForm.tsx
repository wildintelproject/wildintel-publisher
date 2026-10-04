import { useEffect, useRef, useState } from 'react'
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
        <button type="button" className={browseBtn} disabled={nativeOpen} onClick={handleBrowse}>
          {nativeOpen ? 'Choose in the dialog…' : '📁 Browse'}
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
          title={PICKER_TITLE}
          onSelect={setPath}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  )
}
