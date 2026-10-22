import { useState, type ReactNode } from 'react'

const iconBtn = 'w-9 h-9 flex items-center justify-center text-sm border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'

export interface ReorderItem {
  key: string
  /** What is read in the row and in the aria-labels of its arrows. */
  name: string
  content: ReactNode
}

/** A numbered list the user reorders by dragging a row's handle or with its
 * up/down arrows — the same control the authors list uses. */
export default function ReorderList({ items, onMove }: {
  items: ReorderItem[]
  onMove: (from: number, to: number) => void
}) {
  const [dragging, setDragging] = useState<number | null>(null)
  return (
    <ol className="space-y-2">
      {items.map((item, i) => (
        <li
          key={item.key}
          onDragOver={(e) => { if (dragging !== null) e.preventDefault() }}
          onDrop={() => { if (dragging !== null) onMove(dragging, i); setDragging(null) }}
          className={`flex items-center gap-3 px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900/40 ${dragging === i ? 'opacity-50 border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}
        >
          <span
            draggable aria-hidden="true" title="Drag to reorder"
            onDragStart={() => setDragging(i)} onDragEnd={() => setDragging(null)}
            className="cursor-grab select-none text-zinc-400 text-lg leading-none px-1"
          >⠿</span>
          <span className="flex-1 text-sm text-zinc-800 dark:text-zinc-200">
            <span className="font-semibold">{i + 1}.</span> {item.content}
          </span>
          <button type="button" className={iconBtn} aria-label={`Move ${item.name} up`} disabled={i === 0} onClick={() => onMove(i, i - 1)}>↑</button>
          <button type="button" className={iconBtn} aria-label={`Move ${item.name} down`} disabled={i === items.length - 1} onClick={() => onMove(i, i + 1)}>↓</button>
        </li>
      ))}
    </ol>
  )
}
