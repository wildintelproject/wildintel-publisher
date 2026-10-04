// YOLO only — validity rules and save shape for YoloMetadataEditor's own
// value (kept out of the component file so it only exports components).
import type { Organization, ProductAuthor, ProductLicense, ProductPublisher, YoloDataYamlMetadata } from './types'

/** An author row the user left completely blank is simply dropped on save;
 * one with an affiliation but no name can't be saved (the backend's
 * YoloAuthor requires a name). */
function authorIsBlank(author: ProductAuthor): boolean {
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

/** Same rules as Camtrap DP's own publisher/rightsHolder rows (see
 * WizardPage): both are always set, to one of `organizations` — whichever
 * data.yaml already names, if it's one of them, else organizations[0]/[1].
 * Returns a warning for every value that gets replaced that way, so it's
 * never a silent surprise. */
export function withOrganizationDefaults(
  metadata: YoloDataYamlMetadata, organizations: Organization[],
): { metadata: YoloDataYamlMetadata; warnings: string[] } {
  if (organizations.length === 0) return { metadata, warnings: [] }
  const defaultPublisher = organizations[0]
  const defaultRightsHolder = organizations[1] ?? organizations[0]
  const warnings: string[] = []

  const existingPublisher = metadata.publisher?.name
  const matchedPublisher = organizations.find((o) => o.title === existingPublisher)
  if (existingPublisher && !matchedPublisher) {
    warnings.push(
      `"${existingPublisher}" is the publisher in data.yaml, but isn't one of the selectable organizations — ` +
      `it will be replaced by "${defaultPublisher.title}" unless you choose another one below.`,
    )
  }
  const existingHolders = metadata.copyright_holders
  const matchedRightsHolder = organizations.find((o) => o.title === existingHolders[0])
  if (existingHolders.length > 0 && !matchedRightsHolder) {
    warnings.push(
      `"${existingHolders[0]}" is the rights holder in data.yaml, but isn't one of the selectable organizations — ` +
      `it will be replaced by "${defaultRightsHolder.title}" unless you choose another one below.`,
    )
  }
  if (existingHolders.length > 1) {
    warnings.push(`data.yaml lists ${existingHolders.length} rights holders — only one can be chosen here.`)
  }
  return {
    metadata: {
      ...metadata,
      publisher: organizationPublisher(matchedPublisher ?? defaultPublisher),
      copyright_holders: [(matchedRightsHolder ?? defaultRightsHolder).title],
    },
    warnings,
  }
}
