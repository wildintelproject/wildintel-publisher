// Licenses offered by YoloMetadataEditor's own License dropdown — picking
// one fills in its id (SPDX), full name and URL at once. Anything else goes
// through the dropdown's "Other…" entry instead.
import type { ProductLicense } from './types'

export interface CommonLicense {
  id: string
  name: string
  url: string
}

export const COMMON_LICENSES: CommonLicense[] = [
  { id: 'CC-BY-NC-4.0', name: 'Creative Commons Attribution-NonCommercial 4.0 International', url: 'https://creativecommons.org/licenses/by-nc/4.0/' },
  { id: 'CC-BY-4.0', name: 'Creative Commons Attribution 4.0 International', url: 'https://creativecommons.org/licenses/by/4.0/' },
  { id: 'CC-BY-SA-4.0', name: 'Creative Commons Attribution-ShareAlike 4.0 International', url: 'https://creativecommons.org/licenses/by-sa/4.0/' },
  { id: 'CC-BY-NC-SA-4.0', name: 'Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International', url: 'https://creativecommons.org/licenses/by-nc-sa/4.0/' },
  { id: 'CC-BY-ND-4.0', name: 'Creative Commons Attribution-NoDerivatives 4.0 International', url: 'https://creativecommons.org/licenses/by-nd/4.0/' },
  { id: 'CC-BY-NC-ND-4.0', name: 'Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International', url: 'https://creativecommons.org/licenses/by-nc-nd/4.0/' },
  { id: 'CC0-1.0', name: 'Creative Commons Zero v1.0 Universal', url: 'https://creativecommons.org/publicdomain/zero/1.0/' },
  { id: 'ODbL-1.0', name: 'Open Data Commons Open Database License v1.0', url: 'https://opendatacommons.org/licenses/odbl/1-0/' },
  { id: 'MIT', name: 'MIT License', url: 'https://opensource.org/licenses/MIT' },
  { id: 'Apache-2.0', name: 'Apache License 2.0', url: 'https://www.apache.org/licenses/LICENSE-2.0' },
]

/** WildINTEL's own policy — every dataset is published under it unless
 * stated otherwise (same default as settings.toml's TRAPPER.license_id). */
export const DEFAULT_LICENSE_ID = 'CC-BY-NC-4.0'

/** Case-insensitive, so a data.yaml's "cc-by-4.0" still matches. */
export function findCommonLicense(id: string | null | undefined): CommonLicense | undefined {
  const wanted = (id ?? '').trim().toLowerCase()
  return wanted ? COMMON_LICENSES.find((l) => l.id.toLowerCase() === wanted) : undefined
}

/** The license to start the editor with: data.yaml's own, completed with
 * the canonical name/URL when it's one of COMMON_LICENSES; kept as-is (the
 * dropdown's "Other…") when it isn't; DEFAULT_LICENSE_ID when data.yaml
 * has none at all. */
export function initialLicense(license: ProductLicense | null | undefined): ProductLicense {
  const hasAny = !!license && [license.id, license.name, license.url].some((v) => (v ?? '').trim())
  if (!hasAny) return { ...findCommonLicense(DEFAULT_LICENSE_ID)! }
  const common = findCommonLicense(license!.id)
  return common ? { ...common } : { id: license!.id ?? '', name: license!.name ?? '', url: license!.url ?? '' }
}
