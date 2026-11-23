import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

/** A step of the path from the home screen to the page: pressable unless it is the last one. */
export interface TrailStep {
  label: string
  onClick?: () => void
  /** The paths of an icon, drawn before the label when the step is the last one. */
  icon?: ReactNode
}

interface Trail {
  steps: TrailStep[]
  /** What the page is, said after the path. */
  description?: string
}

interface Value {
  trail: Trail | null
  setTrail: (trail: Trail | null) => void
  /** Goes to the home screen, the first step of every path. */
  onHome?: () => void
}

const TrailContext = createContext<Value>({ trail: null, setTrail: () => {} })

/** Holds the path of the page that is shown, which the header of the application says. */
export function TrailProvider({ children, onHome }: { children: ReactNode; onHome?: () => void }) {
  const [trail, setTrail] = useState<Trail | null>(null)
  const value = useMemo(() => ({ trail, setTrail, onHome }), [trail, onHome])
  return <TrailContext.Provider value={value}>{children}</TrailContext.Provider>
}

/** The path of the page that is shown, for the header. */
export function useCurrentTrail(): Trail | null {
  return useContext(TrailContext).trail
}

/** A page says where it is: from the home screen to itself; `null` when it is not the one that is shown. The path is cleared when the page goes away. */
export function useTrail(steps: TrailStep[] | null, description?: string) {
  const { setTrail } = useContext(TrailContext)
  const key = steps ? steps.map(s => s.label).join('›') : ''
  // The functions change at every render; the labels say when the path is another one.
  const latest = useMemo(() => (steps ? { steps, description } : null), [key, description]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!latest) return
    setTrail(latest)
    return () => setTrail(null)
  }, [latest, setTrail])
}

/** The path of a page that hangs from the home screen, or from a section that hangs from it: Home › parents › the page. */
export function usePageTrail(page: { title: string; parents?: string[]; icon?: ReactNode; description?: string; active?: boolean }) {
  const { onHome } = useContext(TrailContext)
  const steps: TrailStep[] | null = page.active === false ? null : [
    { label: 'Home', onClick: onHome },
    ...(page.parents ?? []).map(label => ({ label })),
    { label: page.title, icon: page.icon },
  ]
  useTrail(steps, page.description)
}

/** The icons the pages draw in the last step of their path (24×24, stroked). */
export const TRAIL_ICONS = {
  home: <path d="M3 11l9-8 9 8M5 10v10h14V10" />,
  publish: <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />,
  resume: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" /></>,
}
