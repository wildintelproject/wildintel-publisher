/** The steps of the wizard as one rounded bar of equal segments, `›` between them: each says its number and its name; the current one is
 * highlighted with a bar under it, the ones already done keep the normal colour and the ones to come fade the further away they are. */
export default function StepBar({ labels, current }: { labels: string[]; current: number }) {
  return (
    <ol aria-label="Steps" className="mb-10 m-0 flex list-none items-stretch rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 p-1.5">
      {labels.map((label, i) => {
        const active = i === current
        const tone = active
          ? 'text-blue-600 dark:text-blue-400'
          : i < current
            ? 'text-zinc-700 dark:text-zinc-200'
            : i === current + 1
              ? 'text-zinc-500 dark:text-zinc-500'
              : 'text-zinc-400 dark:text-zinc-600'
        return (
          <li key={label} aria-current={active ? 'step' : undefined} className="flex min-w-0 flex-1 items-center">
            <div className={`relative flex flex-1 flex-col items-center justify-center overflow-hidden rounded-xl px-2 pb-2.5 pt-2 ${tone} ${active ? 'bg-blue-50 dark:bg-blue-950/50' : ''}`}>
              <span className="font-mono text-xs font-semibold">{String(i + 1).padStart(2, '0')}</span>
              <span className="truncate text-sm font-semibold">{label}</span>
              {active && <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-[3px] bg-blue-500" />}
            </div>
            {i < labels.length - 1 && <span aria-hidden="true" className="shrink-0 px-1.5 text-xs text-zinc-400 dark:text-zinc-600">›</span>}
          </li>
        )
      })}
    </ol>
  )
}
