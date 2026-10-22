import { useState, type ReactNode } from 'react'

/** One repository on the settings check: a card with its state (a tick once reviewed), a one-line summary and a chevron.
 * Opens to show its form. The form is mounted the first time the card opens and stays mounted, so what was typed
 * is kept while the card is closed. */
export default function RepoPanel({ n, title, summary, reviewed, locked = false, open, onToggle, children }: {
  /** Its place in the publish order — in the circle until reviewed, then in front of the title. */
  n: number
  title: string
  summary: ReactNode
  reviewed: boolean
  /** Can't be opened yet — the summary says what it waits for. */
  locked?: boolean
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const [everOpened, setEverOpened] = useState(open)
  if (open && !everOpened) setEverOpened(true)
  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 mb-3">
      <button
        type="button" disabled={locked} aria-expanded={open && !locked} onClick={onToggle}
        className="w-full flex items-center gap-3 px-5 py-4 text-left disabled:cursor-not-allowed"
      >
        <span className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${reviewed ? 'bg-emerald-700 text-white' : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-500 dark:text-zinc-400'}`}>
          {reviewed ? (
            <svg aria-hidden="true" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          ) : (
            <span aria-hidden="true" className="text-sm font-bold">{n}</span>
          )}
        </span>
        <span className="flex-1 min-w-0">
          <span className={`block text-base font-semibold ${locked ? 'text-zinc-500 dark:text-zinc-400' : 'text-zinc-900 dark:text-zinc-100'}`}>{reviewed ? `${n}. ${title}` : <><span className="sr-only">{n}.</span>{' '}{title}</>}</span>
          <span className="block text-sm text-zinc-500 dark:text-zinc-400 break-words">{summary}</span>
        </span>
        {reviewed && !open ? (
          <span aria-label={`Edit ${title}`} title="Edit" className="w-10 h-10 flex items-center justify-center flex-shrink-0 rounded-xl border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300">
            <svg aria-hidden="true" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.9 3.9a2.1 2.1 0 013 3L7.6 19.2 3.5 20.5l1.3-4.1L16.9 3.9z" />
            </svg>
          </span>
        ) : <svg aria-hidden="true" className={`w-4 h-4 flex-shrink-0 text-zinc-500 dark:text-zinc-400 transition-transform ${open && !locked ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
        </svg>}
      </button>
      {everOpened && !locked && <div hidden={!open} className="px-5 pb-5">{children}</div>}
    </section>
  )
}
