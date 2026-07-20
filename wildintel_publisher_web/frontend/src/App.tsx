import { useEffect, useState } from 'react'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import WelcomePage from './pages/WelcomePage'
import WizardPage from './pages/WizardPage'
import { api } from './api'

export default function App() {
  const [currentVersion, setCurrentVersion] = useState<string | null>(null)
  const [backendDown, setBackendDown] = useState(false)
  const [started, setStarted] = useState(false)

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

  return (
    <div className="min-h-screen flex flex-col bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100">
      <Navbar version={currentVersion} />
      {backendDown && (
        <div className="bg-red-50 dark:bg-red-950 border-b border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm text-center py-2">
          Backend not reachable — is the server running?
        </div>
      )}
      <main className="flex-1">
        {started ? <WizardPage /> : <WelcomePage onStart={() => setStarted(true)} />}
      </main>
      <Footer />
    </div>
  )
}
