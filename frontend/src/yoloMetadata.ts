// YOLO only — validity rules and save shape for YoloMetadataEditor's own
// value (kept out of the component file so it only exports components).
import type { Organization, ProductAuthor, ProductLicense, ProductPublisher, YoloDataYamlMetadata } from './types'

/** An author row the user left completely blank is simply dropped on save;
 * one with an affiliation but no name can't be saved (the backend's
 * YoloAuthor requires a name). */
export function authorIsBlank(author: ProductAuthor): boolean {
  return !(author.name ?? '').trim() && !(author.affiliation ?? '').trim()
}

export function authorIsInvalid(author: ProductAuthor): boolean {
  return !authorIsBlank(author) && !(author.name ?? '').trim()
}

/** A license is always required (the editor starts with one — see
 * initialLicense), and like the backend's YoloLicense it needs at least an
 * id or a name — only reachable through the dropdown's "Other…" entry. */
export function licenseIsInvalid(license: ProductLicense | null | undefined): boolean {
  return !license || (!(license.id ?? '').trim() && !(license.name ?? '').trim())
}

export function yoloMetadataValid(metadata: YoloDataYamlMetadata): boolean {
  return !licenseIsInvalid(metadata.license) && !metadata.authors.some(authorIsInvalid)
}

/** What gets sent to api.updateYoloDataYaml — blank author rows dropped. */
export function yoloMetadataForSave(metadata: YoloDataYamlMetadata): YoloDataYamlMetadata {
  return { ...metadata, authors: metadata.authors.filter((a) => !authorIsBlank(a)) }
}

export function organizationPublisher(org: Organization): ProductPublisher {
  return { name: org.title, website: org.path ?? undefined, email: org.email ?? undefined }
}

/** Publisher and rights holder are both always set: whatever data.yaml
 * already names is kept — a name that isn't one of `organizations` is fine,
 * the editor accepts any text — and a missing one defaults to
 * organizations[0] (publisher) / [1] (rights holder), same as Camtrap DP's own
 * rows (see WizardPage). Returns a warning when data.yaml lists several
 * rights holders, since only one can be kept. */
export function withOrganizationDefaults(
  metadata: YoloDataYamlMetadata, organizations: Organization[],
): { metadata: YoloDataYamlMetadata; warnings: string[] } {
  if (organizations.length === 0) return { metadata, warnings: [] }
  const defaultPublisher = organizations[0]
  const defaultRightsHolder = organizations[1] ?? organizations[0]
  const warnings: string[] = []

  const existingPublisher = metadata.publisher?.name?.trim()
  const matchedPublisher = organizations.find((o) => o.title === existingPublisher)
  const holders = metadata.copyright_holders.filter((h) => h.trim())
  if (holders.length > 1) {
    warnings.push(`data.yaml lists ${holders.length} rights holders — only one can be chosen here.`)
  }
  return {
    metadata: {
      ...metadata,
      publisher: matchedPublisher ? organizationPublisher(matchedPublisher)
        : existingPublisher ? metadata.publisher! : organizationPublisher(defaultPublisher),
      copyright_holders: [holders[0] ?? defaultRightsHolder.title],
    },
    warnings,
  }
}
