// Version-number helpers for publishing a new version of an
// already-published dataset (see PublicationKindPicker/WizardPage).

function parts(version: string): (number | string)[] {
  return version.trim().replace(/^[vV]/, '').split(/[.-]/).map((p) => (/^\d+$/.test(p) ? Number(p) : p))
}

/** Negative/zero/positive like a sort comparator, or null when the two
 * can't be ordered (non-numeric parts that differ). Missing trailing parts
 * count as 0, so "3" == "3.0". */
export function compareVersions(a: string, b: string): number | null {
  const pa = parts(a)
  const pb = parts(b)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] ?? 0
    const y = pb[i] ?? 0
    if (x === y) continue
    if (typeof x === 'number' && typeof y === 'number') return x - y
    return null
  }
  return 0
}

/** Whether `candidate` can be published after `previous`: strictly newer,
 * or — when the two can't be ordered — at least different. */
export function isNewerVersion(candidate: string | null | undefined, previous: string | null | undefined): boolean {
  if (!previous) return true
  if (!candidate?.trim()) return false
  const order = compareVersions(candidate, previous)
  return order === null ? candidate.trim() !== previous.trim() : order > 0
}

/** The next major version, keeping the same number of parts: "3.0" ->
 * "4.0", "3" -> "4", "1.2.3" -> "2.0.0". Falls back to appending ".1"
 * when the first part isn't a number. */
export function nextVersion(previous: string): string {
  const p = parts(previous)
  if (typeof p[0] !== 'number') return `${previous}.1`
  return [p[0] + 1, ...p.slice(1).map(() => 0)].join('.')
}
