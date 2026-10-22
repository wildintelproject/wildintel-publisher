import type { ReactNode } from 'react'

/** What was decided in the steps before this one, as a row of chips above the step's heading. */
export default function StepChips({ chips }: { chips: { key: string; label: ReactNode; mono?: boolean }[] }) {
  if (chips.length === 0) return null
  return (
    <div role="group" aria-label="Chosen so far" className="flex flex-wrap gap-2 mb-6">
      {chips.map((c) => (
        <span key={c.key} className={`rounded-full border border-zinc-300 dark:border-zinc-700 px-3 py-1 text-xs text-zinc-700 dark:text-zinc-300 ${c.mono ? 'font-mono' : ''}`}>
          {c.label}
        </span>
      ))}
    </div>
  )
}
