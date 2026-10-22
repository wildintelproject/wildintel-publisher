export interface Choice<T extends string> {
  value: T
  title: string
  description: string
  /** Greyed out and not choosable — the description says why. */
  disabled?: boolean
}

/** A choice among a few cards, one per option: a round indicator (a disc, or a blue tick once chosen), a title and what it means.
 * Real radio buttons underneath, so the keyboard and screen readers work as usual. */
export default function ChoiceCards<T extends string>({ name, label, options, value, onChoose, layout = 'column' }: {
  name: string
  label: string
  options: Choice<T>[]
  value: T | null
  onChoose: (value: T) => void
  /** Stacked (default) or side by side. */
  layout?: 'column' | 'row'
}) {
  return (
    <div role="radiogroup" aria-label={label} className={layout === 'row' ? 'grid grid-cols-1 sm:grid-cols-2 gap-3' : 'flex flex-col gap-3'}>
      {options.map((option) => {
        const chosen = value === option.value
        return (
          <label
            key={option.value}
            className={[
              'flex items-start gap-4 rounded-xl border px-5 py-4 transition-colors focus-within:ring-2 focus-within:ring-blue-500/50',
              option.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
              chosen
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/20'
                : option.disabled
                  ? 'border-zinc-300 dark:border-zinc-700'
                  : 'border-zinc-300 dark:border-zinc-700 hover:border-blue-400 dark:hover:border-blue-500',
            ].join(' ')}
          >
            <input type="radio" name={name} className="sr-only" checked={chosen} disabled={option.disabled} onChange={() => onChoose(option.value)} />
            {chosen ? (
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-7 w-7 shrink-0 fill-none stroke-blue-500" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9.5" /><path d="M8 12.5l3 3 5-6" />
              </svg>
            ) : (
              <span aria-hidden="true" className="h-7 w-7 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-300/90" />
            )}
            <span className="min-w-0">
              <span className="block text-lg font-semibold leading-snug text-zinc-900 dark:text-zinc-100">{option.title}</span>
              <span className="block mt-1 text-sm text-zinc-500 dark:text-zinc-400">{option.description}</span>
            </span>
          </label>
        )
      })}
    </div>
  )
}
