import { useEffect, useState } from 'react'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import ResumeSessionsPage from './pages/ResumeSessionsPage'
import SettingsPage from './pages/SettingsPage'
import WelcomePage from './pages/WelcomePage'
import WizardPage from './pages/WizardPage'
import { api } from './api'
import type { SessionSummary } from './types'

export default function App() {
  const [currentVersion, setCurrentVersion] = useState<string | null>(null)
  const [backendDown, setBackendDown] = useState(false)
  const [started, setStarted] = useState(false)
  // Sessions an earlier interruption left on disk, at any phase — fetching
  // a source, preprocessing it, or publishing (see the backend's
  // services.session_store) — fetched once on startup and offered ahead of
  // the welcome page; null while still loading (so nothing flashes before
  // the check completes), empty once confirmed there's nothing to resume.
  // Resuming or explicitly skipping clears it so the wizard/welcome page
  // takes over for the rest of this browser session.
  const [unfinishedSessions, setUnfinishedSessions] = useState<SessionSummary[] | null>(null)
  const [resumeSession, setResumeSession] = useState<SessionSummary | null>(null)
  // The settings page is shown over the rest, which stays mounted (just
  // hidden) — so a wizard run in progress isn't lost.
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function ping() {
      const ok = await api.checkHealth()
      if (!cancelled) setBackendDown(!ok)
    }
    ping()
    const interval = setInterval(ping, 10_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  useEffect(() => {
    api.checkVersion()
      .then((v) => setCurrentVersion(v.current === 'dev' ? null : v.current))
      .catch(() => {})
  }, [])

  useEffect(() => {
    api.listPublishSessions()
      .then((sessions) => setUnfinishedSessions(sessions))
      .catch(() => setUnfinishedSessions([]))
  }, [])

  const showResumeScreen = !started && unfinishedSessions !== null && unfinishedSessions.length > 0

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100">
      <Navbar version={currentVersion} settingsOpen={settingsOpen} onOpenSettings={() => setSettingsOpen(true)} />
      {backendDown && (
        <div className="bg-red-50 dark:bg-red-950 border-b border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm text-center py-2">
          Backend not reachable — is the server running?
        </div>
      )}
      <main className="flex-1">
        {settingsOpen && <SettingsPage onClose={() => setSettingsOpen(false)} />}
        <div className={settingsOpen ? 'hidden' : ''}>
          {started
            ? <WizardPage resumeSession={resumeSession ?? undefined} />
            : showResumeScreen
              ? (
                <ResumeSessionsPage
                  sessions={unfinishedSessions!}
                  onResume={(session) => { setResumeSession(session); setStarted(true) }}
                  onDiscarded={(taskId) => setUnfinishedSessions((s) => (s ?? []).filter((x) => x.task_id !== taskId))}
                  onSkip={() => setUnfinishedSessions([])}
                />
              )
              : <WelcomePage onStart={() => setStarted(true)} />}
        </div>
      </main>
      <Footer />
    </div>
  )
}
