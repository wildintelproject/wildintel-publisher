import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { ClassificationProject, Deployment, ResearchProject, TrapperDownloadSelection } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

function StepHeading({ n, children }: { n: number; children: ReactNode }) {
  return (
    <h4 className="text-base font-semibold mb-4 text-zinc-700 dark:text-zinc-300 flex items-center gap-2">
      <span className="w-5 h-5 rounded-full bg-zinc-200 dark:bg-zinc-700 text-xs flex items-center justify-center font-bold">{n}</span>
      {children}
    </h4>
  )
}

type ConnStatus = 'idle' | 'testing' | 'ok' | 'error'

interface Props {
  /** Called with the full download selection once a deployment is chosen,
   * or `null` whenever it's no longer valid (upstream selection changed). */
  onSelectionChange: (selection: TrapperDownloadSelection | null) => void
}

export default function TrapperConnectionForm({ onSelectionChange }: Props) {
  const [form, setForm] = useState({ url: '', username: '', password: '' })
  const [hasSavedPassword, setHasSavedPassword] = useState(false)
  const [conn, setConn] = useState<{ status: ConnStatus; message: string }>({ status: 'idle', message: '' })

  // Prefill url/username (and note whether a password is already saved) from
  // settings.toml — the same file 'trapper config' reads/writes on the CLI.
  // The password itself is never sent to the frontend; leaving the password
  // field blank later reuses whatever is already saved (see handleTestConnection).
  useEffect(() => {
    api.trapperGetConfig()
      .then((config) => {
        setForm((f) => ({ ...f, url: config.base_url ?? f.url, username: config.user_name ?? f.username }))
        setHasSavedPassword(config.has_password)
      })
      .catch(() => {})
  }, [])

  const [researchProjects, setResearchProjects] = useState<ResearchProject[]>([])
  const [researchProjectPk, setResearchProjectPk] = useState('')

  const [classificationProjects, setClassificationProjects] = useState<ClassificationProject[]>([])
  const [classificationProjectPk, setClassificationProjectPk] = useState('')
  const [loadingClassificationProjects, setLoadingClassificationProjects] = useState(false)

  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [deploymentPk, setDeploymentPk] = useState('')
  const [loadingDeployments, setLoadingDeployments] = useState(false)

  // Camtrap DP specific — whether the generated package also includes
  // event-level (aggregated) observations, on top of the media-level ones.
  // Trapper's own API defaults this to false; wildintel-publisher defaults
  // it to true instead.
  const [includeEvents, setIncludeEvents] = useState(true)

  function setField(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
    setConn({ status: 'idle', message: '' })
    setResearchProjects([])
    setResearchProjectPk('')
    setClassificationProjects([])
    setClassificationProjectPk('')
    setDeployments([])
    setDeploymentPk('')
  }

  const canTest = form.url !== '' && form.username !== '' && (form.password !== '' || hasSavedPassword)
  const isTesting = conn.status === 'testing'

  async function handleTestConnection() {
    setConn({ status: 'testing', message: '' })
    setResearchProjects([])
    setResearchProjectPk('')
    try {
      // A blank password here reuses whatever the backend already has saved
      // (see services.trapper_service.resolve_credentials) — the frontend
      // never receives the actual saved password to fill it back in itself.
      const result = await api.trapperTestConnection(form.url, form.username, form.password)
      const { results } = await api.trapperResearchProjects(form.url, form.username, form.password)
      setResearchProjects(results)
      setHasSavedPassword(true) // the backend saves credentials on a successful test
      setConn({
        status: 'ok',
        message: `Connected — ${result.research_projects_count} research project(s) available.`,
      })
    } catch (e) {
      setConn({ status: 'error', message: e instanceof Error ? e.message : 'Could not connect to Trapper.' })
    }
  }

  async function handleResearchProjectChange(pk: string) {
    setResearchProjectPk(pk)
    setClassificationProjectPk('')
    setClassificationProjects([])
    setDeploymentPk('')
    setDeployments([])
    if (!pk) return
    setLoadingClassificationProjects(true)
    try {
      const { results } = await api.trapperClassificationProjects(form.url, form.username, form.password, Number(pk))
      setClassificationProjects(results)
    } catch {
      setClassificationProjects([])
    } finally {
      setLoadingClassificationProjects(false)
    }
  }

  async function handleClassificationProjectChange(pk: string) {
    setClassificationProjectPk(pk)
    setDeploymentPk('')
    setDeployments([])
    if (!pk) return
    setLoadingDeployments(true)
    try {
      const { results } = await api.trapperDeployments(form.url, form.username, form.password, Number(pk))
      setDeployments(results)
    } catch {
      setDeployments([])
    } finally {
      setLoadingDeployments(false)
    }
  }

  const hasResearchProject = researchProjectPk !== ''
  const hasClassificationProject = classificationProjectPk !== ''
  const selectedDeployment = deployments.find((d) => String(d.pk) === deploymentPk)

  // Reports the current selection up to the wizard so it can enable its own
  // "Next" button — cleared (null) whenever the deployment isn't set yet, or
  // stops being valid because an upstream field changed.
  useEffect(() => {
    if (!selectedDeployment || !hasClassificationProject) {
      onSelectionChange(null)
      return
    }
    onSelectionChange({
      url: form.url,
      username: form.username,
      password: form.password,
      projectId: Number(classificationProjectPk),
      deploymentId: selectedDeployment.deployment_id,
      includeEvents,
    })
  }, [selectedDeployment, classificationProjectPk, hasClassificationProject, form.url, form.username, form.password, includeEvents, onSelectionChange])

  return (
    <div>
      {/* ── 1. Connection ── */}
      <StepHeading n={1}>Connect to Trapper</StepHeading>

      <div className="mb-4">
        <label className={labelClass} htmlFor="trapper-url">Trapper URL</label>
        <input
          id="trapper-url"
          className={inputClass}
          placeholder="https://trapper.example.com"
          value={form.url}
          onChange={(e) => setField('url', e.target.value)}
          autoComplete="url"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className={labelClass} htmlFor="trapper-username">Username</label>
          <input
            id="trapper-username"
            className={inputClass}
            value={form.username}
            onChange={(e) => setField('username', e.target.value)}
            autoComplete="username"
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="trapper-password">Password</label>
          <input
            id="trapper-password"
            type="password"
            className={inputClass}
            placeholder="••••••••"
            value={form.password}
            onChange={(e) => setField('password', e.target.value)}
            autoComplete="current-password"
          />
          {hasSavedPassword && form.password === '' && (
            <p className={hintClass}>Already saved — leave blank to reuse it.</p>
          )}
        </div>
      </div>

      <div className="mb-6">
        <div className="flex justify-end">
          <button
            type="button"
            disabled={!canTest || isTesting}
            onClick={handleTestConnection}
            className={[
              'px-4 py-2 text-sm rounded border flex items-center gap-2 transition-colors',
              canTest && !isTesting
                ? 'border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-200 hover:border-blue-500 hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer'
                : 'border-zinc-300 dark:border-zinc-700 text-zinc-400 dark:text-zinc-600 cursor-not-allowed',
            ].join(' ')}
          >
            {isTesting && <SmallSpinner />}
            {isTesting ? 'Testing…' : 'Test Connection'}
          </button>
        </div>

        {conn.status === 'ok' && (
          <div className="flex items-center gap-1.5 mt-2 text-sm text-emerald-600 dark:text-emerald-400 justify-end">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            {conn.message}
          </div>
        )}
        {conn.status === 'error' && (
          <div className="mt-2 text-sm text-red-600 dark:text-red-400 text-right">
            {conn.message}
          </div>
        )}
      </div>

      {conn.status === 'ok' && (
        <>
          <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />

          {/* ── 2. Research project ── */}
          <StepHeading n={2}>Research project</StepHeading>

          <div className="mb-6">
            <label className={labelClass} htmlFor="trapper-research-project">Research project</label>
            <select
              id="trapper-research-project"
              disabled={researchProjects.length === 0}
              className={[inputClass, researchProjects.length === 0 ? 'cursor-not-allowed opacity-50' : ''].join(' ')}
              value={researchProjectPk}
              onChange={(e) => handleResearchProjectChange(e.target.value)}
            >
              <option value="">
                {researchProjects.length === 0 ? 'No research projects found' : 'Select a research project…'}
              </option>
              {researchProjects.map((p) => (
                <option key={p.pk} value={String(p.pk)}>
                  {p.acronym ? `${p.acronym} — ${p.name}` : p.name}
                </option>
              ))}
            </select>
          </div>
        </>
      )}

      {hasResearchProject && (
        <>
          <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />

          {/* ── 3. Classification project ── */}
          <StepHeading n={3}>Classification project</StepHeading>

          <div className="mb-6">
            <label className={labelClass} htmlFor="trapper-classification-project">Classification project</label>
            <select
              id="trapper-classification-project"
              disabled={loadingClassificationProjects || classificationProjects.length === 0}
              className={[
                inputClass,
                loadingClassificationProjects || classificationProjects.length === 0 ? 'cursor-not-allowed opacity-50' : '',
              ].join(' ')}
              value={classificationProjectPk}
              onChange={(e) => handleClassificationProjectChange(e.target.value)}
            >
              <option value="">
                {loadingClassificationProjects
                  ? 'Loading classification projects…'
                  : classificationProjects.length === 0
                  ? 'No classification projects found'
                  : 'Select a classification project…'}
              </option>
              {classificationProjects.map((p) => (
                <option key={p.pk} value={String(p.pk)}>
                  {p.name}{p.is_active ? '' : ' (inactive)'}
                </option>
              ))}
            </select>
          </div>
        </>
      )}

      {hasClassificationProject && (
        <>
          <div className="border-t border-zinc-200 dark:border-zinc-700 mb-6" />

          {/* ── 4. Deployment ── */}
          <StepHeading n={4}>Deployment</StepHeading>

          <div className="mb-2">
            <label className={labelClass} htmlFor="trapper-deployment">Deployment</label>
            <select
              id="trapper-deployment"
              disabled={loadingDeployments || deployments.length === 0}
              className={[
                inputClass,
                loadingDeployments || deployments.length === 0 ? 'cursor-not-allowed opacity-50' : '',
              ].join(' ')}
              value={deploymentPk}
              onChange={(e) => setDeploymentPk(e.target.value)}
            >
              <option value="">
                {loadingDeployments
                  ? 'Loading deployments…'
                  : deployments.length === 0
                  ? 'No deployments found'
                  : 'Select a deployment…'}
              </option>
              {deployments.map((d) => (
                <option key={d.pk} value={String(d.pk)}>
                  {d.deployment_id}{d.location_id ? ` (${d.location_id})` : ''}
                </option>
              ))}
            </select>
          </div>

          {selectedDeployment && (
            <div className="flex items-center gap-1.5 mt-3 text-sm text-emerald-600 dark:text-emerald-400">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              Selected deployment: <span className="font-mono">{selectedDeployment.deployment_id}</span>
            </div>
          )}

          <label className="flex items-start gap-3 cursor-pointer mt-5">
            <input
              type="checkbox"
              checked={includeEvents}
              onChange={(e) => setIncludeEvents(e.target.checked)}
              className="mt-1 w-4 h-4 rounded border-zinc-300 dark:border-zinc-600 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm">
              <span className="font-semibold text-zinc-800 dark:text-zinc-200">Include events</span>
              <span className="block text-zinc-500 dark:text-zinc-400">
                Also generates event-level (aggregated) observations, alongside the media-level
                ones already included — needs sequences to have been generated for this project.
              </span>
            </span>
          </label>
        </>
      )}
    </div>
  )
}
