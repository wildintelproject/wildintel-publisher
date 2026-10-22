import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Report } from '../types'

const btnOutline = 'inline-flex items-center justify-center px-3 py-1.5 text-sm rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors no-underline'

const STATUS_STYLE = {
  ok: 'text-emerald-700 dark:text-emerald-400',
  failed: 'text-red-600 dark:text-red-400',
  warning: 'text-amber-700 dark:text-amber-400',
} as const

/** A report of a validation or a publication, as it was kept: what was checked, what passed, what failed and why —
 * and the files to download it to look at in detail. */
export default function ReportPanel({ reportId }: { reportId: string }) {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setReport(null); setError(null)
    api.getReport(reportId)
      .then((r) => { if (!cancelled) setReport(r) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not read the report.') })
    return () => { cancelled = true }
  }, [reportId])

  if (error) return <p className="text-sm text-red-600 dark:text-red-400 mt-3">{error}</p>
  if (!report) return <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-3">Reading the report…</p>

  const dryRun = report.parameters.dry_run === true
  return (
    <section aria-label="Report" className="mt-4 rounded-xl border border-zinc-200 dark:border-zinc-700 p-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {report.totals.failed === 0 ? 'Nothing failed' : `${report.totals.failed} problem(s)`}
          {report.totals.warnings > 0 && ` · ${report.totals.warnings} warning(s)`}
          {dryRun && ' · dry run'}
        </p>
        <div className="flex gap-2">
          <a className={btnOutline} href={api.reportUrl(report.id, 'csv')} download>Download CSV</a>
          <a className={btnOutline} href={api.reportUrl(report.id, 'json')} download>Download JSON</a>
        </div>
      </div>
      <div className="mt-3 max-h-72 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-zinc-100 dark:bg-zinc-800 text-left text-zinc-500 dark:text-zinc-400">
            <tr>
              <th className="px-2 py-1 font-medium">What</th><th className="px-2 py-1 font-medium">Check</th>
              <th className="px-2 py-1 font-medium">Status</th><th className="px-2 py-1 font-medium">Message</th>
            </tr>
          </thead>
          <tbody>
            {report.entries.map((e, i) => (
              <tr key={`${e.identifier}|${e.check}|${i}`} className="border-t border-zinc-200 dark:border-zinc-800 align-top">
                <td className="px-2 py-1 font-mono break-all">{e.identifier}</td>
                <td className="px-2 py-1">{report.checks[e.check]?.label ?? e.check}</td>
                <td className={`px-2 py-1 font-medium ${STATUS_STYLE[e.status]}`}>{e.status}</td>
                <td className="px-2 py-1 break-words">{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
