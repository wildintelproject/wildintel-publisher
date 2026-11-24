import type { ReactNode } from 'react'
import type { ProductType } from '../types'

export interface ProductChoice {
  value: ProductType
  title: string
  description: string
  available: boolean
  /** Where the product usually comes from, said in the footer of an available card. */
  source?: string
}

/** The paths of each product's icon (24×24, stroked). */
const ICONS: Record<ProductType, ReactNode> = {
  camtrapdp: <><rect x="2.5" y="4" width="14" height="12" rx="2" /><circle cx="9.5" cy="10" r="2.5" /><path d="M16.5 14l4 2.2v4.6l-4 2.2-4-2.2v-4.6z" transform="translate(0 -2)" /></>,
  yolo: <><rect x="3" y="3" width="4.5" height="4.5" rx="1" /><rect x="9.75" y="3" width="4.5" height="4.5" rx="1" /><rect x="16.5" y="3" width="4.5" height="4.5" rx="1" /><rect x="3" y="9.75" width="4.5" height="4.5" rx="1" /><rect x="9.75" y="9.75" width="4.5" height="4.5" rx="1" /><rect x="16.5" y="9.75" width="4.5" height="4.5" rx="1" /><rect x="3" y="16.5" width="4.5" height="4.5" rx="1" /><rect x="9.75" y="16.5" width="4.5" height="4.5" rx="1" /><rect x="16.5" y="16.5" width="4.5" height="4.5" rx="1" /></>,
  software: <><rect x="4" y="5" width="16" height="11" rx="1.5" /><path d="M2 19h20M10 9l-2 2.5 2 2.5M14 9l2 2.5-2 2.5" /></>,
  ai_model: <><rect x="5" y="8" width="14" height="11" rx="2" /><path d="M12 4v4M9.5 13h.01M14.5 13h.01M9.5 16h5" /></>,
  ebv: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
  image_gallery: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="M21 16l-5-5-8 9" /></>,
}

function Icon({ product, className }: { product: ProductType; className: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className={`${className} fill-none stroke-current`} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      {ICONS[product]}
    </svg>
  )
}

/** What to publish, as cards to choose from: the ones that can be chosen in a row, each with a round indicator, its icon, title, description and where it comes
 * from; the ones that are still to come below, faded and not choosable. Real radio buttons underneath, so the keyboard and screen readers work as usual. */
export default function ProductCards({ options, value, onChoose }: { options: ProductChoice[]; value: ProductType | null; onChoose: (value: ProductType) => void }) {
  const available = options.filter((o) => o.available)
  const soon = options.filter((o) => !o.available)
  return (
    <div className="space-y-4">
      <div role="radiogroup" aria-label="Product type" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {available.map((option) => {
          const chosen = value === option.value
          return (
            <label
              key={option.value}
              className={[
                'flex cursor-pointer flex-col overflow-hidden rounded-2xl border text-center transition-colors focus-within:ring-2 focus-within:ring-blue-500/50',
                chosen
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
                  : 'border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900/60 hover:border-blue-400 dark:hover:border-blue-500',
              ].join(' ')}
            >
              <input type="radio" name="product-type" className="sr-only" checked={chosen} onChange={() => onChoose(option.value)} />
              <span className="relative flex flex-1 flex-col items-center gap-3 px-6 pb-6 pt-8">
                <span
                  aria-hidden="true"
                  className={`absolute right-4 top-4 flex h-6 w-6 items-center justify-center rounded-full border-2 ${chosen ? 'border-blue-500 bg-blue-500' : 'border-zinc-400 dark:border-zinc-600'}`}
                >
                  {chosen && <span className="h-2 w-2 rounded-full bg-white" />}
                </span>
                <Icon product={option.value} className={`h-12 w-12 ${chosen ? 'text-blue-500' : 'text-zinc-500 dark:text-zinc-400'}`} />
                <strong className="text-lg text-zinc-900 dark:text-zinc-100">{option.title}</strong>
                <span className="text-sm text-zinc-500 dark:text-zinc-400">{option.description}</span>
              </span>
              {option.source && (
                <span className={`border-t px-4 py-3 text-xs font-semibold ${chosen ? 'border-blue-500/40 text-blue-600 dark:text-blue-400' : 'border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400'}`}>
                  Source: {option.source}
                </span>
              )}
            </label>
          )
        })}
      </div>
      {soon.length > 0 && (
        <ul aria-label="Coming soon" className="m-0 grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-3">
          {soon.map((option) => (
            <li key={option.value} className="relative rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white/50 dark:bg-zinc-900/30 p-5 opacity-60">
              <span className="absolute right-4 top-4 rounded-md bg-zinc-200 dark:bg-zinc-800 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Coming soon</span>
              <span className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400">
                <Icon product={option.value} className="h-5 w-5" />
              </span>
              <strong className="block text-lg text-zinc-700 dark:text-zinc-300">{option.title}</strong>
              <span className="text-sm text-zinc-500 dark:text-zinc-400">{option.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
