import { useState } from 'react'
import { api } from '../api'
import type { PublishSessionSummary } from '../types'

interface Props {
  sessions: PublishSessionSummary[]
  /** Resumes `session` — the caller mounts a WizardPage with it as
   * resumeSession, skipping straight to the publish step. */
  onResume: (session: PublishSessionSummary) => void
  /** Discards `session` from the list (already deleted on the backend by
   * the time this is called). */
  onDiscarded: (taskId: string) => void
  /** Leaves this screen to start a brand new publish instead — the
   * sessions themselves are untouched, and will be offered again next time
   * the web app starts. */
  onSkip: () => void
}

const REPO_TITLES: Record<string, string> = {
  hfh: 'Hugging Face Hub', zenodo: 'Zenodo', b2share: 'B2SHARE', gbif: 'GBIF',
}

const btnOutline = 'px-4 py-2 text-sm border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50'
const btnPrimary = 'px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40'
const btnDanger = 'px-4 py-2 text-sm border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 rounded hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors disabled:opacity-50'

function formatCreatedAt(createdAt: string): string {
  try {
    return new Date(createdAt).toLocaleString()
  } catch {
    return createdAt
  }
}

function SessionCard({ session, onResume, onDiscarded }: { session: PublishSessionSummary; onResume: () => void; onDiscarded: (taskId: string) => void }) {
  const [discarding, setDiscarding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDiscard() {
    setDiscarding(true)
    setError(null)
    try {
      await api.discardPublishSession(session.task_id)
      onDiscarded(session.task_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not discard this session.')
      setDiscarding(false)
    }
  }

  return (
    <div className="rounded-xl border-2 border-zinc-300 dark:border-zinc-700 p-5">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <strong className="text-zinc-900 dark:text-zinc-100">
            {session.repos.map((r) => REPO_TITLES[r.repo] ?? r.repo).join(' → ')}
          </strong>
          <p className="text-zinc-500 dark:text-zinc-400 text-xs mt-0.5">
            Started {formatCreatedAt(session.created_at)}
            {session.dry_run && ' — dry run'}
          </p>
        </div>
        {session.status === 'error' && (
          <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300 whitespace-nowrap">
            Interrupted
          </span>
        )}
      </div>

      <ul className="list-none p-0 m-0 mb-4 space-y-1">
        {session.repos.map((r) => {
          const status = session.repo_status[r.repo]
          const label = status?.status === 'done' ? 'Done'
            : status?.status === 'error' ? `Failed${status.error ? `: ${status.error}` : ''}`
            : status?.stage ? `Interrupted (${status.stage})`
            : 'Not started'
          const color = status?.status === 'done' ? 'text-emerald-600 dark:text-emerald-400'
            : status?.status === 'error' ? 'text-red-600 dark:text-red-400'
            : 'text-zinc-500 dark:text-zinc-400'
          return (
            <li key={r.repo} className="text-sm flex items-center gap-2">
              <span className="text-zinc-700 dark:text-zinc-300 font-medium">{REPO_TITLES[r.repo] ?? r.repo}</span>
              <span className={color}>{label}</span>
            </li>
          )
        })}
      </ul>

      {error && <p className="text-sm text-red-600 dark:text-red-400 mb-3">{error}</p>}

      <div className="flex items-center gap-2">
        <button type="button" className={btnPrimary} onClick={onResume} disabled={discarding}>
          Resume
        </button>
        <button type="button" className={btnDanger} onClick={handleDiscard} disabled={discarding}>
          {discarding ? 'Discarding…' : 'Discard'}
        </button>
      </div>
    </div>
  )
}

export default function ResumeSessionsPage({ sessions, onResume, onDiscarded, onSkip }: Props) {
  return (
    <div className="mx-auto px-4 py-8" style={{ maxWidth: 700 }}>
      <h1 className="text-2xl font-bold mb-1">Unfinished publish{sessions.length > 1 ? 'es' : ''}</h1>
      <p className="text-zinc-500 dark:text-zinc-400 mb-6 text-sm">
        {sessions.length === 1
          ? 'A previous publish was interrupted before it finished. Resume it to pick up where it left off — '
          : 'These publishes were interrupted before they finished. Resume one to pick up where it left off — '}
        already-downloaded images and already-uploaded files won't be redone. Credentials are never saved, so
        you'll need to re-enter them.
      </p>

      <div className="space-y-4 mb-6">
        {sessions.map((session) => (
          <SessionCard
            key={session.task_id}
            session={session}
            onResume={() => onResume(session)}
            onDiscarded={onDiscarded}
          />
        ))}
      </div>

      <button type="button" className={btnOutline} onClick={onSkip}>
        Start a new publish instead
      </button>
    </div>
  )
}
