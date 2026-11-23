import { useEffect, useState } from 'react'
import { useCurrentTrail } from './Trail'

export const DOCS_URL = 'https://wildintelproject.github.io/wildintel-publisher/'
export const REPO_URL = 'https://github.com/wildintelproject/wildintel-publisher'

interface Props {
  version: string | null
  /** Goes back to the welcome screen. */
  onHome: () => void
  /** Opens the settings page (settings.toml — see SettingsPage). */
  onOpenSettings: () => void
  settingsOpen: boolean
}

const btnOutline = 'px-3 py-1.5 text-sm border border-zinc-300 dark:border-zinc-600 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors'

export default function Navbar({ version, onHome, onOpenSettings, settingsOpen }: Props) {
  const trail = useCurrentTrail()
  const [dark, setDark] = useState(true)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  return (
    <nav className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 print:hidden">
      <div className="max-w-screen-2xl mx-auto px-4 py-2 flex items-center gap-3">
        <button type="button" aria-label="Home" title="Home" onClick={onHome}
                className="flex h-12 w-12 shrink-0 overflow-hidden rounded-xl hover:opacity-80 transition-opacity">
          <img src="/logo.svg" alt="" width={48} height={48} className="h-full w-full" />
        </button>
        <div className="min-w-0 flex-1 flex flex-col justify-center gap-0.5">
          <div className="flex items-center gap-2">
            <span className="font-bold text-zinc-900 dark:text-zinc-100 text-lg leading-tight">WildINTEL Publisher</span>
            {version && (
              <span className="rounded-full bg-cyan-100 dark:bg-cyan-950 px-2 py-0.5 text-xs font-mono text-cyan-700 dark:text-cyan-300">v{version}</span>
            )}
          </div>
          {trail && (
            <nav aria-label="You are here" className="flex min-w-0 items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400">
              {trail.steps.map((step, i) => {
                const last = i === trail.steps.length - 1
                return (
                  <span key={step.label} className="flex shrink-0 items-center gap-1.5">
                    {i > 0 && <span aria-hidden="true">›</span>}
                    {last
                      ? (
                        <span aria-current="page" className="inline-flex items-center gap-2 rounded-full border border-emerald-600/60 dark:border-emerald-500/50 bg-emerald-100 dark:bg-emerald-950/60 px-3 py-1 font-medium text-zinc-900 dark:text-zinc-100">
                          {step.icon && (
                            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current text-emerald-600 dark:text-emerald-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{step.icon}</svg>
                          )}
                          {step.label}
                        </span>
                      )
                      : step.onClick
                        ? <button type="button" className="underline underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={step.onClick}>{step.label}</button>
                        : <span>{step.label}</span>}
                  </span>
                )
              })}
              {trail.description && <span className="hidden min-w-0 truncate lg:inline" title={trail.description}>— {trail.description}</span>}
            </nav>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <a
            className={`${btnOutline} no-underline`}
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            title="Open the documentation"
          >
            ? Help
          </a>

          <button
            className={`${btnOutline} ${settingsOpen ? 'bg-zinc-100 dark:bg-zinc-800' : ''}`}
            title="Settings" aria-label="Settings" aria-pressed={settingsOpen}
            onClick={onOpenSettings}
          >
            ⚙️
          </button>

          <button
            className={btnOutline}
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            onClick={() => setDark(d => !d)}
          >
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
      </div>
    </nav>
  )
}
