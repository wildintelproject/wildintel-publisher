import { useMemo, useState } from 'react'
import type { KeyboardEvent } from 'react'

export interface Suggestion {
  /** What is written in the field when it is picked. */
  value: string
  /** A second line under it (an organization, say). */
  detail?: string
}

/** A text field that suggests known values as you type — pick one, or write
 * anything else: the text is always free. */
export default function SuggestInput<T extends Suggestion>({ id, ariaLabel, value, onChange, onPick, options, className, placeholder }: {
  id?: string
  ariaLabel: string
  value: string
  /** The text changed by typing. */
  onChange: (text: string) => void
  /** A suggestion was picked from the list. */
  onPick: (option: T) => void
  options: T[]
  className: string
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const listId = `${id ?? ariaLabel.replace(/\W+/g, '-')}-suggestions`

  const shown = useMemo(() => {
    const needle = value.trim().toLowerCase()
    return options.filter((o) => !needle || o.value.toLowerCase().includes(needle))
      // Exactly what is already written is not worth suggesting.
      .filter((o) => o.value.trim().toLowerCase() !== needle)
  }, [options, value])

  function pick(option: T) {
    onPick(option)
    setOpen(false)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || shown.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, shown.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); const option = shown[active]; if (option) pick(option) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div className="relative">
      <input
        id={id} aria-label={ariaLabel} role="combobox" aria-expanded={open && shown.length > 0}
        aria-controls={listId} aria-autocomplete="list" autoComplete="off"
        className={className} placeholder={placeholder} value={value}
        onFocus={() => { setActive(0); setOpen(true) }}
        onBlur={() => setOpen(false)}
        onChange={(e) => { onChange(e.target.value); setActive(0); setOpen(true) }}
        onKeyDown={handleKeyDown}
      />
      {open && shown.length > 0 && (
        <ul
          id={listId} role="listbox"
          className="absolute z-10 mt-1 w-full max-h-60 overflow-y-auto rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-lg"
        >
          {shown.map((o, i) => (
            <li
              key={o.value} role="option" aria-selected={i === active}
              className={`px-3 py-2 text-sm cursor-pointer ${i === active ? 'bg-blue-500 text-white' : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-700'}`}
              onMouseDown={(e) => { e.preventDefault(); pick(o) }}
              onMouseEnter={() => setActive(i)}
            >
              <span>{o.value}</span>
              {o.detail && <span className={`block text-xs ${i === active ? 'text-blue-100' : 'text-zinc-500 dark:text-zinc-400'}`}>{o.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
