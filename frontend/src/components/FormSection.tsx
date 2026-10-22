import type { ReactNode } from 'react'

/** A titled block of a publish form — the forms are one flat page, each block a question. */
export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h5 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{title}</h5>
      {hint && <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}

/** What an AI Dataset gets instead of the choice: its images are local files with no other host to link to. */
export function LockedChoice({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-zinc-200 dark:border-zinc-700 px-4 py-3 text-sm">
      <svg aria-hidden="true" className="w-4 h-4 mt-1 flex-shrink-0 text-zinc-500 dark:text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
        <rect x="5" y="11" width="14" height="9" rx="2" /><path strokeLinecap="round" d="M8 11V8a4 4 0 118 0v3" />
      </svg>
      <div>
        <p className="font-semibold text-zinc-800 dark:text-zinc-200">{title}</p>
        <p className="text-zinc-500 dark:text-zinc-400">{description}</p>
      </div>
    </div>
  )
}
