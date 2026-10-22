// Compares the title of a dataset with the one of its previous publication,
// to warn when a "new version" doesn't look like one (see WizardPage).

/** Words that say nothing about which dataset it is. */
const STOP_WORDS = new Set(['the', 'a', 'an', 'of', 'and', 'for', 'in', 'on', 'de', 'del', 'la', 'el', 'dataset', 'data', 'version'])

/** Below this share of common words the titles are considered unrelated. */
export const RELATED_THRESHOLD = 0.4

function words(title: string): Set<string> {
  return new Set(
    title
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((w) => w && !STOP_WORDS.has(w) && !/^v?\d+$/.test(w))
      .map((w) => (w.length > 3 && w.endsWith('s') ? w.slice(0, -1) : w)),
  )
}

/** The share of the words of the shorter title that the other one has too
 * (0–1), so adding words to a title doesn't make it a different one. null
 * when either has no words to compare. */
export function titleSimilarity(a: string | null | undefined, b: string | null | undefined): number | null {
  const wa = words(a ?? '')
  const wb = words(b ?? '')
  if (wa.size === 0 || wb.size === 0) return null
  let common = 0
  for (const w of wa) if (wb.has(w)) common++
  return common / Math.min(wa.size, wb.size)
}

/** True only when both titles can be compared and share (almost) nothing. */
export function titlesUnrelated(current: string | null | undefined, previous: string | null | undefined): boolean {
  const similarity = titleSimilarity(current, previous)
  return similarity !== null && similarity < RELATED_THRESHOLD
}
